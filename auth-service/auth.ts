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