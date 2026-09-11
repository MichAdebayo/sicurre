/**
 * The permission keys are slugs Cloudflare does not publish.
 *
 * They are not the UUIDs the permission-groups API returns, and an unrecognised
 * key is ignored **silently** — no error, the row simply never appears in the
 * form. A customer then creates a token missing a permission and provisioning
 * dies several steps later, which is the exact failure the pre-filled link
 * exists to prevent.
 *
 * Every key below was confirmed by opening the generated link and counting the
 * rows Cloudflare pre-selected: five of five. `email_routing_rules` and
 * `email_routing_addresses` — the plural forms — were tried first and loaded
 * three of five. Changing any of these without re-testing the real link puts
 * that failure back.
 */
import { describe, expect, it } from "vitest";

import {
  SICURRE_TOKEN_PERMISSIONS,
  cloudflareTokenTemplateUrl,
} from "../../../src/app/lib/cloudflare-token-template";

/** Confirmed against Cloudflare's form, not inferred from a naming pattern. */
const VERIFIED_KEYS = [
  "dns",
  "zone_settings",
  "email_routing_rule",
  "email_routing_address",
  "workers_scripts",
];

describe("Cloudflare token template", () => {
  it("asks for exactly the keys that were verified", () => {
    expect(SICURRE_TOKEN_PERMISSIONS.map((p) => p.key).sort()).toEqual(
      [...VERIFIED_KEYS].sort(),
    );
  });

  it("uses the singular email routing keys", () => {
    const keys = SICURRE_TOKEN_PERMISSIONS.map((p) => p.key);
    expect(keys).toContain("email_routing_rule");
    expect(keys).toContain("email_routing_address");
    expect(keys).not.toContain("email_routing_rules");
    expect(keys).not.toContain("email_routing_addresses");
  });

  it("covers every endpoint the provisioner calls", () => {
    // Zone: dns_records, email/routing/dns (zone settings), email/routing/rules.
    // Account: email/routing/addresses, workers/scripts.
    expect(SICURRE_TOKEN_PERMISSIONS.filter((p) => p.scope === "Zone")).toHaveLength(3);
    expect(SICURRE_TOKEN_PERMISSIONS.filter((p) => p.scope === "Account")).toHaveLength(2);
  });

  it("encodes the permissions the way Cloudflare parses them", () => {
    const url = new URL(cloudflareTokenTemplateUrl("sicurre.com"));
    expect(url.origin + url.pathname).toBe("https://dash.cloudflare.com/profile/api-tokens");

    const parsed = JSON.parse(url.searchParams.get("permissionGroupKeys") ?? "[]");
    expect(parsed).toHaveLength(5);
    for (const entry of parsed) {
      expect(Object.keys(entry).sort()).toEqual(["key", "type"]);
      expect(entry.type).toBe("edit");
    }
  });

  it("names the token after the domain being connected", () => {
    const url = new URL(cloudflareTokenTemplateUrl("sicurre.com"));
    expect(url.searchParams.get("name")).toBe("Sicurre - sicurre.com");
  });

  it("still builds a usable link before a domain is typed", () => {
    const url = new URL(cloudflareTokenTemplateUrl());
    expect(url.searchParams.get("name")).toBe("Sicurre");
    expect(JSON.parse(url.searchParams.get("permissionGroupKeys") ?? "[]")).toHaveLength(5);
  });

  it("every permission is shown to the customer, not just requested", () => {
    // This grants write access to someone's DNS. Hiding what is granted behind
    // a one-click button would be worse than the dropdown it replaces.
    for (const p of SICURRE_TOKEN_PERMISSIONS) {
      expect(p.label.length).toBeGreaterThan(0);
      expect(["Zone", "Account"]).toContain(p.scope);
    }
  });
});
