import request from "supertest";
import { describe, expect, it, vi } from "vitest";

import { createAuthApp } from "../../../auth-service/server.js";

function dependencies(overrides: Record<string, unknown> = {}) {
  return {
    databaseDialect: "sqlite",
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

  it("forwards remaining auth requests to the injected handler", async () => {
    const deps = dependencies();
    const app = createAuthApp(deps);

    expect((await request(app).post("/api/auth/sign-in/email")).status).toBe(204);
    expect(deps.authHandler).toHaveBeenCalledOnce();
  });
});
