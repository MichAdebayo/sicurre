import { afterEach, describe, expect, it } from "vitest";
import { Pool } from "pg";

import {
  createPostgresAuthDatabase,
  directMigrationUrl,
  normalizePostgresUrl,
} from "../../../auth-service/database.js";

describe("Better Auth PostgreSQL database configuration", () => {
  let database: ReturnType<typeof createPostgresAuthDatabase>["database"] | null = null;

  afterEach(async () => {
    await database?.destroy();
    database = null;
  });

  it("normalizes Python PostgreSQL URLs and derives the direct migration endpoint", () => {
    const pooled = normalizePostgresUrl(
      "postgresql+psycopg://user:pass@ep-example-pooler.region.neon.tech/db?sslmode=verify-full",
    );

    expect(pooled).toBe(
      "postgresql://user:pass@ep-example-pooler.region.neon.tech/db?sslmode=verify-full",
    );
    expect(directMigrationUrl(pooled)).toBe(
      "postgresql://user:pass@ep-example.region.neon.tech/db?sslmode=verify-full",
    );
  });

  it("uses Better Auth's supported adapter shape and qualifies runtime tables", () => {
    const pool = new Pool({ connectionString: "postgresql://localhost/unused" });
    const configured = createPostgresAuthDatabase(pool, "auth");
    database = configured.database;

    const query = configured.database
      .selectFrom("user" as never)
      .selectAll()
      .compile();

    expect(configured.adapter.type).toBe("postgres");
    expect(configured.adapter.db).toBe(configured.database);
    expect(query.sql).toContain('from "auth"."user"');
  });
});
