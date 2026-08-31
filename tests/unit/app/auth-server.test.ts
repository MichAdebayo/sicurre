import request from "supertest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createAuthApp } from "../../../auth-service/server.js";

function dependencies(overrides: Record<string, unknown> = {}) {
  return {
    databaseDialect: "sqlite",
    authHandler: vi.fn((_req, res) => res.status(204).end()),
    ...overrides,
  };
}

describe("Better Auth HTTP boundary", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("does not advertise the server stack", async () => {
    // Express sets X-Powered-By by default. It tells an attacker what to
    // target and serves no purpose to any legitimate client.
    const response = await request(createAuthApp(dependencies())).get("/api/auth/health");

    expect(response.headers["x-powered-by"]).toBeUndefined();
  });

  it("does not trust a developer origin when running in production", async () => {
    vi.stubEnv("SICURRE_ENVIRONMENT", "production");
    vi.stubEnv("SICURRE_FRONTEND_ORIGIN", "https://sicurre.com");

    // The CORS list is built at module scope, so assert the builder directly:
    // this is the value the production process would hand to cors().
    const { buildTrustedOrigins } = await import("../../../auth-service/trusted-origins.js");
    const origins = buildTrustedOrigins();

    expect(origins).toEqual(["https://sicurre.com"]);
  });

  it("redirects older local verification links without verifying the account", async () => {
    vi.stubEnv("SICURRE_FRONTEND_ORIGIN", "");
    const deps = dependencies();
    const response = await request(createAuthApp(deps)).get("/verify-email");
    expect(response.status).toBe(302);
    expect(response.headers.location).toBe("http://127.0.0.1:5173/verify-email");
    expect(deps.authHandler).not.toHaveBeenCalled();
  });

  it("uses the configured frontend for local legacy redirects", async () => {
    vi.stubEnv("SICURRE_FRONTEND_ORIGIN", "http://localhost:5174");
    const response = await request(createAuthApp(dependencies())).get("/verify-email");
    expect(response.headers.location).toBe("http://localhost:5174/verify-email");
  });

  it("does not add the local compatibility redirect to production auth", async () => {
    const response = await request(createAuthApp(dependencies({ databaseDialect: "postgresql" }))).get("/verify-email");
    expect(response.status).toBe(404);
  });
  it("reports health and disabled Turnstile configuration", async () => {
    delete process.env.TURNSTILE_SITE_KEY;
    delete process.env.TURNSTILE_SECRET_KEY;
    const app = createAuthApp(dependencies());

    expect((await request(app).get("/api/auth/health")).body).toEqual({
      status: "ok",
      service: "better-auth",
      database: "sqlite",
    });
    expect((await request(app).get("/api/auth/config")).body).toEqual({
      turnstile: { enabled: false, siteKey: null },
    });
  });

  it("only exposes a Turnstile site key when both values exist", async () => {
    process.env.TURNSTILE_SITE_KEY = "site";
    process.env.TURNSTILE_SECRET_KEY = "secret";

    const response = await request(createAuthApp(dependencies())).get("/api/auth/config");

    expect(response.body).toEqual({ turnstile: { enabled: true, siteKey: "site" } });
  });

  it("forwards remaining auth requests to the injected handler", async () => {
    const deps = dependencies();
    const app = createAuthApp(deps);

    expect((await request(app).post("/api/auth/sign-in/email")).status).toBe(204);
    expect(deps.authHandler).toHaveBeenCalledOnce();
  });
});
