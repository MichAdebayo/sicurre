const baseUrl = (process.env.SICURRE_APP_SMOKE_URL || "http://127.0.0.1:5173").replace(/\/$/, "");

const checks = [
  { name: "app health", path: "/__app/health", expect: "sicurre-app" },
  { name: "app metrics", path: "/metrics", expect: "sicurre_app_gateway_requests_total" },
  { name: "landing shell", path: "/", expect: "Sicurre" },
  { name: "login route", path: "/login", expect: "Sicurre" },
  { name: "auth sidecar proxy", path: "/api/auth/health", expect: "better-auth" },
  { name: "auth public config", path: "/api/auth/config", expect: '"enabled":false' },
  { name: "api health proxy", path: "/health", expect: "app-stack-smoke" },
  { name: "openapi proxy", path: "/openapi.json", expect: "\"openapi\"" },
];

for (const check of checks) {
  const response = await fetch(`${baseUrl}${check.path}`);
  if (!response.ok) {
    throw new Error(`${check.name} failed with HTTP ${response.status}`);
  }
  const text = await response.text();
  if (!text.includes(check.expect)) {
    throw new Error(`${check.name} did not include expected marker: ${check.expect}`);
  }
  console.log(`ok: ${check.name} ${check.path}`);
}

const protectedDataResponse = await fetch(`${baseUrl}/v1/data/sources?limit=1`);
if (protectedDataResponse.status !== 401) {
  throw new Error(`protected data endpoint should return HTTP 401, received ${protectedDataResponse.status}`);
}
console.log("ok: protected data endpoint rejects anonymous access");

console.log("ok: app stack smoke complete");
