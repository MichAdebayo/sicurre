// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DomainShieldRoute from "../../../src/app/routes/domain-shield";

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
    data: {
      report_count: 0,
      total_messages: 0,
      aligned_messages: 0,
      failed_messages: 0,
      top_sources: [],
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useDomainShieldStatus: () => ({
    data: {
      spf: { valid: true, record: "v=spf1 -all", error: null },
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
    },
    isLoading: false,
    error: null,
  }),
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

describe("Domain Shield layout", () => {
  it("removes the programmatic DMARC file input from document layout", () => {
    const { container } = render(<DomainShieldRoute />);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');

    expect(input).toHaveClass("hidden");
    expect(input).not.toHaveClass("sr-only");
  });
});
