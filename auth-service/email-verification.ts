/** Build the scanner-resistant frontend entry point used in verification emails. */
export function buildEmailVerificationEntryUrl(frontendOrigin: string, token: string): string {
  const entryUrl = new URL("/verify-email", frontendOrigin);
  entryUrl.hash = new URLSearchParams({ token }).toString();
  return entryUrl.toString();
}
