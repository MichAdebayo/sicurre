import { createReadStream } from "node:fs";
import { access, stat } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = process.env.APP_DIST_DIR || path.resolve(__dirname, "../../dist");
const port = Number(process.env.PORT || 5173);
const apiServiceUrl = (process.env.API_SERVICE_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
const authServiceUrl = (process.env.AUTH_SERVICE_URL || "http://127.0.0.1:3005").replace(/\/$/, "");
const trustProxyHeaders = process.env.TRUST_PROXY_HEADERS?.trim().toLowerCase() === "true";
const startedAt = Date.now();
let requestTotal = 0;
let proxyErrorsTotal = 0;
const routeCounters = new Map();
const statusCounters = new Map();
const durationBuckets = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];
const routeDurations = new Map();

const mimeTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

// Paths that belong to the API rather than the single-page application.
//
// Anything not listed here falls through to the SPA, which answers every
// unknown path with index.html and HTTP 200. That is correct for client-side
// routing and misleading for everything else: /docs and /redoc returned 200
// while serving the application shell, so the API documentation looked
// published when it was unreachable. /openapi.json was listed, so the raw
// specification worked while the two human-readable views did not.
export function shouldProxy(pathname) {
  if (pathname.startsWith("/api/auth")) return authServiceUrl;
  if (
    pathname === "/health" ||
    pathname === "/openapi.json" ||
    pathname === "/docs" ||
    pathname === "/redoc" ||
    pathname.startsWith("/docs/") ||
    pathname.startsWith("/v1") ||
    pathname.startsWith("/auth") ||
    pathname.startsWith("/internal/ml/")
  ) {
    return apiServiceUrl;
  }
  return null;
}

export function metricRoute(pathname) {
  if (pathname === "/__app/health") return "health";
  if (pathname === "/metrics") return "metrics";
  if (pathname.startsWith("/api/auth")) return "auth";
  if (pathname === "/health" || pathname === "/openapi.json" || pathname.startsWith("/v1") || pathname.startsWith("/auth") || pathname.startsWith("/internal/ml/")) {
    return "api";
  }
  if (pathname.startsWith("/assets")) return "assets";
  return "app";
}

function incrementRoute(pathname) {
  const route = metricRoute(pathname);
  routeCounters.set(route, (routeCounters.get(route) || 0) + 1);
}

export function observeRequest(route, statusCode, durationSeconds) {
  const statusKey = `${route}:${statusCode}`;
  statusCounters.set(statusKey, (statusCounters.get(statusKey) || 0) + 1);
  const observation = routeDurations.get(route) || {
    count: 0,
    sum: 0,
    buckets: new Map(durationBuckets.map((bucket) => [bucket, 0])),
  };
  observation.count += 1;
  observation.sum += durationSeconds;
  for (const bucket of durationBuckets) {
    if (durationSeconds <= bucket) {
      observation.buckets.set(bucket, observation.buckets.get(bucket) + 1);
    }
  }
  routeDurations.set(route, observation);
}

export function renderMetrics() {
  const lines = [
    "# HELP sicurre_app_gateway_uptime_seconds Seconds since the app gateway started.",
    "# TYPE sicurre_app_gateway_uptime_seconds gauge",
    `sicurre_app_gateway_uptime_seconds ${Math.round((Date.now() - startedAt) / 1000)}`,
    "# HELP sicurre_app_gateway_requests_total Total HTTP requests served by the app gateway.",
    "# TYPE sicurre_app_gateway_requests_total counter",
  ];
  for (const [route, count] of routeCounters.entries()) {
    lines.push(`sicurre_app_gateway_requests_total{route="${route}"} ${count}`);
  }
  lines.push(
    "# HELP sicurre_app_gateway_responses_total HTTP responses grouped by route and status.",
    "# TYPE sicurre_app_gateway_responses_total counter",
  );
  for (const [key, count] of statusCounters.entries()) {
    const [route, status] = key.split(":");
    lines.push(`sicurre_app_gateway_responses_total{route="${route}",status="${status}"} ${count}`);
  }
  lines.push(
    "# HELP sicurre_app_gateway_request_duration_seconds End-to-end gateway request duration.",
    "# TYPE sicurre_app_gateway_request_duration_seconds histogram",
  );
  for (const [route, observation] of routeDurations.entries()) {
    for (const bucket of durationBuckets) {
      lines.push(
        `sicurre_app_gateway_request_duration_seconds_bucket{route="${route}",le="${bucket}"} ${observation.buckets.get(bucket)}`,
      );
    }
    lines.push(
      `sicurre_app_gateway_request_duration_seconds_bucket{route="${route}",le="+Inf"} ${observation.count}`,
      `sicurre_app_gateway_request_duration_seconds_sum{route="${route}"} ${observation.sum}`,
      `sicurre_app_gateway_request_duration_seconds_count{route="${route}"} ${observation.count}`,
    );
  }
  lines.push(
    "# HELP sicurre_app_gateway_proxy_errors_total Total upstream proxy failures.",
    "# TYPE sicurre_app_gateway_proxy_errors_total counter",
    `sicurre_app_gateway_proxy_errors_total ${proxyErrorsTotal}`,
    "",
  );
  return lines.join("\n");
}

function readRequestBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks)));
    request.on("error", reject);
  });
}

async function proxyRequest(request, response, targetBase) {
  const target = new URL(request.url || "/", targetBase);
  const headers = { ...request.headers };
  delete headers.host;
  delete headers.connection;
  delete headers["content-length"];
  const forwardedRealIp = headers["x-real-ip"];
  const trustedRealIp = trustProxyHeaders && typeof forwardedRealIp === "string" && net.isIP(forwardedRealIp)
    ? forwardedRealIp
    : null;
  headers["x-real-ip"] = trustedRealIp
    ?? (request.socket.remoteAddress || "127.0.0.1").replace(/^::ffff:/, "");

  const method = request.method || "GET";
  const body = method === "GET" || method === "HEAD" ? undefined : await readRequestBody(request);
  const upstream = await fetch(target, { method, headers, body });
  const responseHeaders = {};
  upstream.headers.forEach((value, key) => {
    if (!["connection", "content-encoding", "content-length", "transfer-encoding"].includes(key)) {
      responseHeaders[key] = value;
    }
  });
  response.writeHead(upstream.status, responseHeaders);
  if (method === "HEAD") {
    response.end();
    return;
  }
  response.end(Buffer.from(await upstream.arrayBuffer()));
}

export function safeFilePath(pathname) {
  const decoded = decodeURIComponent(pathname);
  const relative = decoded === "/" ? "index.html" : decoded.replace(/^\/+/, "");
  const candidate = path.resolve(distDir, relative);
  if (!candidate.startsWith(path.resolve(distDir))) {
    return null;
  }
  return candidate;
}

async function serveStatic(request, response, pathname) {
  const requested = safeFilePath(pathname);
  const indexFile = path.join(distDir, "index.html");
  let filePath = requested;
  if (!filePath) {
    response.writeHead(400);
    response.end("Bad request");
    return;
  }

  try {
    const fileStat = await stat(filePath);
    if (fileStat.isDirectory()) {
      filePath = path.join(filePath, "index.html");
    }
    await access(filePath);
  } catch {
    filePath = indexFile;
  }

  const ext = path.extname(filePath).toLowerCase();
  response.writeHead(200, {
    "Cache-Control": filePath === indexFile ? "no-store" : "public, max-age=31536000, immutable",
    "Content-Type": mimeTypes.get(ext) || "application/octet-stream",
  });
  createReadStream(filePath).pipe(response);
}

export const server = http.createServer(async (request, response) => {
  const requestStartedAt = process.hrtime.bigint();
  const requestUrl = new URL(request.url || "/", "http://localhost");
  const route = metricRoute(requestUrl.pathname);
  response.once("finish", () => {
    const elapsed = Number(process.hrtime.bigint() - requestStartedAt) / 1e9;
    observeRequest(route, response.statusCode, elapsed);
  });
  try {
    const url = requestUrl;
    requestTotal += 1;
    incrementRoute(url.pathname);
    if (url.pathname === "/__app/health") {
      response.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
      response.end(JSON.stringify({ status: "ok", service: "sicurre-app" }));
      return;
    }
    if (url.pathname === "/metrics") {
      response.writeHead(200, { "Content-Type": "text/plain; version=0.0.4; charset=utf-8" });
      response.end(renderMetrics());
      return;
    }
    const proxyBase = shouldProxy(url.pathname);
    if (proxyBase) {
      await proxyRequest(request, response, proxyBase);
      return;
    }
    await serveStatic(request, response, url.pathname);
  } catch (error) {
    proxyErrorsTotal += 1;
    console.error("container_server error", error);
    response.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    response.end(JSON.stringify({ detail: "App gateway request failed" }));
  }
});

export function startServer() {
  return server.listen(port, "0.0.0.0", () => {
    console.log(`Sicurre app server listening on http://0.0.0.0:${port}`);
  });
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) startServer();
