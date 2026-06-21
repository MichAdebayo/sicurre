import path from "node:path";

import cors from "cors";
import { config as loadEnv } from "dotenv";
import express, { type Request, type Response } from "express";
import { fromNodeHeaders, toNodeHandler } from "better-auth/node";

import { auth } from "./auth.js";

loadEnv({ path: path.resolve(process.cwd(), ".env") });

const app = express();
const port = Number(process.env.SICURRE_BETTER_AUTH_PORT ?? process.env.BETTER_AUTH_PORT ?? 3005);
const frontendOrigin = process.env.SICURRE_FRONTEND_ORIGIN ?? "http://127.0.0.1:5173";

app.use(
  cors({
    origin: frontendOrigin,
    credentials: true,
  }),
);

app.all("/api/auth/*", toNodeHandler(auth));

app.use(express.json());

app.get("/api/auth/health", (_req: Request, res: Response) => {
  res.json({ status: "ok", service: "better-auth" });
});

app.get("/api/auth/debug-session", async (req: Request, res: Response) => {
  const session = await auth.api.getSession({
    headers: fromNodeHeaders(req.headers),
  });
  res.json(session);
});

app.listen(port, () => {
  console.log(`Better Auth server listening on http://127.0.0.1:${port}`);
});