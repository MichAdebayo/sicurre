// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStats } from "../../../src/app/hooks/useStats";
import { useThreats } from "../../../src/app/hooks/useThreats";
import type { KPIStats, ThreatLog } from "../../../src/app/lib/api";

const fetchMock = vi.fn();
let client: QueryClient;

function Wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const jsonResponse = (body: unknown, ok = true): Response =>
  ({ ok, status: ok ? 200 : 500, json: async () => body }) as unknown as Response;

const kpis = {
  total_scanned: 120,
  threats_blocked: 12,
  threats_phishing_count: 8,
  threats_spam_count: 3,
  threats_legitimate_count: 109,
} as unknown as KPIStats;

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
  latency_ms: 420,
  privacy_reference: "MSG-0001",
  content_redacted: true,
};

const calledPaths = () => fetchMock.mock.calls.map((call) => String(call[0]));

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  client.clear();
  sessionStorage.clear();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("useStats", () => {
  it("loads the KPI statistics of the domain and caches them for the workspace", async () => {
    fetchMock.mockResolvedValue(jsonResponse(kpis));

    const { result } = renderHook(() => useStats("workspace-1", "vinse.app"), { wrapper: Wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.stats).toBeUndefined();

    await waitFor(() => expect(result.current.stats).toEqual(kpis));

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/stats/kpi?domain=vinse.app",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(JSON.parse(sessionStorage.getItem("sicurre:kpis:workspace-1:vinse.app") ?? "null")).toEqual(kpis);
  });

  it("serves the cached statistics of the workspace before the network answers", async () => {
    sessionStorage.setItem("sicurre:kpis:workspace-1:vinse.app", JSON.stringify(kpis));
    fetchMock.mockResolvedValue(jsonResponse({ ...kpis, total_scanned: 121 }));

    const { result } = renderHook(() => useStats("workspace-1", "vinse.app"), { wrapper: Wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.stats).toEqual(kpis);

    await waitFor(() => expect(result.current.stats?.total_scanned).toBe(121));
  });

  it("does not query the API while no domain is active", () => {
    const { result } = renderHook(() => useStats("workspace-1", ""), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.stats).toBeUndefined();
  });

  it("exposes the API error message when the statistics cannot be loaded", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Statistiques indisponibles" }, false));

    const { result } = renderHook(() => useStats("workspace-1", "vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    expect((result.current.error as Error).message).toBe("Statistiques indisponibles");
    expect(result.current.stats).toBeUndefined();
  });
});

describe("useThreats", () => {
  it("lists the recent threat events of the domain", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [threat], page: 1, page_size: 100, total: 1, pages: 1 }));

    const { result } = renderHook(() => useThreats("vinse.app"), { wrapper: Wrapper });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.threats).toEqual([threat]));

    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/threats?page=1&page_size=100&date_range=all&domain=vinse.app",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("updates the status of an event and refreshes the list afterwards", async () => {
    const listPath = "/v1/threats?page=1&page_size=100&date_range=all&domain=vinse.app";
    fetchMock.mockImplementation(async (path: string) => {
      if (path === listPath) {
        return jsonResponse({ items: [threat], page: 1, page_size: 100, total: 1, pages: 1 });
      }
      return jsonResponse({ ...threat, status: "trashed" });
    });

    const { result } = renderHook(() => useThreats("vinse.app"), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.threats).toHaveLength(1));

    let updated: ThreatLog | undefined;
    await act(async () => {
      updated = await result.current.updateStatus.mutateAsync({ id: "t-1", status: "trashed" });
    });

    expect(updated?.status).toBe("trashed");
    const statusCall = fetchMock.mock.calls.find((call) => String(call[0]).startsWith("/v1/threats/t-1/status"));
    expect(statusCall?.[0]).toBe("/v1/threats/t-1/status?domain=vinse.app");
    expect(statusCall?.[1]).toEqual(expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "trashed" }) }));

    await waitFor(() => expect(calledPaths().filter((path) => path === listPath).length).toBeGreaterThanOrEqual(2));
  });

  it("surfaces the failure of a status update to the caller", async () => {
    const listPath = "/v1/threats?page=1&page_size=100&date_range=all&domain=vinse.app";
    fetchMock.mockImplementation(async (path: string) => {
      if (path === listPath) {
        return jsonResponse({ items: [threat], page: 1, page_size: 100, total: 1, pages: 1 });
      }
      return jsonResponse({ detail: "Événement introuvable" }, false);
    });

    const { result } = renderHook(() => useThreats("vinse.app"), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.threats).toHaveLength(1));

    await expect(
      act(() => result.current.updateStatus.mutateAsync({ id: "missing", status: "restored" })),
    ).rejects.toThrow("Événement introuvable");
    await waitFor(() => expect(result.current.updateStatus.isError).toBe(true));
  });

  it("does not query the API while no domain is active", () => {
    const { result } = renderHook(() => useThreats(""), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.threats).toBeUndefined();
  });

  it("exposes the API error message when the history cannot be loaded", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, false));

    const { result } = renderHook(() => useThreats("vinse.app"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    expect((result.current.error as Error).message).toBe("Request failed");
  });
});
