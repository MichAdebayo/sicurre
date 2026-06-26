import path from "node:path";

import Database from "better-sqlite3";
import { config as loadEnv } from "dotenv";
import { betterAuth } from "better-auth";

loadEnv({ path: path.resolve(process.cwd(), ".env") });

const authBaseUrl =
  process.env.BETTER_AUTH_URL ??
  process.env.SICURRE_BETTER_AUTH_URL ??
  "http://127.0.0.1:3005";

const authSecret =
  process.env.BETTER_AUTH_SECRET ??
  process.env.SICURRE_BETTER_AUTH_SECRET ??
  "dev-only-better-auth-secret-change-me-please-1234567890";

const sqlitePath =
  process.env.SICURRE_BETTER_AUTH_DB_PATH ??
  path.resolve(process.cwd(), "data/local/sicurre.db");

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
  database: new Database(sqlitePath),
  emailAndPassword: {
    enabled: true,
    autoSignIn: true,
    minPasswordLength: 8,
    maxPasswordLength: 128,
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7,
    updateAge: 60 * 60 * 24,
    storeSessionInDatabase: true,
    preserveSessionInDatabase: true,
  },
});