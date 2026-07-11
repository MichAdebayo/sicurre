import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";
import { config as loadEnv } from "dotenv";

import {
  auth,
  authDatabase,
  authDatabaseDialect,
  prepareAuthDatabase,
} from "../../auth-service/auth.js";

type Args = {
  email: string;
  password: string;
  name: string;
};

const rootDir = path.resolve(import.meta.dirname, "../..");
const envPath = path.join(rootDir, ".env");

loadEnv({ path: envPath });

function parseArgs(): Args {
  const args = new Map<string, string>();
  for (let index = 2; index < process.argv.length; index += 1) {
    const key = process.argv[index];
    const next = process.argv[index + 1];
    if (!key.startsWith("--") || !next || next.startsWith("--")) continue;
    args.set(key.slice(2), next);
    index += 1;
  }

  const email = args.get("email") ?? process.env.SICURRE_ADMIN_EMAIL ?? "";
  const password = args.get("password") ?? process.env.SICURRE_ADMIN_PASSWORD ?? "";
  const name = args.get("name") ?? process.env.SICURRE_ADMIN_NAME ?? "Sicurre Admin";

  if (!email || !email.includes("@")) {
    throw new Error("Missing --email admin@example.com or SICURRE_ADMIN_EMAIL.");
  }
  if (!password || password.length < 8) {
    throw new Error("Missing --password with at least 8 characters or SICURRE_ADMIN_PASSWORD.");
  }

  return { email: email.trim().toLowerCase(), password, name: name.trim() };
}

function ensureAdminEmailInEnv(email: string): boolean {
  const existing = fs.existsSync(envPath) ? fs.readFileSync(envPath, "utf8") : "";
  const key = "SICURRE_PLATFORM_ADMIN_EMAILS";
  const lines = existing.split(/\r?\n/);
  const index = lines.findIndex((line) => line.startsWith(`${key}=`));
  const currentValue = index >= 0 ? lines[index].slice(key.length + 1).trim() : "";
  const emails = new Set(
    currentValue
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );

  if (emails.has(email)) return false;
  emails.add(email);

  const nextLine = `${key}=${Array.from(emails).join(",")}`;
  if (index >= 0) {
    lines[index] = nextLine;
  } else {
    if (existing.length > 0 && !existing.endsWith("\n")) lines.push("");
    lines.push(nextLine);
  }
  fs.writeFileSync(envPath, lines.join("\n"));
  return true;
}

async function main(): Promise<void> {
  const { email, password, name } = parseArgs();

  if (process.env.SICURRE_ENVIRONMENT?.trim().toLowerCase() === "production") {
    throw new Error("This local utility cannot edit production administrators.");
  }
  await prepareAuthDatabase();
  if (authDatabaseDialect !== "sqlite" || !("prepare" in authDatabase)) {
    throw new Error("The local admin utility requires the SQLite auth adapter.");
  }
  const localAuthDatabase = authDatabase as Database.Database;
  const existingUser = localAuthDatabase
    .prepare('SELECT id, email FROM "user" WHERE lower(email) = ? LIMIT 1')
    .get(email) as { id: string; email: string } | undefined;

  if (!existingUser) {
    await auth.api.signUpEmail({
      body: { email, password, name },
    });
  } else {
    localAuthDatabase.prepare('UPDATE "user" SET name = ?, "updatedAt" = ? WHERE id = ?').run(
      name,
      new Date(),
      existingUser.id,
    );
  }

  localAuthDatabase.prepare('UPDATE "user" SET "emailVerified" = 1, "updatedAt" = ? WHERE lower(email) = ?').run(
    new Date(),
    email,
  );
  const envChanged = ensureAdminEmailInEnv(email);

  console.log(existingUser ? "Admin Better Auth user already existed; name/email verification updated." : "Admin Better Auth user created.");
  console.log(envChanged ? `${email} added to SICURRE_PLATFORM_ADMIN_EMAILS.` : `${email} already present in SICURRE_PLATFORM_ADMIN_EMAILS.`);
  console.log("Restart the FastAPI server after changing .env so admin detection reloads.");
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
