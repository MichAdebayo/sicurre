/** Resolve the browser-facing origin independently from the local auth sidecar. */
export function resolveFrontendOrigin(options: {
  configuredOrigin?: string;
  authBaseUrl: string;
  isProduction: boolean;
}): string {
  const configured = options.configuredOrigin?.trim();
  return new URL(configured || (options.isProduction
    ? options.authBaseUrl
    : "http://127.0.0.1:5173")).origin;
}

/** Keep the token in the fragment until the frontend starts verification. */
export function buildEmailVerificationEntryUrl(frontendOrigin: string, token: string): string {
  const entryUrl = new URL("/verify-email", frontendOrigin);
  entryUrl.hash = new URLSearchParams({ token }).toString();
  return entryUrl.toString();
}
