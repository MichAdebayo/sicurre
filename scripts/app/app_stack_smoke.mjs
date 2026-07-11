const baseUrl = (process.env.SICURRE_APP_SMOKE_URL || "http://127.0.0.1:5173").replace(/\/$/, "");

const checks = [
  { name: "app health", path: "/__app/health", expect: "sicurre-app" },
  { name: "app metrics", path: "/metrics", expect: "sicurre_app_gateway_requests_total" },
  { name: "landing shell", path: "/", expect: "Sicurre" },
  { name: "login route", path: "/login", expect: "Sicurre" },
  { name: "auth sidecar proxy", path: "/api/auth/health", expect: "better-auth" },
  { name: "auth public config", path: "/api/auth/config", expect: '"enabled":false' },
  { name: "api health proxy", path: "/health", expect: "app-stack-smoke" },
  { name: "data sources proxy", path: "/v1/data/sources?limit=1", expect: "\"items\"" },
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

const emailCheckResponse = await fetch(`${baseUrl}/api/auth/check-email`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "smoke-does-not-exist@sicurre.invalid" }),
});
if (!emailCheckResponse.ok) {
  throw new Error(`auth email preflight failed with HTTP ${emailCheckResponse.status}`);
}
const emailCheck = await emailCheckResponse.json();
if (emailCheck.exists !== false) {
  throw new Error("auth email preflight should return exists=false for smoke address");
}
console.log("ok: auth email preflight /api/auth/check-email");

console.log("ok: app stack smoke complete");
