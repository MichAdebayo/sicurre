import path from "node:path";

import { toNodeHandler } from "better-auth/node";
import { config as loadEnv } from "dotenv";

loadEnv({ path: path.resolve(process.cwd(), ".env") });

const [{ auth, authDatabaseDialect, authEmailExists, prepareAuthDatabase }, { createAuthApp }] = await Promise.all([
  import("./auth.js"),
  import("./server.js"),
]);
const port = Number(process.env.SICURRE_BETTER_AUTH_PORT ?? process.env.BETTER_AUTH_PORT ?? 3005);

try {
  await prepareAuthDatabase();
  createAuthApp({
    databaseDialect: authDatabaseDialect,
    emailExists: authEmailExists,
    getSession: (headers) => auth.api.getSession({ headers }),
    authHandler: toNodeHandler(auth),
  }).listen(port, () => {
    console.log(`Better Auth server listening on http://127.0.0.1:${port}`);
  });
} catch (error) {
  console.error("Better Auth database initialization failed", error);
  process.exit(1);
}
