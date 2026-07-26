import { toNodeHandler } from "better-auth/node";

import "./env.js";
import { runWithStartupRetry } from "./startup.js";

const [
  { auth, authDatabaseDialect, prepareAuthDatabase, seedProductionAdmin },
  { createAuthApp },
] = await Promise.all([import("./auth.js"), import("./server.js")]);
const port = Number(process.env.SICURRE_BETTER_AUTH_PORT ?? process.env.BETTER_AUTH_PORT ?? 3005);

try {
  const adminSeed = await runWithStartupRetry(async () => {
    await prepareAuthDatabase();
    return seedProductionAdmin();
  }, {
    onRetry: (error, attempt, delayMs) => {
      console.warn(JSON.stringify({
        level: "warn",
        service: "auth-service",
        event: "database_initialization_retry",
        attempt,
        delay_ms: delayMs,
        error: error instanceof Error ? error.message : "unknown_error",
      }));
    },
  });
  console.log(JSON.stringify({
    level: "info",
    service: "auth-service",
    event: "admin_seed_checked",
    result: adminSeed,
  }));
  createAuthApp({
    databaseDialect: authDatabaseDialect,
    authHandler: toNodeHandler(auth),
  }).listen(port, () => {
    console.log(JSON.stringify({
      level: "info",
      service: "auth-service",
      event: "server_started",
      address: "127.0.0.1",
      port,
    }));
  });
} catch (error) {
  console.error(JSON.stringify({
    level: "error",
    service: "auth-service",
    event: "database_initialization_failed",
    error: error instanceof Error ? error.message : "unknown_error",
  }));
  process.exit(1);
}
