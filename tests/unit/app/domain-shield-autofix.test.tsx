// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DomainShieldRoute from "../../../src/app/routes/domain-shield";

const shield = vi.hoisted(() => ({
  status: {} as Record<string, unknown>,
}));

const healthy = () => ({
  spf: { valid: true, record: "v=spf1 include:_spf.mx.cloudflare.net ~all", error: null },
  dkim: { valid: true, record: "v=DKIM1; p=key", error: null },
  dmarc: {
    valid: true,
    record: "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com",
    policy: "reject",
    reporting_enabled: true,
    error: null,
  },
  ssl: { valid: true, days_remaining: 30, auto_renew: true, error: null },
  reputation_score: 100,
  score_grade: "A",
  blacklists: { listed: false, matched: [], error: null },
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
  motion: { div: "div" },
}));

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({
    domains: [{ id: "domain-1", zone_name: "vinse.app", status: "active" }],
    activeDomain: "vinse.app",
    isLoading: false,
  }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useCloudflareStatus: () => ({ refetch: vi.fn() }),
  useDmarcReportSummary: () => ({
    data: { report_count: 0, total_messages: 0, aligned_messages: 0, failed_messages: 0, top_sources: [] },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useDomainShieldStatus: () => ({ data: shield.status, isLoading: false, error: null }),
  useImportDmarcReport: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useRefreshDomainShieldStatus: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useSetupCloudflare: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useWorkspaceCloudflareToken: () => ({ data: { configured: true } }),
}));

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.clearAllMocks();
});

describe("Domain Shield auto-configuration", () => {
  it("shows the green state and no checkbox when nothing needs work", () => {
    shield.status = healthy();
    render(<DomainShieldRoute />);
    expect(screen.getByText("domain_shield.autofix_complete")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText("domain_shield.row_spf")).not.toBeInTheDocument();
  });

  it("lists SPF with a checkbox when the record is missing", () => {
    shield.status = { ...healthy(), spf: { valid: false, record: null, error: null } };
    render(<DomainShieldRoute />);
    expect(screen.queryByText("domain_shield.autofix_complete")).not.toBeInTheDocument();
    expect(screen.getByText("domain_shield.row_spf")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.queryByText("domain_shield.row_dmarc")).not.toBeInTheDocument();
  });

  it("treats a monitor-only DMARC policy as work to do, matching the score", () => {
    shield.status = {
      ...healthy(),
      dmarc: {
        valid: true,
        record: "v=DMARC1; p=none; rua=mailto:dmarc@sicurre.com",
        policy: "none",
        reporting_enabled: true,
        error: null,
      },
    };
    render(<DomainShieldRoute />);
    expect(screen.queryByText("domain_shield.autofix_complete")).not.toBeInTheDocument();
    expect(screen.getByText("domain_shield.row_dmarc")).toBeInTheDocument();
    // The step card above and the auto-fix row both name the partial state.
    expect(screen.getAllByText("domain_shield.status_partial").length).toBeGreaterThanOrEqual(2);
  });

  it("names a missing Sicurre reporting address on the DMARC row", () => {
    shield.status = {
      ...healthy(),
      dmarc: { valid: true, record: "v=DMARC1; p=reject", policy: "reject", reporting_enabled: false, error: null },
    };
    render(<DomainShieldRoute />);
    expect(screen.getByText("domain_shield.reporting_missing")).toBeInTheDocument();
  });

  it("lists DKIM as provider-managed and never offers to fix it", () => {
    shield.status = { ...healthy(), dkim: { valid: false, record: null, error: null } };
    render(<DomainShieldRoute />);
    expect(screen.getByText("domain_shield.dkim_provider_managed")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
