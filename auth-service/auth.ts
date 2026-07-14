import path from "node:path";
import { mkdirSync } from "node:fs";

import Database from "better-sqlite3";
import { betterAuth } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { getMigrations } from "better-auth/db/migration";
import { Pool } from "pg";

import "./env.js";

const authBaseUrl =
  process.env.BETTER_AUTH_URL ??
  process.env.SICURRE_BETTER_AUTH_URL ??
  "http://127.0.0.1:3005";

const authSecret =
  process.env.BETTER_AUTH_SECRET ??
  process.env.SICURRE_BETTER_AUTH_SECRET ??
  "dev-only-better-auth-secret-change-me-please-1234567890";

const environment = (process.env.SICURRE_ENVIRONMENT ?? "development").trim().toLowerCase();
const isProduction = environment === "production";
const localDatabasePath = process.env.SICURRE_LOCAL_BETTER_AUTH_DB_PATH?.trim();
const configuredProductionDatabaseUrl = process.env.SICURRE_BETTER_AUTH_DATABASE_URL?.trim();
const productionDatabaseUrl = configuredProductionDatabaseUrl
  ?.replace(/^postgresql\+psycopg:\/\//, "postgresql://")
  .replace(/^postgresql\+asyncpg:\/\//, "postgresql://");
const authSchema = (process.env.SICURRE_BETTER_AUTH_SCHEMA ?? "auth").trim();

if (!/^[a-z_][a-z0-9_]*$/.test(authSchema)) {
  throw new Error("SICURRE_BETTER_AUTH_SCHEMA must be a safe PostgreSQL identifier.");
}
if (isProduction && !productionDatabaseUrl) {
  throw new Error("Production Better Auth requires SICURRE_BETTER_AUTH_DATABASE_URL.");
}
if (isProduction && localDatabasePath) {
  throw new Error("Production Better Auth must not define SICURRE_LOCAL_BETTER_AUTH_DB_PATH.");
}
if (!isProduction && productionDatabaseUrl) {
  throw new Error("Local Better Auth must not define SICURRE_BETTER_AUTH_DATABASE_URL.");
}

export const authDatabaseDialect = isProduction ? "postgresql" : "sqlite";
const productionPool = isProduction
  ? new Pool({
      connectionString: productionDatabaseUrl,
      options: `-c search_path=${authSchema},public`,
      max: 10,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
    })
  : null;

const resolvedLocalDatabasePath = localDatabasePath
  ?? path.resolve(process.cwd(), "data/local/better-auth.db");
if (!isProduction) {
  mkdirSync(path.dirname(resolvedLocalDatabasePath), { recursive: true });
}
const localDatabase = isProduction ? null : new Database(resolvedLocalDatabasePath);

export const authDatabase = productionPool ?? localDatabase!;

export async function prepareAuthDatabase(): Promise<void> {
  if (productionPool) {
    await productionPool.query(`CREATE SCHEMA IF NOT EXISTS "${authSchema}"`);
  }
  const { runMigrations } = await getMigrations(auth.options);
  await runMigrations();
}

export async function closeAuthDatabase(): Promise<void> {
  if (productionPool) {
    await productionPool.end();
    return;
  }
  localDatabase?.close();
}

export async function authEmailExists(email: string): Promise<boolean> {
  if (productionPool) {
    const result = await productionPool.query(
      `SELECT 1 AS found FROM "${authSchema}"."user" WHERE lower(email) = $1 LIMIT 1`,
      [email],
    );
    return result.rowCount === 1;
  }
  const row = localDatabase!
    .prepare('SELECT 1 AS found FROM "user" WHERE lower(email) = ? LIMIT 1')
    .get(email) as { found?: number } | undefined;
  return Boolean(row?.found);
}

type TurnstileVerification = {
  success: boolean;
  "error-codes"?: string[];
};

async function verifyTurnstileToken(token: string, remoteIp: string | null): Promise<boolean> {
  const secret = process.env.TURNSTILE_SECRET_KEY?.trim();
  if (!secret) return true;

  const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      secret,
      response: token,
      remoteip: remoteIp || undefined,
      idempotency_key: crypto.randomUUID(),
    }),
    signal: AbortSignal.timeout(8_000),
  });

  if (!response.ok) return false;
  const result = await response.json() as TurnstileVerification;
  return result.success === true;
}

const trustedOrigins = [
  process.env.SICURRE_FRONTEND_ORIGIN,
  "http://127.0.0.1:5173",
  "http://localhost:5173",
].filter(Boolean) as string[];

export const auth = betterAuth({
  secret: authSecret,
  baseURL: authBaseUrl,
  basePath: "/api/auth",
  trustedOrigins,
  database: authDatabase,
  hooks: {
    before: createAuthMiddleware(async (ctx) => {
      if (ctx.path !== "/sign-up/email" || !process.env.TURNSTILE_SECRET_KEY?.trim()) {
        return;
      }

      const token = ctx.headers?.get("x-turnstile-token")?.trim();
      if (!token) {
        throw new APIError("BAD_REQUEST", { message: "TURNSTILE_REQUIRED" });
      }

      const forwardedFor = ctx.headers?.get("cf-connecting-ip")
        ?? ctx.headers?.get("x-forwarded-for")?.split(",")[0]?.trim()
        ?? null;
      let verified = false;
      try {
        verified = await verifyTurnstileToken(token, forwardedFor);
      } catch {
        verified = false;
      }
      if (!verified) {
        throw new APIError("BAD_REQUEST", { message: "TURNSTILE_FAILED" });
      }
    }),
  },
  emailAndPassword: {
    enabled: true,
    autoSignIn: true,
    minPasswordLength: 8,
    maxPasswordLength: 128,
    sendResetPassword: async ({ user, url }) => {
      const apiKey = process.env.LOOPS_API_KEY;
      const transactionalId = process.env.LOOPS_RESET_PASSWORD_TRANSACTION_ID;
      if (!apiKey || !transactionalId) {
        console.warn(`[Loops] Missing key or Transaction ID for password reset to ${user.email}`);
        return;
      }
      try {
        const res = await fetch("https://api.loops.so/v1/transactional", {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${apiKey}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            transactionalId,
            email: user.email,
            dataVariables: {
              firstName: user.name.split(" ")[0] || "Utilisateur",
              resetUrl: url,
            },
          }),
        });
        if (!res.ok) {
          console.error(`[Loops] Password reset mail error: ${res.status} - ${await res.text()}`);
        }
      } catch (err) {
        console.error(`[Loops] Password reset exception:`, err);
      }
    },
  },
  emailVerification: {
    sendOnSignUp: true,
    sendVerificationEmail: async ({ user, url }) => {
      const apiKey = process.env.LOOPS_API_KEY;
      const transactionalId = process.env.LOOPS_SIGN_UP_TRANSACTION_ID;
      if (!apiKey || !transactionalId) {
        console.warn(`[Loops] Missing key or Transaction ID for sign up verification to ${user.email}`);
        return;
      }
      try {
        const res = await fetch("https://api.loops.so/v1/transactional", {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${apiKey}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            transactionalId,
            email: user.email,
            dataVariables: {
              firstName: user.name.split(" ")[0] || "Utilisateur",
              verificationUrl: url,
            },
          }),
        });
        if (!res.ok) {
          console.error(`[Loops] Verification mail error: ${res.status} - ${await res.text()}`);
        }
      } catch (err) {
        console.error(`[Loops] Verification mail exception:`, err);
      }
    },
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7,
    updateAge: 60 * 60 * 24,
    storeSessionInDatabase: true,
    preserveSessionInDatabase: true,
  },
});
