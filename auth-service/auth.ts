import path from "node:path";
import { mkdirSync } from "node:fs";

import Database from "better-sqlite3";
import { betterAuth } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { getMigrations } from "better-auth/db/migration";
import { Pool } from "pg";

import { ensureConfiguredAdmin, type AdminSeedResult } from "./admin-seed.js";
import {
  createPostgresAuthDatabase,
  directMigrationUrl,
  normalizePostgresUrl,
} from "./database.js";
import { buildEmailVerificationEntryUrl, resolveFrontendOrigin } from "./email-verification.js";
import { sendLoopsTransactional } from "./loops.js";
import { buildTrustedOrigins } from "./trusted-origins.js";
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
  ? normalizePostgresUrl(configuredProductionDatabaseUrl)
  : undefined;
const productionMigrationDatabaseUrl = productionDatabaseUrl
  ? directMigrationUrl(productionDatabaseUrl)
  : undefined;
const authSchema = (process.env.SICURRE_BETTER_AUTH_SCHEMA ?? "auth").trim();

if (!/^[a-z_][a-z0-9_]*$/.test(authSchema)) {
  throw new Error("SICURRE_BETTER_AUTH_SCHEMA must be a safe PostgreSQL identifier.");
}
if (isProduction && !productionDatabaseUrl) {
  throw new Error("Production Better Auth requires SICURRE_BETTER_AUTH_DATABASE_URL.");
}
if (isProduction && authSecret === "dev-only-better-auth-secret-change-me-please-1234567890") {
  throw new Error("Production Better Auth requires SICURRE_BETTER_AUTH_SECRET.");
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
      max: 10,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
      keepAlive: true,
    })
  : null;
const productionDatabaseConfig = productionPool
  ? createPostgresAuthDatabase(productionPool, authSchema)
  : null;
const productionDatabase = productionDatabaseConfig?.database ?? null;
const productionAuthDatabase = productionDatabaseConfig?.adapter ?? null;

const resolvedLocalDatabasePath = localDatabasePath
  ?? path.resolve(process.cwd(), "data/local/better-auth.db");
if (!isProduction) {
  mkdirSync(path.dirname(resolvedLocalDatabasePath), { recursive: true });
}
const localDatabase = isProduction ? null : new Database(resolvedLocalDatabasePath);

export const authDatabase = productionAuthDatabase ?? localDatabase!;

export async function prepareAuthDatabase(): Promise<void> {
  if (productionPool) {
    await productionPool.query(`CREATE SCHEMA IF NOT EXISTS "${authSchema}"`);
  }
  if (!productionMigrationDatabaseUrl) {
    const { runMigrations } = await getMigrations(auth.options);
    await runMigrations();
    return;
  }

  const migrationPool = new Pool({
    connectionString: productionMigrationDatabaseUrl,
    options: `-c search_path=${authSchema},public`,
    max: 1,
    connectionTimeoutMillis: 10_000,
  });
  try {
    const { runMigrations } = await getMigrations({
      ...auth.options,
      database: migrationPool,
    });
    await runMigrations();
  } finally {
    await migrationPool.end();
  }
}

export async function closeAuthDatabase(): Promise<void> {
  if (productionDatabase) {
    await productionDatabase.destroy();
    return;
  }
  localDatabase?.close();
}

let internalAdminSeedActive = false;

export async function seedProductionAdmin(): Promise<AdminSeedResult> {
  if (!productionPool) return "disabled";

  return ensureConfiguredAdmin(
    {
      email: process.env.SICURRE_ADMIN_EMAIL,
      password: process.env.SICURRE_ADMIN_PASSWORD,
      name: process.env.SICURRE_ADMIN_NAME,
    },
    {
      exists: async (email) => {
        const result = await productionPool.query(
          `SELECT 1 FROM "${authSchema}"."user" WHERE lower(email) = lower($1) LIMIT 1`,
          [email],
        );
        return result.rowCount === 1;
      },
      create: async ({ email, password, name }) => {
        internalAdminSeedActive = true;
        try {
          await auth.api.signUpEmail({ body: { email, password, name } });
        } finally {
          internalAdminSeedActive = false;
        }
      },
      normalize: async ({ email, name }) => {
        await productionPool.query(
          `UPDATE "${authSchema}"."user"
           SET name = $1, "emailVerified" = true, "updatedAt" = $2
           WHERE lower(email) = lower($3)`,
          [name, new Date(), email],
        );
      },
    },
  );
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

const trustedOrigins = buildTrustedOrigins({
  configuredOrigin: process.env.SICURRE_FRONTEND_ORIGIN,
  isProduction,
});
const frontendOrigin = resolveFrontendOrigin({
  configuredOrigin: process.env.SICURRE_FRONTEND_ORIGIN,
  authBaseUrl,
  isProduction,
});

export const auth = betterAuth({
  secret: authSecret,
  baseURL: authBaseUrl,
  basePath: "/api/auth",
  trustedOrigins,
  database: authDatabase,
  advanced: {
    ipAddress: {
      ipAddressHeaders: ["x-real-ip"],
    },
  },
  hooks: {
    before: createAuthMiddleware(async (ctx) => {
      if (
        internalAdminSeedActive
        || ctx.path !== "/sign-up/email"
        || !process.env.TURNSTILE_SECRET_KEY?.trim()
      ) {
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
    autoSignIn: false,
    requireEmailVerification: true,
    minPasswordLength: 8,
    maxPasswordLength: 128,
    sendResetPassword: async ({ user, url }) => {
      const transactionalId = process.env.LOOPS_RESET_PASSWORD_TRANSACTION_ID?.trim() ?? "";
      try {
        await sendLoopsTransactional({
          transactionalId,
          email: user.email,
          dataVariables: {
            firstName: user.name.split(" ")[0] || "Utilisateur",
            resetUrl: url,
          },
        });
      } catch (error) {
        console.error("[Loops] Password reset delivery failed", error);
        throw error;
      }
    },
  },
  emailVerification: {
    sendOnSignUp: true,
    sendOnSignIn: true,
    autoSignInAfterVerification: false,
    sendVerificationEmail: async ({ user, token }) => {
      if (internalAdminSeedActive) return;

      const transactionalId = process.env.LOOPS_SIGN_UP_TRANSACTION_ID?.trim() ?? "";
      try {
        await sendLoopsTransactional({
          transactionalId,
          email: user.email,
          dataVariables: {
            firstName: user.name.split(" ")[0] || "Utilisateur",
            verificationUrl: buildEmailVerificationEntryUrl(frontendOrigin, token),
          },
        });
      } catch (error) {
        console.error("[Loops] Verification delivery failed", error);
        throw error;
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
