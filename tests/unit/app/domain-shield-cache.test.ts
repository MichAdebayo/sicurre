import { describe, expect, it } from "vitest";

import { isReusableDomainShieldStatus } from "../../../src/app/lib/domain-shield-cache";

function status(error: string | null) {
  return {
    spf: { valid: true, record: "v=spf1 -all", error: null },
    dkim: { valid: true, record: "v=DKIM1", error: null },
    dmarc: {
      valid: true,
      record: "v=DMARC1; p=reject",
      policy: "reject",
      error: null,
    },
    ssl: { valid: true, days_remaining: 30, auto_renew: true, error: null },
    reputation_score: 100,
    score_grade: "A",
    blacklists: { listed: false, matched: [], error },
  };
}

describe("Domain Shield cache", () => {
  it("reuses a complete last-known status", () => {
    expect(isReusableDomainShieldStatus(status(null))).toBe(true);
  });

  it("refreshes instead of replaying a transient reputation error", () => {
    expect(isReusableDomainShieldStatus(status("provider unavailable"))).toBe(false);
  });
});
