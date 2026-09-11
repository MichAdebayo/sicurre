/**
 * Showing the plan and provisioning in the same click is not consent.
 *
 * The first version of this change rendered the preview and then continued
 * straight into setup inside one handler. The panel appeared at the moment the
 * write began, so the customer could never untick a record before it was
 * written — exactly the failure the preview exists to remove, reproduced with
 * extra steps.
 *
 * Verifying and provisioning are separate clicks. These tests read the source
 * because the failure is structural: it is about which handler calls what, not
 * about a value on screen.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const source = readFileSync(
  join(process.cwd(), "src/app/components/common/cloudflare-integrator.tsx"),
  "utf8",
);

/** The body of one function declaration, up to the next top-level const. */
function handlerBody(name: string): string {
  const start = source.indexOf(`const ${name} = async () => {`);
  expect(start, `${name} not found`).toBeGreaterThan(-1);
  const rest = source.slice(start + 1);
  const end = rest.indexOf("\n  const ");
  return end === -1 ? rest : rest.slice(0, end);
}

describe("connect consent", () => {
  it("verifying never provisions", () => {
    const verify = handlerBody("handleVerify");
    expect(verify).toContain("verifyMutation");
    expect(verify).not.toContain("setupMutation");
  });

  it("provisioning carries the customer's choices, not defaults", () => {
    const integrate = handlerBody("handleIntegrate");
    expect(integrate).toContain("setupMutation");
    expect(integrate).toContain("fix_spf: applySpf");
    expect(integrate).toContain("fix_dmarc: applyDmarc");
  });

  it("the button only offers to connect once a plan has been read", () => {
    expect(source).toContain("onClick={dnsPlan ? handleIntegrate : handleVerify}");
  });

  it("editing the token or the domain drops the plan", () => {
    // A plan describes one token against one zone. Carrying it across an edit
    // would collect consent for records the customer never saw.
    const edits = source.match(/onChange=\{e => \{[^}]*setDnsPlan\(null\)/g) ?? [];
    expect(edits.length).toBe(2);
  });
});
