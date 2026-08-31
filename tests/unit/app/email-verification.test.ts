import { describe, expect, it } from "vitest";

import { buildEmailVerificationEntryUrl, resolveFrontendOrigin } from "../../../auth-service/email-verification";
import {
  buildVerificationRequestUrl,
  parseVerificationCallback,
} from "../../../src/app/lib/email-verification";

describe("email verification contract", () => {
  it.each([undefined, "", "  "])("uses the local frontend when its origin is unset (%s)", (configuredOrigin) => {
    const origin = resolveFrontendOrigin({ configuredOrigin, authBaseUrl: "http://127.0.0.1:3005", isProduction: false });
    expect(buildEmailVerificationEntryUrl(origin, "test-token")).toBe("http://127.0.0.1:5173/verify-email#token=test-token");
  });

  it("uses the production public origin without falling back to localhost", () => {
    expect(resolveFrontendOrigin({ authBaseUrl: "https://sicurre.com/api/auth", isProduction: true })).toBe("https://sicurre.com");
  });

  it.each([false, true])("honors the configured frontend origin (production=%s)", (isProduction) => {
    expect(resolveFrontendOrigin({ configuredOrigin: " https://preview.sicurre.com/ ", authBaseUrl: "http://127.0.0.1:3005", isProduction })).toBe("https://preview.sicurre.com");
  });
  it("keeps the emailed token out of the initial HTTP request", () => {
    const url = new URL(buildEmailVerificationEntryUrl("https://sicurre.com", "one time/token"));

    expect(url.pathname).toBe("/verify-email");
    expect(url.search).toBe("");
    expect(new URLSearchParams(url.hash.slice(1)).get("token")).toBe("one time/token");
  });

  it("does not report a callback error as successful verification", () => {
    expect(parseVerificationCallback("?verified=1&error=TOKEN_EXPIRED")).toEqual({
      status: "error",
      reason: "expired",
    });
    expect(parseVerificationCallback("?verified=1&error=INVALID_TOKEN")).toEqual({
      status: "error",
      reason: "invalid",
    });
    expect(parseVerificationCallback("?verified=1")).toEqual({ status: "verified" });
  });

  it("targets Better Auth for automatic verification and returns to sign-in", () => {
    const url = new URL(buildVerificationRequestUrl(
      "token-value",
      "https://sicurre.com",
      "https://sicurre.com/api/auth",
    ));

    expect(url.pathname).toBe("/api/auth/verify-email");
    expect(url.searchParams.get("token")).toBe("token-value");
    expect(url.searchParams.get("callbackURL")).toBe("https://sicurre.com/login?verified=1");
  });
});
