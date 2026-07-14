import request from "supertest";
import { describe, expect, it, vi } from "vitest";

import { createAuthApp } from "../../../auth-service/server.js";

function dependencies(overrides: Record<string, unknown> = {}) {
  return {
    databaseDialect: "sqlite",
    emailExists: vi.fn(async () => true),
    getSession: vi.fn(async () => ({ user: { id: "u1" } })),
    authHandler: vi.fn((_req, res) => res.status(204).end()),
    ...overrides,
  };
}

describe("Better Auth HTTP boundary", () => {
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

  it("validates, normalizes, and checks email addresses", async () => {
    const emailExists = vi.fn(async () => true);
    const app = createAuthApp(dependencies({ emailExists }));

    expect((await request(app).post("/api/auth/check-email").send({ email: "invalid" })).status).toBe(400);
    expect((await request(app).post("/api/auth/check-email").send({ email: " USER@EXAMPLE.TEST " })).body).toEqual({ exists: true });
    expect(emailExists).toHaveBeenCalledWith("user@example.test");
  });

  it("returns a stable service-unavailable response for database errors", async () => {
    const app = createAuthApp(dependencies({
      emailExists: vi.fn(async () => { throw new Error("database offline"); }),
    }));

    const response = await request(app).post("/api/auth/check-email").send({ email: "user@example.test" });

    expect(response.status).toBe(503);
    expect(response.body).toEqual({ exists: false, error: "auth_database_unavailable" });
  });

  it("forwards session and remaining auth requests to injected handlers", async () => {
    const deps = dependencies();
    const app = createAuthApp(deps);

    expect((await request(app).get("/api/auth/debug-session")).body).toEqual({ user: { id: "u1" } });
    expect((await request(app).post("/api/auth/sign-in/email")).status).toBe(204);
    expect(deps.getSession).toHaveBeenCalledOnce();
    expect(deps.authHandler).toHaveBeenCalledOnce();
  });
});
