import { describe, expect, it } from "vitest";

import { countTrendVerdicts } from "../../../src/app/lib/dashboard-trends";

describe("dashboard trend classification", () => {
  it("keeps spam separate from phishing and groups quarantine with blocked threats", () => {
    expect(
      countTrendVerdicts([
        { verdict: "legitimate" },
        { verdict: "spam" },
        { verdict: "spam" },
        { verdict: "phishing" },
        { verdict: "quarantine" },
      ]),
    ).toEqual({ legitimate: 1, spam: 2, phishing: 2 });
  });
});
