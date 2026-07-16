import cors from "cors";
import express, { type Request, type Response } from "express";

const trustedOrigins = [
  process.env.SICURRE_FRONTEND_ORIGIN,
  "http://127.0.0.1:5173",
  "http://localhost:5173",
].filter(Boolean) as string[];

export type AuthServerDependencies = {
  databaseDialect: string;
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

  app.all("/api/auth/*", dependencies.authHandler);
  app.use(express.json());
  return app;
}
