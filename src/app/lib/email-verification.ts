export type VerificationCallback =
  | { status: "none" }
  | { status: "verified" }
  | { status: "error"; reason: "expired" | "invalid" };

/** Interpret Better Auth's verification redirect without masking an error as success. */
export function parseVerificationCallback(search: string): VerificationCallback {
  const params = new URLSearchParams(search);
  const error = params.get("error");
  if (error) {
    return {
      status: "error",
      reason: error === "TOKEN_EXPIRED" ? "expired" : "invalid",
    };
  }
  return params.get("verified") === "1" ? { status: "verified" } : { status: "none" };
}

/** Build the verification request with a sign-in callback for success or errors. */
export function buildVerificationRequestUrl(
  token: string,
  origin: string,
  authBaseUrl: string,
): string {
  const url = new URL(`${authBaseUrl.replace(/\/$/, "")}/verify-email`, origin);
  url.searchParams.set("token", token);
  url.searchParams.set("callbackURL", `${origin}/login?verified=1`);
  return url.toString();
}

/** Exchange the emailed token through Better Auth without a second confirmation. */
export function verifyEmailFromLink(token: string, origin: string, authBaseUrl: string): void {
  window.location.replace(buildVerificationRequestUrl(token, origin, authBaseUrl));
}
