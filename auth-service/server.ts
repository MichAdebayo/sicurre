import path from "node:path";

import cors from "cors";
import { config as loadEnv } from "dotenv";
import express, { type Request, type Response } from "express";
import { fromNodeHeaders, toNodeHandler } from "better-auth/node";

import { auth, authDatabase } from "./auth.js";

loadEnv({ path: path.resolve(process.cwd(), ".env") });

const app = express();
const port = Number(process.env.SICURRE_BETTER_AUTH_PORT ?? process.env.BETTER_AUTH_PORT ?? 3005);
const trustedOrigins = [
  process.env.SICURRE_FRONTEND_ORIGIN,
  "http://127.0.0.1:5173",
  "http://localhost:5173",
].filter(Boolean) as string[];

app.use(
  cors({
    origin: trustedOrigins,
    credentials: true,
  }),
);

app.get("/api/auth/health", (_req: Request, res: Response) => {
  res.json({ status: "ok", service: "better-auth" });
});

app.post("/api/auth/check-email", express.json(), (req: Request, res: Response) => {
  const email = typeof req.body?.email === "string" ? req.body.email.trim().toLowerCase() : "";
  if (!email || !email.includes("@")) {
    res.status(400).json({ exists: false });
    return;
  }

  try {
    const row = authDatabase
      .prepare('select 1 as found from "user" where lower(email) = ? limit 1')
      .get(email) as { found?: number } | undefined;
    res.json({ exists: Boolean(row?.found) });
  } catch {
    res.json({ exists: false });
  }
});

app.get("/api/auth/debug-session", async (req: Request, res: Response) => {
  const session = await auth.api.getSession({
    headers: fromNodeHeaders(req.headers),
  });
  res.json(session);
});

app.all("/api/auth/*", toNodeHandler(auth));

app.use(express.json());

app.listen(port, () => {
  console.log(`Better Auth server listening on http://127.0.0.1:${port}`);
});
