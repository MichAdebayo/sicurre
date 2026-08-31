/**
 * The single allowlist of origins this service trusts.
 *
 * It feeds two separate defences, which is why it lives in one place:
 *
 *   - `server.ts` passes it to `cors({ credentials: true })`, deciding who may
 *     read a response that carries the user's session cookie.
 *   - `auth.ts` passes it to Better Auth, which also uses it for its CSRF
 *     origin check, deciding who may submit state-changing requests.
 *
 * It previously existed as two identical literals, one per file. Correcting
 * only the CORS copy would have changed the response headers and left CSRF
 * still trusting the same origins — a fix that looks like it worked.
 *
 * The development origins are gated on the environment. Shipped ungated, a
 * production deployment trusts a Vite dev server that only exists on a
 * developer's machine: any page the victim loads on their own localhost:5173
 * could read authenticated responses from the live service.
 */

const DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"] as const;

export function isProductionEnvironment(
  environment: string | undefined = process.env.SICURRE_ENVIRONMENT,
): boolean {
  return (environment ?? "development").trim().toLowerCase() === "production";
}

export function buildTrustedOrigins(options?: {
  configuredOrigin?: string;
  isProduction?: boolean;
}): string[] {
  const configuredOrigin =
    options?.configuredOrigin ?? process.env.SICURRE_FRONTEND_ORIGIN;
  const production = options?.isProduction ?? isProductionEnvironment();

  return [
    configuredOrigin,
    ...(production ? [] : DEV_ORIGINS),
  ].filter(Boolean) as string[];
}
