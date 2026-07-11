import { closeAuthDatabase, prepareAuthDatabase } from "../../auth-service/auth.js";

async function main(): Promise<void> {
  await prepareAuthDatabase();
  await closeAuthDatabase();
  console.log("Better Auth schema is current.");
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
