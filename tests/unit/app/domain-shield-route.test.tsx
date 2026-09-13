// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DomainShieldRoute from "../../../src/app/routes/domain-shield";

const state = vi.hoisted(() => ({
  domains: [{ id: "domain-1", zone_name: "vinse.app", status: "active" }] as unknown[],
  activeDomain: "vinse.app",
  domainsLoading: false,
  shield: { data: undefined as unknown, isLoading: false, error: null as unknown },
  reports: { data: undefined as unknown, isLoading: false, isError: false, refetch: vi.fn() },
  cloudflareRefetch: vi.fn(),
  importReport: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  refreshShield: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  setup: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  tokenConfigured: true,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (!options) return key;
      const detail = ["count", "days", "feeds"].find((name) => name in options);
      return detail ? `${key}:${options[detail]}` : key;
    },
  }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
  motion: { div: "div", span: "span" },
}));

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({
    domains: state.domains,
    activeDomain: state.activeDomain,
    isLoading: state.domainsLoading,
  }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useCloudflareStatus: () => ({ refetch: state.cloudflareRefetch }),
  useDmarcReportSummary: () => state.reports,
  useDomainShieldStatus: () => state.shield,
  useImportDmarcReport: () => state.importReport,
  useRefreshDomainShieldStatus: () => state.refreshShield,
  useSetupCloudflare: () => state.setup,
  useWorkspaceCloudflareToken: () => ({ data: { configured: state.tokenConfigured } }),
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

const emptyReports = () => ({
  report_count: 0,
  total_messages: 0,
  aligned_messages: 0,
  failed_messages: 0,
  top_sources: [],
});

const spfMissing = () => ({ ...healthy(), spf: { valid: false, record: null, error: null } });

// Pretend the audit already ran this session so the cards show their verdicts
// at once and the auto-fix button is not waiting on the terminal animation.
const markDiagnosed = () => sessionStorage.setItem("diagnosed_vinse.app", "true");

const headerRefreshButton = () =>
  within(screen.getByText("vinse.app").parentElement as HTMLElement).getByRole("button");

// The active record and the recommendation can read the same; only the
// recommendation sits next to a copy button.
const copyButtonNextTo = (recordText: string) => {
  const parents = screen.getAllByText(recordText).map((node) => node.parentElement as HTMLElement);
  const withButton = parents.find((parent) => within(parent).queryByRole("button"));
  return within(withButton as HTMLElement).getByRole("button");
};

const fileInput = (container: HTMLElement) =>
  container.querySelector<HTMLInputElement>('input[type="file"]') as HTMLInputElement;

const flushPromises = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

beforeEach(() => {
  state.domains = [{ id: "domain-1", zone_name: "vinse.app", status: "active" }];
  state.activeDomain = "vinse.app";
  state.domainsLoading = false;
  state.shield = { data: healthy(), isLoading: false, error: null };
  state.reports = { data: emptyReports(), isLoading: false, isError: false, refetch: vi.fn() };
  state.cloudflareRefetch = vi.fn();
  state.importReport = { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() };
  state.refreshShield = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false, reset: vi.fn() };
  state.setup = { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() };
  state.tokenConfigured = true;
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Domain Shield loading and error states", () => {
  it("shows the skeleton while the status loads for the first time", () => {
    state.shield = { data: undefined, isLoading: true, error: null };
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.title")).toBeInTheDocument();
    expect(screen.queryByText("domain_shield.integrity_title")).not.toBeInTheDocument();
    expect(screen.queryByText("domain_shield.fetch_failed")).not.toBeInTheDocument();
    expect(headerRefreshButton()).toBeDisabled();
  });

  it("names the failure when the status cannot be fetched", () => {
    state.shield = { data: undefined, isLoading: false, error: new Error("500") };
    render(<DomainShieldRoute />);

    expect(screen.getByText("common.error_occurred")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.fetch_failed")).toBeInTheDocument();
  });

  it("asks for a domain when none is active and says so when none is connected", () => {
    state.activeDomain = "";
    state.domains = [];
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.no_domains")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.no_active_shield")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.no_active_shield_desc")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows a placeholder while the domain list loads", () => {
    state.domainsLoading = true;
    state.activeDomain = "";
    render(<DomainShieldRoute />);

    expect(screen.queryByText("domain_shield.no_domains")).not.toBeInTheDocument();
    expect(screen.queryByText("vinse.app")).not.toBeInTheDocument();
  });
});

describe("Domain Shield audit cards", () => {
  it("steps through the five checks one second apart and remembers the run", () => {
    vi.useFakeTimers();
    render(<DomainShieldRoute />);

    expect(screen.getAllByText("domain_shield.analyzing")).toHaveLength(1);
    expect(screen.getAllByText("domain_shield.pending")).toHaveLength(4);
    expect(screen.getByRole("button", { name: "domain_shield.rerun_audit" })).toBeDisabled();

    act(() => { vi.advanceTimersByTime(2000); });
    expect(screen.getAllByText("domain_shield.status_conform").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("domain_shield.pending")).toHaveLength(2);

    act(() => { vi.advanceTimersByTime(3000); });
    expect(screen.queryByText("domain_shield.analyzing")).not.toBeInTheDocument();
    expect(screen.queryByText("domain_shield.pending")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("diagnosed_vinse.app")).toBe("true");
    expect(screen.getByRole("button", { name: "domain_shield.rerun_audit" })).toBeEnabled();
  });

  it("shows the verdicts at once when the audit already ran this session", () => {
    markDiagnosed();
    state.shield = {
      data: {
        ...spfMissing(),
        dmarc: { valid: true, record: "v=DMARC1; p=none; rua=mailto:dmarc@sicurre.com", policy: "none", reporting_enabled: true, error: null },
        blacklists: { listed: false, matched: [], error: "timeout" },
      },
      isLoading: false,
      error: null,
    };
    render(<DomainShieldRoute />);

    expect(screen.queryByText("domain_shield.analyzing")).not.toBeInTheDocument();
    expect(screen.getByText("domain_shield.not_verified")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.dmarc_open_items:1")).toBeInTheDocument();
    expect(screen.getAllByText("domain_shield.status_missing").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("domain_shield.status_partial").length).toBeGreaterThanOrEqual(1);
  });

  it("reruns the audit on demand and forgets the previous run", () => {
    markDiagnosed();
    render(<DomainShieldRoute />);

    fireEvent.click(screen.getByRole("button", { name: "domain_shield.rerun_audit" }));
    expect(sessionStorage.getItem("diagnosed_vinse.app")).toBeNull();
    expect(screen.getByText("domain_shield.analyzing")).toBeInTheDocument();
  });
});

describe("Domain Shield refresh action", () => {
  it("refreshes the status and restarts the audit", async () => {
    markDiagnosed();
    render(<DomainShieldRoute />);

    fireEvent.click(headerRefreshButton());
    await waitFor(() => expect(state.refreshShield.mutateAsync).toHaveBeenCalledWith("vinse.app"));
    await waitFor(() => expect(screen.getByText("domain_shield.analyzing")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("surfaces the refresh error, using the message when there is one", async () => {
    markDiagnosed();
    state.refreshShield.mutateAsync.mockRejectedValueOnce(new Error("Cloudflare is down"));
    render(<DomainShieldRoute />);

    fireEvent.click(headerRefreshButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Cloudflare is down");

    fireEvent.click(screen.getByRole("button", { name: "Fermer la notification" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());

    state.refreshShield.mutateAsync.mockRejectedValueOnce("nope");
    fireEvent.click(headerRefreshButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("domain_shield.refresh_failed");
  });
});

describe("Domain Shield auto-configuration", () => {
  it("explains the records and lets the customer untick a fix before running it", async () => {
    markDiagnosed();
    state.shield = {
      data: { ...spfMissing(), dmarc: { valid: false, record: null, policy: undefined, reporting_enabled: false, error: null } },
      isLoading: false,
      error: null,
    };
    state.setup.mutateAsync.mockResolvedValue({ status: "active" });
    render(<DomainShieldRoute session={{ email: "owner@vinse.app" } as never} />);

    expect(screen.getByRole("tooltip", { name: "domain_shield.dns_records_help" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "common.help", description: "domain_shield.dns_records_help" })).toBeInTheDocument();

    const [spfBox, dmarcBox] = screen.getAllByRole("checkbox");
    expect(spfBox).toBeChecked();
    expect(dmarcBox).toBeChecked();
    fireEvent.click(spfBox);
    fireEvent.click(dmarcBox);
    expect(spfBox).not.toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    await waitFor(() => expect(state.setup.mutateAsync).toHaveBeenCalledWith({
      zone_name: "vinse.app",
      destination_email: "owner@vinse.app",
      fix_spf: false,
      fix_dmarc: false,
    }));
    expect(await screen.findByRole("status")).toHaveTextContent("domain_shield.setup_applied");
    expect(screen.getByRole("button", { name: /domain_shield.autofix_applied/ })).toBeDisabled();
    expect(state.refreshShield.mutateAsync).toHaveBeenCalledWith("vinse.app");
  });

  it("falls back to the owner address and shows the writing state while the call runs", async () => {
    markDiagnosed();
    state.shield = { data: spfMissing(), isLoading: false, error: null };
    let finish: (value: unknown) => void = () => {};
    state.setup.mutateAsync.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<DomainShieldRoute />);

    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    expect(await screen.findByRole("button", { name: /domain_shield.autofix_writing_dns/ })).toBeDisabled();
    expect(state.setup.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ destination_email: "owner@sicurre.com" }));

    await act(async () => { finish({ status: "pending_verification" }); });
    expect(await screen.findByRole("status")).toHaveTextContent("domain_shield.setup_applied");
  });

  it("polls Cloudflare while provisioning and applies the result once active", async () => {
    vi.useFakeTimers();
    markDiagnosed();
    state.shield = { data: spfMissing(), isLoading: false, error: null };
    state.setup.mutateAsync.mockResolvedValue({ status: "provisioning" });
    state.cloudflareRefetch
      .mockResolvedValueOnce({ data: { status: "provisioning" } })
      .mockResolvedValueOnce({ data: { status: "active" } });
    render(<DomainShieldRoute />);

    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    await flushPromises();
    expect(screen.getByRole("status")).toHaveTextContent("domain_shield.setup_started");
    expect(screen.getByRole("button", { name: /domain_shield.autofix_routing/ })).toBeDisabled();

    await act(async () => { vi.advanceTimersByTime(2000); });
    await flushPromises();
    expect(state.cloudflareRefetch).toHaveBeenCalledTimes(1);

    await act(async () => { vi.advanceTimersByTime(2000); });
    await flushPromises();
    expect(state.cloudflareRefetch).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status")).toHaveTextContent("domain_shield.setup_applied");
    expect(state.refreshShield.mutateAsync).toHaveBeenCalledWith("vinse.app");
  });

  it("stops polling on a provisioning error and names the Cloudflare message", async () => {
    vi.useFakeTimers();
    markDiagnosed();
    state.shield = { data: spfMissing(), isLoading: false, error: null };
    state.setup.mutateAsync.mockResolvedValue({ status: "provisioning" });
    state.cloudflareRefetch.mockResolvedValue({ data: { status: "error", error_message: "Worker quota exceeded" } });
    render(<DomainShieldRoute />);

    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    await flushPromises();
    await act(async () => { vi.advanceTimersByTime(2000); });
    await flushPromises();

    expect(screen.getByRole("alert")).toHaveTextContent("Worker quota exceeded");
    expect(screen.getByRole("button", { name: /domain_shield.autofix_failed/ })).toBeDisabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("gives up waiting after fifteen polls and says the setup is still running", async () => {
    vi.useFakeTimers();
    markDiagnosed();
    state.shield = { data: spfMissing(), isLoading: false, error: null };
    state.setup.mutateAsync.mockResolvedValue({ status: "provisioning" });
    state.cloudflareRefetch.mockResolvedValue({ data: { status: "provisioning" } });
    render(<DomainShieldRoute />);

    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    await flushPromises();
    let polls = 0;
    while (polls < 15) {
      await act(async () => { vi.advanceTimersByTime(2000); });
      await flushPromises();
      polls += 1;
    }

    expect(state.cloudflareRefetch).toHaveBeenCalledTimes(15);
    expect(screen.getByRole("status")).toHaveTextContent("domain_shield.setup_in_progress");
    expect(screen.getByRole("button", { name: /domain_shield.autofix_routing/ })).toBeDisabled();
  });

  it("translates a permission failure and passes any other message through", async () => {
    markDiagnosed();
    state.shield = { data: spfMissing(), isLoading: false, error: null };
    state.setup.mutateAsync.mockRejectedValueOnce(new Error("Authentication error (10000)"));
    render(<DomainShieldRoute />);

    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("domain_shield.cloudflare_dns_permission_error");
    expect(screen.getByRole("button", { name: /domain_shield.autofix_failed/ })).toBeDisabled();

    // Closing the toast rearms the button.
    fireEvent.click(screen.getByRole("button", { name: "Fermer la notification" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /domain_shield.autofix_launch/ })).toBeEnabled());

    state.setup.mutateAsync.mockRejectedValueOnce(new Error("Zone is read only"));
    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Zone is read only");

    fireEvent.click(screen.getByRole("button", { name: "Fermer la notification" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /domain_shield.autofix_launch/ })).toBeEnabled());

    state.setup.mutateAsync.mockRejectedValueOnce(new Error(""));
    fireEvent.click(screen.getByRole("button", { name: /domain_shield.autofix_launch/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("domain_shield.setup_initialization_failed");
  });

  it("disables the fix and explains why when no Cloudflare token is stored", () => {
    markDiagnosed();
    state.tokenConfigured = false;
    state.shield = { data: spfMissing(), isLoading: false, error: null };
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.cloudflare_required_title")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.cloudflare_required_desc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /domain_shield.autofix_launch/ })).toBeDisabled();
  });

  it("offers nothing to run once everything is in place", () => {
    markDiagnosed();
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.autofix_complete")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /domain_shield.autofix_launch/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tooltip", { name: "domain_shield.dns_records_help" })).not.toBeInTheDocument();
  });
});

describe("Domain Shield monitoring rows", () => {
  it("shows the SSL countdown, a clean blocklist and the report counters", () => {
    markDiagnosed();
    state.reports.data = { ...emptyReports(), report_count: 2, total_messages: 40, aligned_messages: 37, failed_messages: 3, top_sources: [
      { source_ip: "203.0.113.9", message_count: 3, dkim_result: "fail", spf_result: "fail" },
    ] };
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.ssl_countdown:30")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.blacklist_clean")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.failed_count:3")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.report_count_received:2")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.reports_received")).toBeInTheDocument();
    expect(screen.getByText("203.0.113.9")).toBeInTheDocument();
    expect(screen.getByText("3 · DKIM fail · SPF fail")).toBeInTheDocument();
    expect(screen.getByRole("tooltip", { name: "domain_shield.report_failed_hint" })).toBeInTheDocument();
    expect(screen.getAllByRole("tooltip")).toHaveLength(5);
  });

  it("flags a listed domain with its feeds and an expired certificate", () => {
    markDiagnosed();
    state.shield = {
      data: {
        ...healthy(),
        ssl: { valid: false, days_remaining: 0, auto_renew: false, error: "expired" },
        blacklists: { listed: true, matched: ["spamhaus", "surbl"], error: null },
      },
      isLoading: false,
      error: null,
    };
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.unresolved")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.listed")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.matched_feeds:spamhaus, surbl")).toBeInTheDocument();
  });

  it("says when the blocklist check itself was unavailable", () => {
    markDiagnosed();
    state.shield = { data: { ...healthy(), blacklists: { listed: false, matched: [], error: "timeout" } }, isLoading: false, error: null };
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.reputation_unavailable")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.reputation_unavailable_desc")).toBeInTheDocument();
  });
});

describe("Domain Shield DNS records", () => {
  it("copies each recommended record to the clipboard and drops the tick after two seconds", () => {
    vi.useFakeTimers();
    markDiagnosed();
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<DomainShieldRoute />);

    fireEvent.click(copyButtonNextTo("v=spf1 include:spf.cloudflare.com include:sicurre.com ~all"));
    expect(writeText).toHaveBeenLastCalledWith("v=spf1 include:spf.cloudflare.com include:sicurre.com ~all");
    fireEvent.click(copyButtonNextTo("v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1+z7s..."));
    expect(writeText).toHaveBeenLastCalledWith("v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1+z7s...");
    fireEvent.click(copyButtonNextTo("v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"));
    expect(writeText).toHaveBeenLastCalledWith("v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com");

    act(() => { vi.advanceTimersByTime(2100); });
    expect(writeText).toHaveBeenCalledTimes(3);
  });

  it("builds the recommended DMARC record from what is already published", () => {
    markDiagnosed();
    const dmarcWith = (record: string | null, policy = "none") =>
      ({ ...healthy(), dmarc: { valid: !!record, record, policy, reporting_enabled: false, error: null } });

    state.shield = { data: dmarcWith(null), isLoading: false, error: null };
    const { rerender } = render(<DomainShieldRoute />);
    expect(screen.getByText("domain_shield.no_dmarc_record")).toBeInTheDocument();
    expect(screen.getByTitle("v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com")).toBeInTheDocument();

    state.shield = { data: dmarcWith("v=DMARC1; p=none; rua=mailto:reports@vinse.app"), isLoading: false, error: null };
    rerender(<DomainShieldRoute />);
    expect(screen.getByTitle("v=DMARC1; p=reject; rua=mailto:reports@vinse.app,mailto:dmarc@sicurre.com")).toBeInTheDocument();

    state.shield = { data: dmarcWith("v=DMARC1; p=quarantine", "quarantine"), isLoading: false, error: null };
    rerender(<DomainShieldRoute />);
    expect(screen.getByTitle("v=DMARC1; p=quarantine; rua=mailto:dmarc@sicurre.com")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.reporting_missing")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.report_missing_desc")).toBeInTheDocument();

    state.shield = { data: dmarcWith("v=DMARC1; p=none;"), isLoading: false, error: null };
    rerender(<DomainShieldRoute />);
    expect(screen.getByTitle("v=DMARC1; p=none; rua=mailto:dmarc@sicurre.com")).toBeInTheDocument();
  });

  it("shows the missing-record placeholders when nothing is published", () => {
    markDiagnosed();
    state.shield = {
      data: { ...spfMissing(), dkim: { valid: false, record: null, error: null } },
      isLoading: false,
      error: null,
    };
    render(<DomainShieldRoute />);

    expect(screen.getByText("domain_shield.no_spf_record")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.no_dkim_record")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.dkim_provider_managed")).toBeInTheDocument();
  });
});

describe("Domain Shield DMARC reports", () => {
  it("opens the file picker from the import button", () => {
    markDiagnosed();
    const { container } = render(<DomainShieldRoute />);
    const click = vi.spyOn(fileInput(container), "click");

    fireEvent.click(screen.getByRole("button", { name: "domain_shield.import_report" }));
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("imports a report and says how many records it held, or that it was already known", async () => {
    markDiagnosed();
    state.importReport.mutateAsync
      .mockResolvedValueOnce({ status: "imported", record_count: 7 })
      .mockResolvedValueOnce({ status: "already_imported", record_count: 0 });
    const { container } = render(<DomainShieldRoute />);
    const input = fileInput(container);
    const report = new File(["<feedback/>"], "report.xml", { type: "application/xml" });

    fireEvent.change(input, { target: { files: [report] } });
    await waitFor(() => expect(state.importReport.mutateAsync).toHaveBeenCalledWith(report));
    expect(await screen.findByRole("status")).toHaveTextContent("domain_shield.report_imported:7");

    fireEvent.change(input, { target: { files: [report] } });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("domain_shield.report_already_imported"));
  });

  it("refuses a report above five megabytes without calling the API", async () => {
    markDiagnosed();
    const { container } = render(<DomainShieldRoute />);
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.xml");

    fireEvent.change(fileInput(container), { target: { files: [big] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("domain_shield.report_too_large");
    expect(state.importReport.mutateAsync).not.toHaveBeenCalled();
  });

  it("ignores an empty selection and names an import failure", async () => {
    markDiagnosed();
    state.importReport.mutateAsync
      .mockRejectedValueOnce(new Error("Malformed XML"))
      .mockRejectedValueOnce("nope");
    const { container } = render(<DomainShieldRoute />);
    const input = fileInput(container);

    fireEvent.change(input, { target: { files: [] } });
    expect(state.importReport.mutateAsync).not.toHaveBeenCalled();

    const report = new File(["<bad"], "bad.xml");
    fireEvent.change(input, { target: { files: [report] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Malformed XML");

    fireEvent.change(input, { target: { files: [report] } });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("domain_shield.report_import_failed"));
  });

  it("shows the pending state on the import button", () => {
    markDiagnosed();
    state.importReport.isPending = true;
    render(<DomainShieldRoute />);
    expect(screen.getByRole("button", { name: "domain_shield.import_report" })).toBeDisabled();
  });

  it("shows a skeleton while the summary loads and a retry when it fails", () => {
    markDiagnosed();
    state.reports = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    const { rerender } = render(<DomainShieldRoute />);
    expect(screen.queryByText("domain_shield.report_count")).not.toBeInTheDocument();
    expect(screen.getByText("domain_shield.no_report_data")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.awaiting_report")).toBeInTheDocument();

    const refetch = vi.fn();
    state.reports = { data: undefined, isLoading: false, isError: true, refetch };
    rerender(<DomainShieldRoute />);
    const failure = screen.getByRole("alert");
    expect(failure).toHaveTextContent("common.load_error");
    fireEvent.click(within(failure).getByRole("button", { name: "common.retry" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("says when no source has reported yet", () => {
    markDiagnosed();
    render(<DomainShieldRoute />);
    expect(screen.getByText("domain_shield.report_empty")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.no_reports_received")).toBeInTheDocument();
  });
});
