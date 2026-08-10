import { Kysely, PostgresDialect } from "kysely";
import type { Pool } from "pg";

export function normalizePostgresUrl(databaseUrl: string): string {
  return databaseUrl
    .replace(/^postgresql\+psycopg:\/\//, "postgresql://")
    .replace(/^postgresql\+asyncpg:\/\//, "postgresql://");
}

export function directMigrationUrl(databaseUrl: string): string {
  return databaseUrl.replace(/@(ep-[^.]+)-pooler\./, "@$1.");
}

export function createPostgresAuthDatabase(pool: Pool, schema: string): {
  database: Kysely<unknown>;
  adapter: { db: Kysely<unknown>; type: "postgres" };
} {
  const database = new Kysely<unknown>({
    dialect: new PostgresDialect({ pool }),
  }).withSchema(schema);
  return {
    database,
    adapter: { db: database, type: "postgres" },
  };
}
