import cors from "cors";
import express, { type Request, type Response } from "express";
import { fromNodeHeaders } from "better-auth/node";

const trustedOrigins = [
  process.env.SICURRE_FRONTEND_ORIGIN,
  "http://127.0.0.1:5173",
  "http://localhost:5173",
].filter(Boolean) as string[];

export type AuthServerDependencies = {
  databaseDialect: string;
  emailExists: (email: string) => Promise<boolean>;
  getSession: (headers: Headers) => Promise<unknown>;
  authHandler: express.RequestHandler;
};

export function createAuthApp(
  dependencies: AuthServerDependencies,
): express.Express {
  const app = express();
  app.use(cors({ origin: trustedOrigins, credentials: true }));

  app.get("/api/auth/health", (_req: Request, res: Response) => {
    res.json({ status: "ok", service: "better-auth", database: dependencies.databaseDialect });
  });

  app.get("/api/auth/config", (_req: Request, res: Response) => {
    const siteKey = process.env.TURNSTILE_SITE_KEY?.trim() ?? "";
    const enabled = Boolean(siteKey && process.env.TURNSTILE_SECRET_KEY?.trim());
    res.json({ turnstile: { enabled, siteKey: enabled ? siteKey : null } });
  });

  app.post("/api/auth/check-email", express.json(), async (req: Request, res: Response) => {
    const email = typeof req.body?.email === "string" ? req.body.email.trim().toLowerCase() : "";
    if (!email || !email.includes("@")) {
      res.status(400).json({ exists: false });
      return;
    }

    try {
      res.json({ exists: await dependencies.emailExists(email) });
    } catch {
      res.status(503).json({ exists: false, error: "auth_database_unavailable" });
    }
  });

  app.get("/api/auth/debug-session", async (req: Request, res: Response) => {
    res.json(await dependencies.getSession(fromNodeHeaders(req.headers)));
  });

  app.all("/api/auth/*", dependencies.authHandler);
  app.use(express.json());
  return app;
}
