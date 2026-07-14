import { mkdtemp, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

let gateway;
let gatewayBase;
let upstream;

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

beforeAll(async () => {
  const dist = await mkdtemp(path.join(tmpdir(), "sicurre-gateway-"));
  await writeFile(path.join(dist, "index.html"), "<html>sicurre shell</html>");
  await writeFile(path.join(dist, "app.js"), "console.log('asset')");

  upstream = http.createServer((request, response) => {
    if (request.url === "/v1/fail") {
      request.socket.destroy();
      return;
    }
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      response.writeHead(201, {
        "Content-Type": "application/json",
        "Content-Encoding": "identity",
        Connection: "close",
      });
      response.end(JSON.stringify({
        method: request.method,
        body: Buffer.concat(chunks).toString(),
        host: request.headers.host,
      }));
    });
  });
  const upstreamPort = await listen(upstream);
  process.env.APP_DIST_DIR = dist;
  process.env.PORT = "0";
  process.env.API_SERVICE_URL = `http://127.0.0.1:${upstreamPort}`;
  process.env.AUTH_SERVICE_URL = `http://127.0.0.1:${upstreamPort}`;
  gateway = await import("../../../scripts/app/container_server.mjs");
  const startedGateway = gateway.startServer();
  await new Promise((resolve) => startedGateway.once("listening", resolve));
  const gatewayPort = startedGateway.address().port;
  gatewayBase = `http://127.0.0.1:${gatewayPort}`;
});

afterAll(async () => {
  await Promise.all([
    new Promise((resolve) => gateway.server.close(resolve)),
    new Promise((resolve) => upstream.close(resolve)),
  ]);
});

describe("app gateway routing and metrics", () => {
  it.each([
    ["/api/auth/session", "auth"],
    ["/v1/threats", "api"],
    ["/openapi.json", "api"],
    ["/assets/app.js", "assets"],
    ["/metrics", "metrics"],
    ["/__app/health", "health"],
    ["/dashboard", "app"],
  ])("classifies %s as %s", (pathname, expected) => {
    expect(gateway.metricRoute(pathname)).toBe(expected);
  });

  it("selects only authentication and API upstream routes", () => {
    expect(gateway.shouldProxy("/api/auth/session")).toBe(process.env.AUTH_SERVICE_URL);
    expect(gateway.shouldProxy("/v1/threats")).toBe(process.env.API_SERVICE_URL);
    expect(gateway.shouldProxy("/auth/session")).toBe(process.env.API_SERVICE_URL);
    expect(gateway.shouldProxy("/dashboard")).toBeNull();
  });

  it("rejects path traversal and maps the root document", () => {
    expect(gateway.safeFilePath("/")).toMatch(/index\.html$/);
    expect(gateway.safeFilePath("/../../etc/passwd")).toBeNull();
  });

  it("serves health, static assets, and SPA fallbacks", async () => {
    const health = await fetch(`${gatewayBase}/__app/health`);
    expect(health.status).toBe(200);
    expect(await health.json()).toEqual({ status: "ok", service: "sicurre-app" });

    const asset = await fetch(`${gatewayBase}/app.js`);
    expect(asset.headers.get("cache-control")).toContain("immutable");
    expect(await asset.text()).toContain("asset");

    const fallback = await fetch(`${gatewayBase}/missing/route`);
    expect(fallback.headers.get("cache-control")).toBe("no-store");
    expect(await fallback.text()).toContain("sicurre shell");
  });

  it("proxies GET, POST, and HEAD requests without leaking gateway headers", async () => {
    const getResponse = await fetch(`${gatewayBase}/v1/items`);
    expect(getResponse.status).toBe(201);
    expect((await getResponse.json()).method).toBe("GET");
    expect(getResponse.headers.get("content-encoding")).toBeNull();

    const postResponse = await fetch(`${gatewayBase}/api/auth/check`, {
      method: "POST",
      body: JSON.stringify({ ok: true }),
      headers: { "Content-Type": "application/json" },
    });
    const postBody = await postResponse.json();
    expect(postBody.method).toBe("POST");
    expect(postBody.body).toBe('{"ok":true}');

    expect((await fetch(`${gatewayBase}/v1/items`, { method: "HEAD" })).status).toBe(201);
  });

  it("returns a stable 502 when an upstream connection fails", async () => {
    const response = await fetch(`${gatewayBase}/v1/fail`);

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ detail: "App gateway request failed" });
  });

  it("renders counters and cumulative duration buckets", async () => {
    gateway.observeRequest("api", 200, 0.04);
    gateway.observeRequest("api", 503, 0.4);

    const response = await fetch(`${gatewayBase}/metrics`);
    const metrics = await response.text();

    expect(metrics).toContain('sicurre_app_gateway_requests_total{route="health"} 1');
    expect(metrics).toContain('sicurre_app_gateway_responses_total{route="api",status="200"} 1');
    expect(metrics).toContain('sicurre_app_gateway_request_duration_seconds_count{route="api"}');
    expect(metrics).toContain('sicurre_app_gateway_request_duration_seconds_bucket{route="api",le="0.05"}');
  });
});
