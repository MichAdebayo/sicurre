import Database from "better-sqlite3";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../auth-service/env.js", () => ({}));
vi.mock("pg", () => ({ Pool: class {} }));
vi.mock("../../../auth-service/database.js", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../../auth-service/database.js")>(),
  // Exercise the real auth configuration without any production DB connection.
  createPostgresAuthDatabase: () => {
    const adapter = new Database(":memory:");
    return { adapter, database: { destroy: async () => adapter.close() } };
  },
}));

describe("local-only Better Auth documentation", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("BETTER_AUTH_SECRET", "test-only-documentation-secret-1234567890abcdef");
    vi.stubEnv("BETTER_AUTH_URL", "http://localhost:3005");
    vi.stubEnv("SICURRE_BETTER_AUTH_SCHEMA", "auth");
    vi.stubEnv("SICURRE_FRONTEND_ORIGIN", "http://localhost:5173");
  });
  afterEach(() => vi.unstubAllEnvs());

  it.each([
    ["development", 200], ["dev", 200], ["local", 200],
    ["production", 404], [" Production ", 404], ["prod", 404], ["staging", 404], ["", 404],
  ])("serves documentation in %s with status %i", async (environment, status) => {
    const production = String(environment).trim().toLowerCase() === "production";
    vi.stubEnv("SICURRE_ENVIRONMENT", String(environment));
    vi.stubEnv("SICURRE_LOCAL_BETTER_AUTH_DB_PATH", production ? "" : ":memory:");
    vi.stubEnv("SICURRE_BETTER_AUTH_DATABASE_URL", production ? "postgresql://test:test@localhost/test" : "");
    const { auth, closeAuthDatabase } = await import("../../../auth-service/auth.js");
    try {
      for (const path of ["/reference", "/open-api/generate-schema"]) {
        const response = await auth.handler(new Request(`http://localhost:3005/api/auth${path}`));
        expect(response.status).toBe(status);
        const body = await response.text();
        if (status === 200) {
          expect(body).not.toContain(process.env.BETTER_AUTH_SECRET);
          expect(body).not.toContain("postgresql://");
          expect(body).toContain(path === "/reference" ? "Scalar API Reference" : '"openapi"');
        }
      }
      expect((await auth.handler(new Request("http://localhost:3005/api/auth/ok"))).status).toBe(200);
    } finally {
      await closeAuthDatabase();
    }
  });
});
