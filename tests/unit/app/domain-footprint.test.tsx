// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DomainFootprint, DomainFootprintSection, describeDomainFootprint } from "../../../src/app/components/settings/domain-footprint";
import type { DomainShieldStatus } from "../../../src/app/lib/api";

const shield = vi.hoisted(() => ({ data: undefined as unknown, isLoading: false }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useDomainShieldStatus: () => ({ data: shield.data, isLoading: shield.isLoading }),
}));

const t = (key: string) => key;

const status = (overrides: Partial<DomainShieldStatus> = {}): DomainShieldStatus => ({
  spf: { valid: true, record: "v=spf1 include:_spf.mx.cloudflare.net ~all", error: null },
  dkim: { valid: true, record: "v=DKIM1; p=key", error: null },
  dmarc: {
    valid: true,
    record: "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com",
    policy: "reject",
    reporting_enabled: true,
    error: null,
  },
  ssl: { valid: true, days_remaining: 42, auto_renew: true, error: null },
  reputation_score: 100,
  score_grade: "A",
  blacklists: { listed: false, matched: [], error: null },
  ...overrides,
});

afterEach(() => {
  cleanup();
  shield.data = undefined;
  shield.isLoading = false;
});

describe("describeDomainFootprint", () => {
  it("separates what Sicurre writes from what it only reads", () => {
    const { writes, reads } = describeDomainFootprint(status(), t);
    expect(writes.map((fact) => fact.key)).toEqual(["spf", "dmarc-reporting", "dmarc-policy"]);
    expect(reads.map((fact) => fact.key)).toEqual(["dkim", "certificate"]);
    expect(writes.every((fact) => fact.tone === "ok")).toBe(true);
    expect(reads.every((fact) => fact.tone === "neutral")).toBe(true);
  });

  it("marks a monitor-only policy and a missing reporting address as still to do", () => {
    const { writes } = describeDomainFootprint(
      status({ dmarc: { valid: true, record: "v=DMARC1; p=none", policy: "none", reporting_enabled: false, error: null } }),
      t,
    );
    const byKey = Object.fromEntries(writes.map((fact) => [fact.key, fact]));
    expect(byKey["dmarc-policy"].status).toBe("settings.footprint_monitor_only");
    expect(byKey["dmarc-policy"].tone).toBe("todo");
    expect(byKey["dmarc-reporting"].tone).toBe("todo");
  });

  it("recognises the reporting address from the record when the flag is absent", () => {
    const { writes } = describeDomainFootprint(
      status({ dmarc: { valid: true, record: "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com", policy: "reject", error: null } }),
      t,
    );
    expect(writes.find((fact) => fact.key === "dmarc-reporting")?.tone).toBe("ok");
  });

  it("reports DKIM and the certificate as read-only facts, never as tasks", () => {
    const { reads } = describeDomainFootprint(
      status({ dkim: { valid: false, record: null, error: null }, ssl: { valid: false, days_remaining: 0, auto_renew: false, error: "x" } }),
      t,
    );
    expect(reads.map((fact) => fact.status)).toEqual(["settings.footprint_absent", "settings.footprint_not_inspected"]);
    expect(reads.every((fact) => fact.tone === "neutral")).toBe(true);
  });
});

describe("DomainFootprint", () => {
  it("renders both lists for a domain, named by its heading", () => {
    shield.data = status();
    render(<DomainFootprint domain="vinse.app" />);
    expect(screen.getByRole("heading", { level: 3, name: "vinse.app" })).toBeInTheDocument();
    expect(screen.getByText("settings.footprint_writes")).toBeInTheDocument();
    expect(screen.getByText("settings.footprint_reads")).toBeInTheDocument();
    expect(screen.getAllByText("settings.footprint_in_place")).toHaveLength(3);
  });

  it("says it is reading while the status loads, and says so when it cannot", () => {
    shield.isLoading = true;
    const { unmount } = render(<DomainFootprint domain="vinse.app" />);
    expect(screen.getByRole("status")).toHaveTextContent("settings.footprint_loading");
    unmount();
    shield.isLoading = false;
    render(<DomainFootprint domain="vinse.app" />);
    expect(screen.getByText("settings.footprint_unavailable")).toBeInTheDocument();
  });
});

describe("DomainFootprintSection", () => {
  it("is always shown once a domain is connected, one card per domain, with the intro and the note", () => {
    shield.data = status();
    render(
      <DomainFootprintSection
        domains={[
          { id: "1", zone_name: "vinse.app", status: "active" },
          { id: "2", zone_name: "sicurre.com", status: "pending_verification" },
        ]}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "settings.footprint_title" })).toBeInTheDocument();
    expect(screen.getByText("settings.footprint_intro")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["vinse.app", "sicurre.com"]);
    expect(screen.getByText("settings.footprint_disconnect_note")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders nothing when no domain is connected", () => {
    const { container } = render(<DomainFootprintSection domains={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
