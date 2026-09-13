// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useAdminDomains,
  useAdminOverview,
  useAdminRuntimeHealth,
  useAlertHistory,
  useAlertPreferences,
  useCloudflareList,
  useCloudflareStatus,
  useDatasets,
  useDmarcReportSummary,
  useDomainShieldStatus,
  useKPIStats,
  useOperationalExercises,
  useQuarantineItems,
  useReportAddress,
  useReportedEmails,
  useSecurityRules,
  useThreatLogs,
  useThreatPage,
  useWorkspaceCloudflareToken,
  type DomainShieldStatus,
  type KPIStats,
  type ThreatLog,
} from "../../../src/app/lib/api";

vi.mock("../../../src/app/lib/auth-client", () => ({
  authBaseURL: "/api/auth",
  authClient: {},
}));

const fetchMock = vi.fn();
let client: QueryClient;

function Wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const respondWith = (body: unknown, status = 200) => {
  fetchMock.mockImplementation(async () =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
};

const calledPaths = () => fetchMock.mock.calls.map((call) => String(call[0]));

const kpis: KPIStats = {
  domain: "vinse.app",
  raw_records_count: 120,
  normalized_messages_count: 118,
  dataset_items_count: 100,
  threats_phishing_count: 8,
  threats_spam_count: 3,
  threats_legitimate_count: 107,
};

const threat: ThreatLog = {
  id: "t-1",
  message_id: "m-1",
  subject: "Facture en attente",
  sender: "compta@exemple.test",
  body_preview: "",
  verdict: "phishing",
  confidence: 0.93,
  status: "active",
  received_at: "2026-09-10T09:30:00.000Z",
  privacy_reference: "MSG-0001",
  content_redacted: true,
};

const shield: DomainShieldStatus = {
  spf: { valid: true, record: "v=spf1 -all", error: null },
  dkim: { valid: true, record: "v=DKIM1", error: null },
  dmarc: { valid: true, record: "v=DMARC1; p=reject", policy: "reject", error: null },
  ssl: { valid: true, days_remaining: 42, auto_renew: true, error: null },
  reputation_score: 92,
  score_grade: "A",
  blacklists: { listed: false, matched: [], error: null },
  updated_at: "2026-09-12T08:00:00.000Z",
};

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  client.clear();
  localStorage.clear();
  sessionStorage.clear();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("useKPIStats", () => {
  it("loads the KPI statistics of the domain and caches them for the workspace", async () => {
    respondWith(kpis);

    const { result } = renderHook(() => useKPIStats("ws-1", "vinse.app"), { wrapper: Wrapper });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual(kpis));
    expect(fetchMock).toHaveBeenCalledWith("/v1/stats/kpi?domain=vinse.app", expect.objectContaining({ credentials: "include" }));
    expect(JSON.parse(sessionStorage.getItem("sicurre:kpis:ws-1:vinse.app") ?? "null")).toEqual(kpis);
  });

  it("serves the cached statistics of the workspace before the network answers", async () => {
    sessionStorage.setItem("sicurre:kpis:ws-1:vinse.app", JSON.stringify(kpis));
    respondWith({ ...kpis, raw_records_count: 121 });

    const { result } = renderHook(() => useKPIStats("ws-1", "vinse.app"), { wrapper: Wrapper });

    expect(result.current.data).toEqual(kpis);
    await waitFor(() => expect(result.current.data?.raw_records_count).toBe(121));
  });

  it("ignores a corrupted cache entry and loads from the network", async () => {
    sessionStorage.setItem("sicurre:kpis:ws-1:vinse.app", "{not json");
    respondWith(kpis);

    const { result } = renderHook(() => useKPIStats("ws-1", "vinse.app"), { wrapper: Wrapper });

    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data).toEqual(kpis));
  });

  it("does not read the cache without a workspace and does not query without a domain", () => {
    sessionStorage.setItem("sicurre:kpis::", JSON.stringify(kpis));

    const { result } = renderHook(() => useKPIStats("", ""), { wrapper: Wrapper });

    expect(result.current.data).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("admin queries", () => {
  it("loads the platform overview", async () => {
    const overview = { summary: { workspaces_count: 4 }, verdicts: [], feedback_by_type: [] };
    respondWith(overview);

    const { result } = renderHook(() => useAdminOverview(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(overview));
    expect(calledPaths()).toEqual(["/v1/admin/overview"]);
  });

  it("exposes the API error of the overview without retrying", async () => {
    respondWith({ detail: "Accès refusé" }, 403);

    const { result } = renderHook(() => useAdminOverview(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Accès refusé");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("lists the connected domains of the page with the search term", async () => {
    const page = { items: [{ zone_name: "vinse.app" }], page: 2, page_size: 20, total: 21, pages: 2 };
    respondWith(page);

    const { result } = renderHook(() => useAdminDomains(2, "vinse"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(page));
    expect(calledPaths()).toEqual(["/v1/admin/domains?page=2&page_size=20&search=vinse"]);
  });

  it("does not list the domains while disabled", () => {
    renderHook(() => useAdminDomains(1, "", false), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads the runtime health of the platform", async () => {
    const health = { status: "ok", checked_at: "2026-09-13T08:00:00Z", components: [] };
    respondWith(health);

    const { result } = renderHook(() => useAdminRuntimeHealth(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(health));
    expect(calledPaths()).toEqual(["/v1/admin/runtime-health"]);
  });

  it("does not probe the runtime health while disabled", () => {
    renderHook(() => useAdminRuntimeHealth(false), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads the operational exercise state, including the active exercise", async () => {
    const state = {
      enabled: true,
      active: { id: "ex-1", exercise_type: "api_unavailable", initiated_by: "michael", started_at: "s", expires_at: "e" },
      recent: [],
      supported_types: ["api_unavailable", "high_latency", "elevated_5xx"],
    };
    respondWith(state);

    const { result } = renderHook(() => useOperationalExercises(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(state));
    expect(calledPaths()).toEqual(["/v1/admin/operational-exercises"]);
  });

  it("stops polling the exercises after an error", async () => {
    respondWith({ detail: "Exercices désactivés" }, 503);

    const { result } = renderHook(() => useOperationalExercises(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Exercices désactivés");
  });

  it("does not load the exercises while disabled", () => {
    renderHook(() => useOperationalExercises(false), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("threat queries", () => {
  it("lists the first page of threats with the default filters", async () => {
    const page = { items: [threat], page: 1, page_size: 10, total: 1, pages: 1 };
    respondWith(page);

    const { result } = renderHook(() => useThreatPage("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(page));
    expect(calledPaths()).toEqual([
      "/v1/threats?page=1&page_size=10&verdict=all&date_range=all&search=&hidden=false&domain=vinse.app",
    ]);
  });

  it("forwards every filter of the threat query to the API", async () => {
    respondWith({ items: [], page: 2, page_size: 25, total: 0, pages: 0 });

    const { result } = renderHook(
      () => useThreatPage("vinse.app", { page: 2, pageSize: 25, verdict: "phishing", dateRange: "7d", search: "facture", hidden: true }),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(result.current.data?.page).toBe(2));
    expect(calledPaths()).toEqual([
      "/v1/threats?page=2&page_size=25&verdict=phishing&date_range=7d&search=facture&hidden=true&domain=vinse.app",
    ]);
  });

  it("does not list threats without a domain", () => {
    const { result } = renderHook(() => useThreatPage(""), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.data).toBeUndefined();
  });

  it("unwraps the recent threat events of the domain", async () => {
    respondWith({ items: [threat], page: 1, page_size: 100, total: 1, pages: 1 });

    const { result } = renderHook(() => useThreatLogs("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual([threat]));
    expect(calledPaths()).toEqual(["/v1/threats?page=1&page_size=100&date_range=all&domain=vinse.app"]);
  });

  it("does not list recent threats without a domain", () => {
    renderHook(() => useThreatLogs(""), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("feedback queries", () => {
  it("loads the address that receives forwarded reports", async () => {
    respondWith({ address: "report@vinse.app" });

    const { result } = renderHook(() => useReportAddress(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual({ address: "report@vinse.app" }));
    expect(calledPaths()).toEqual(["/v1/feedback/report-address"]);
  });

  it("loads the metadata of the forwarded reports", async () => {
    const reports = { items: [{ id: "r-1", received_at: "2026-09-12T08:00:00Z", size_bytes: 1024, status: "stored" }] };
    respondWith(reports);

    const { result } = renderHook(() => useReportedEmails(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(reports));
    expect(calledPaths()).toEqual(["/v1/feedback/reports"]);
  });
});

describe("cloudflare and dataset queries", () => {
  it("loads the integration status", async () => {
    respondWith({ status: "active", zone_name: "vinse.app" });

    const { result } = renderHook(() => useCloudflareStatus(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data?.status).toBe("active"));
    expect(calledPaths()).toEqual(["/v1/integrations/cloudflare/status"]);
  });

  it("tells whether the workspace token is configured", async () => {
    respondWith({ configured: true });

    const { result } = renderHook(() => useWorkspaceCloudflareToken(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual({ configured: true }));
    expect(calledPaths()).toEqual(["/v1/integrations/cloudflare/token"]);
  });

  it("lists every connected domain", async () => {
    respondWith([{ status: "active", zone_name: "vinse.app" }]);

    const { result } = renderHook(() => useCloudflareList(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(calledPaths()).toEqual(["/v1/integrations/cloudflare/list"]);
  });

  it("lists the datasets and can be disabled", async () => {
    respondWith([{ id: "d-1", version_tag: "v1", item_count: 10, status: "published", published_at: null }]);

    const { result } = renderHook(() => useDatasets(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(calledPaths()).toEqual(["/v1/datasets"]);

    fetchMock.mockClear();
    renderHook(() => useDatasets(false), { wrapper: Wrapper });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("quarantine and alert queries", () => {
  it("lists the quarantined messages of the domain", async () => {
    respondWith([{ id: "q-1", domain: "vinse.app", status: "held" }]);

    const { result } = renderHook(() => useQuarantineItems("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(calledPaths()).toEqual(["/v1/quarantine?domain=vinse.app"]);
  });

  it("loads the alert preferences of the domain", async () => {
    respondWith({ domain: "vinse.app", email_enabled: true });

    const { result } = renderHook(() => useAlertPreferences("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data?.email_enabled).toBe(true));
    expect(calledPaths()).toEqual(["/v1/alerts/preferences?domain=vinse.app"]);
  });

  it("lists the security rules of the domain", async () => {
    respondWith([{ id: "r-1", rule_type: "whitelist", pattern: "*@vinse.app" }]);

    const { result } = renderHook(() => useSecurityRules("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(calledPaths()).toEqual(["/v1/alerts/rules?domain=vinse.app"]);
  });

  it("lists the alert history of the domain", async () => {
    respondWith([{ id: "a-1", title: "Phishing bloqué", is_read: false }]);

    const { result } = renderHook(() => useAlertHistory("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(calledPaths()).toEqual(["/v1/alerts/history?domain=vinse.app"]);
  });

  it("does not query quarantine, preferences, rules or history without a domain", () => {
    renderHook(() => useQuarantineItems(""), { wrapper: Wrapper });
    renderHook(() => useAlertPreferences(""), { wrapper: Wrapper });
    renderHook(() => useSecurityRules(""), { wrapper: Wrapper });
    renderHook(() => useAlertHistory(""), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useDomainShieldStatus", () => {
  it("loads the shield status and stores it for the next visit", async () => {
    respondWith(shield);

    const { result } = renderHook(() => useDomainShieldStatus("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(shield));
    expect(calledPaths()).toEqual(["/v1/domain-shield/vinse.app/status"]);
    expect(JSON.parse(localStorage.getItem("sicurre_domain_shield_status:vinse.app") ?? "null")).toEqual(shield);
  });

  it("serves a reusable stored status without touching the network", async () => {
    localStorage.setItem("sicurre_domain_shield_status:vinse.app", JSON.stringify(shield));

    const { result } = renderHook(() => useDomainShieldStatus("vinse.app"), { wrapper: Wrapper });

    expect(result.current.data).toEqual(shield);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("ignores a stored status that is not worth reusing", async () => {
    localStorage.setItem(
      "sicurre_domain_shield_status:vinse.app",
      JSON.stringify({ ...shield, blacklists: { listed: false, matched: [], error: "timeout" } }),
    );
    respondWith(shield);

    const { result } = renderHook(() => useDomainShieldStatus("vinse.app"), { wrapper: Wrapper });

    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data).toEqual(shield));
  });

  it("discards a corrupted stored status and loads from the network", async () => {
    localStorage.setItem("sicurre_domain_shield_status:vinse.app", "{broken");
    respondWith(shield);

    const { result } = renderHook(() => useDomainShieldStatus("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(shield));
    expect(JSON.parse(localStorage.getItem("sicurre_domain_shield_status:vinse.app") ?? "null")).toEqual(shield);
  });

  it("does not query while disabled or without a domain", () => {
    renderHook(() => useDomainShieldStatus("vinse.app", false), { wrapper: Wrapper });
    renderHook(() => useDomainShieldStatus(""), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useDmarcReportSummary", () => {
  it("loads the aggregate DMARC summary of the domain", async () => {
    const summary = { domain: "vinse.app", total_messages: 10, aligned_messages: 9, failed_messages: 1, report_count: 2, last_report_at: null, top_sources: [] };
    respondWith(summary);

    const { result } = renderHook(() => useDmarcReportSummary("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(summary));
    expect(calledPaths()).toEqual(["/v1/domain-shield/vinse.app/dmarc-reports"]);
  });

  it("does not query while disabled or without a domain", () => {
    renderHook(() => useDmarcReportSummary("vinse.app", false), { wrapper: Wrapper });
    renderHook(() => useDmarcReportSummary(""), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
