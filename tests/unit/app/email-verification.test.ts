import { describe, expect, it } from "vitest";

import { buildEmailVerificationEntryUrl } from "../../../auth-service/email-verification";
import {
  buildVerificationRequestUrl,
  parseVerificationCallback,
} from "../../../src/app/lib/email-verification";

describe("email verification contract", () => {
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

  it("targets Better Auth only after confirmation and returns to sign-in", () => {
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
