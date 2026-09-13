// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useCreateFeedback,
  useCreateSecurityRule,
  useCreateSupportRequest,
  useDeleteAccount,
  useDeleteQuarantine,
  useDeleteSecurityRule,
  useDeleteWorkspaceCloudflareToken,
  useDismissAlert,
  useEraseAdminAccount,
  useImportDmarcReport,
  useMarkAlertRead,
  useMarkDomainAlertsRead,
  usePreviewCloudflareDomain,
  useRecoverOperationalExercise,
  useRefreshDomainShieldStatus,
  useReleaseAndWhitelist,
  useReleaseQuarantine,
  useRunPipeline,
  useSaveWorkspaceCloudflareToken,
  useSetThreatVisibility,
  useSetupCloudflare,
  useStartOperationalExercise,
  useTeardownCloudflare,
  useUpdateAlertPreferences,
  useUpdateThreatStatus,
  useVerifyCloudflareToken,
  type DomainShieldStatus,
} from "../../../src/app/lib/api";

vi.mock("../../../src/app/lib/auth-client", () => ({
  authBaseURL: "/api/auth",
  authClient: {},
}));

const fetchMock = vi.fn();
let client: QueryClient;
let invalidate: ReturnType<typeof vi.spyOn>;

function Wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const respondWith = (body: unknown, status = 200) => {
  fetchMock.mockImplementation(async () =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
};

function request(index = 0) {
  const [url, init] = fetchMock.mock.calls[index] as [string, RequestInit];
  const headers = init.headers as Headers;
  return {
    url,
    method: init.method,
    body: init.body,
    credentials: init.credentials,
    contentType: headers.get("Content-Type"),
  };
}

const invalidatedKeys = () =>
  invalidate.mock.calls.map((call) => (call[0] as { queryKey: unknown[] }).queryKey);

/** Render the mutation hook, run it once and return what it resolved to. */
async function runMutation<TData, TVars>(
  hook: () => { mutateAsync: (vars: TVars) => Promise<TData> },
  vars: TVars,
): Promise<TData> {
  const { result } = renderHook(hook, { wrapper: Wrapper });
  let outcome!: TData;
  await act(async () => {
    outcome = await result.current.mutateAsync(vars);
  });
  return outcome;
}

const shield: DomainShieldStatus = {
  spf: { valid: true, record: "v=spf1 -all", error: null },
  dkim: { valid: true, record: "v=DKIM1", error: null },
  dmarc: { valid: true, record: "v=DMARC1; p=reject", policy: "reject", error: null },
  ssl: { valid: true, days_remaining: 42, auto_renew: true, error: null },
  reputation_score: 92,
  score_grade: "A",
  blacklists: { listed: false, matched: [], error: null },
};

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  invalidate = vi.spyOn(client, "invalidateQueries");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  client.clear();
  localStorage.clear();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("operational exercise mutations", () => {
  it("starts an exercise and refreshes the exercise state", async () => {
    respondWith({ id: "ex-1", exercise_type: "api_unavailable" });

    const outcome = await runMutation(useStartOperationalExercise, { exercise_type: "api_unavailable", duration_seconds: 120 });

    expect(outcome.id).toBe("ex-1");
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/admin/operational-exercises",
      method: "POST",
      body: JSON.stringify({ exercise_type: "api_unavailable", duration_seconds: 120 }),
      credentials: "include",
      contentType: "application/json",
    }));
    expect(invalidatedKeys()).toEqual([["admin-operational-exercises"]]);
  });

  it("recovers an exercise by id and refreshes the exercise state", async () => {
    respondWith({ id: "ex-1", status: "recovered" });

    await runMutation(useRecoverOperationalExercise, "ex-1");

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/admin/operational-exercises/ex-1/recover",
      method: "POST",
      body: undefined,
    }));
    expect(invalidatedKeys()).toEqual([["admin-operational-exercises"]]);
  });

  it("surfaces the API refusal and refreshes nothing", async () => {
    respondWith({ detail: "Un exercice est déjà actif" }, 409);

    const { result } = renderHook(() => useStartOperationalExercise(), { wrapper: Wrapper });

    await expect(
      act(() => result.current.mutateAsync({ exercise_type: "high_latency", duration_seconds: 60 })),
    ).rejects.toThrow("Un exercice est déjà actif");
    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe("threat and feedback mutations", () => {
  it("hides several events at once and refreshes the threat lists", async () => {
    respondWith({ updated: 2, hidden: true });

    const outcome = await runMutation(() => useSetThreatVisibility("vinse.app"), { ids: ["t-1", "t-2"], hidden: true });

    expect(outcome).toEqual({ updated: 2, hidden: true });
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/threats/visibility?domain=vinse.app",
      method: "POST",
      body: JSON.stringify({ ids: ["t-1", "t-2"], hidden: true }),
    }));
    expect(invalidatedKeys()).toEqual([["threats"]]);
  });

  it("changes the status of an event and refreshes threats and statistics", async () => {
    respondWith({ id: "t-1", status: "trashed" });

    await runMutation(() => useUpdateThreatStatus("vinse.app"), { id: "t-1", status: "trashed" });

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/threats/t-1/status?domain=vinse.app",
      method: "POST",
      body: JSON.stringify({ status: "trashed" }),
    }));
    expect(invalidatedKeys()).toEqual([["threats"], ["kpis"]]);
  });

  it("records feedback on a verdict and refreshes threats and statistics", async () => {
    respondWith({ id: "f-1", event_id: "t-1", feedback_type: "false_positive", created_at: "now" });
    const payload = { event_id: "t-1", feedback_type: "false_positive" as const, corrected_verdict: "legitimate" as const, reporter_note: "newsletter" };

    await runMutation(() => useCreateFeedback("vinse.app"), payload);

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/feedback?domain=vinse.app",
      method: "POST",
      body: JSON.stringify(payload),
    }));
    expect(invalidatedKeys()).toEqual([["threats"], ["kpis"]]);
  });

  it("files a support request without touching any cached query", async () => {
    respondWith({ id: "s-1", status: "open", created_at: "now" });
    const payload = { requester_name: "Michael", requester_email: "michael@vinse.app", category: "billing", message: "Bonjour" };

    const outcome = await runMutation(useCreateSupportRequest, payload);

    expect(outcome.status).toBe("open");
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/support/requests",
      method: "POST",
      body: JSON.stringify(payload),
    }));
    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe("cloudflare mutations", () => {
  const cfKeys = [["cf-integration"], ["auth-session"], ["cloudflare-list"], ["cf-workspace-token"], ["domain-shield"]];

  it("previews a domain from public DNS without touching any cached query", async () => {
    respondWith({ zone_name: "vinse.app", resolvable: true, on_cloudflare: true, mail_provider: "other" });

    const outcome = await runMutation(usePreviewCloudflareDomain, { zone_name: "vinse.app" });

    expect(outcome.on_cloudflare).toBe(true);
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/integrations/cloudflare/preview",
      method: "POST",
      body: JSON.stringify({ zone_name: "vinse.app" }),
    }));
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("verifies a token against its zone", async () => {
    respondWith({ valid: true, zone_id: "z-1" });

    const outcome = await runMutation(useVerifyCloudflareToken, { cf_api_token: "cf-secret", zone_name: "vinse.app" });

    expect(outcome).toEqual({ valid: true, zone_id: "z-1" });
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/integrations/cloudflare/verify-token",
      method: "POST",
      body: JSON.stringify({ cf_api_token: "cf-secret", zone_name: "vinse.app" }),
    }));
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("sets up the integration and refreshes every view that depends on it", async () => {
    respondWith({ integration_id: "i-1", status: "provisioning" });
    const payload = { zone_name: "vinse.app", destination_email: "inbox@vinse.app", fix_spf: true, fix_dmarc: false };

    await runMutation(useSetupCloudflare, payload);

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/integrations/cloudflare/setup",
      method: "POST",
      body: JSON.stringify(payload),
    }));
    expect(invalidatedKeys()).toEqual(cfKeys);
  });

  it("rejects with the API detail when the setup is refused", async () => {
    respondWith({ detail: "Jeton invalide" }, 400);

    const { result } = renderHook(() => useSetupCloudflare(), { wrapper: Wrapper });

    await expect(
      act(() => result.current.mutateAsync({ zone_name: "vinse.app", destination_email: "inbox@vinse.app" })),
    ).rejects.toThrow("Jeton invalide");
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("tears the integration down and refreshes every view that depends on it", async () => {
    respondWith({ status: "removed", dmarc_reporting_withdrawn: true });

    await runMutation(useTeardownCloudflare, { integration_id: "i-1" });

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/integrations/cloudflare",
      method: "DELETE",
      body: JSON.stringify({ integration_id: "i-1" }),
    }));
    expect(invalidatedKeys()).toEqual(cfKeys);
  });

  it("saves the workspace token and refreshes the token and domain list", async () => {
    respondWith({ status: "saved" });

    await runMutation(useSaveWorkspaceCloudflareToken, "cf-secret");

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/integrations/cloudflare/token",
      method: "POST",
      body: JSON.stringify({ cf_api_token: "cf-secret" }),
    }));
    expect(invalidatedKeys()).toEqual([["cf-workspace-token"], ["cloudflare-list"]]);
  });

  it("deletes the workspace token and refreshes every view that depends on it", async () => {
    respondWith({ status: "deleted" });

    await runMutation(useDeleteWorkspaceCloudflareToken, undefined);

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/integrations/cloudflare/token",
      method: "DELETE",
      body: undefined,
    }));
    expect(invalidatedKeys()).toEqual([["cf-workspace-token"], ["cf-integration"], ["auth-session"], ["cloudflare-list"], ["domain-shield"]]);
  });
});

describe("account erasure", () => {
  it("sends the typed address, then forgets the stored session and every cached query", async () => {
    respondWith({ status: "deleted" });
    localStorage.setItem("sicurre_user_email", "owner@example.test");
    const clear = vi.spyOn(client, "clear");

    const outcome = await runMutation(useDeleteAccount, "owner@example.test");

    expect(outcome).toEqual({ status: "deleted" });
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/auth/account",
      method: "DELETE",
      body: JSON.stringify({ email: "owner@example.test" }),
      credentials: "include",
      contentType: "application/json",
    }));
    expect(localStorage.getItem("sicurre_user_email")).toBeNull();
    expect(clear).toHaveBeenCalled();
  });

  it("keeps the session when the API refuses the erasure", async () => {
    respondWith({ detail: "Confirmation email does not match the account" }, 400);
    localStorage.setItem("sicurre_user_email", "owner@example.test");
    const { result } = renderHook(useDeleteAccount, { wrapper: Wrapper });

    await expect(
      act(() => result.current.mutateAsync("someone@else.test")),
    ).rejects.toThrow("Confirmation email does not match the account");
    expect(localStorage.getItem("sicurre_user_email")).toBe("owner@example.test");
  });
});

describe("admin account erasure", () => {
  it("erases the customer by email and refreshes the admin inventory", async () => {
    respondWith({ status: "deleted" });

    await runMutation(useEraseAdminAccount, "owner@example.test");

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/admin/accounts",
      method: "DELETE",
      body: JSON.stringify({ email: "owner@example.test" }),
    }));
    expect(invalidatedKeys()).toEqual([["admin-domains"], ["admin-overview"]]);
  });
});

describe("pipeline and quarantine mutations", () => {
  it("runs the pipeline and refreshes datasets and statistics", async () => {
    respondWith({ run_id: "run-1" });

    const outcome = await runMutation(useRunPipeline, undefined);

    expect(outcome).toEqual({ run_id: "run-1" });
    expect(request()).toEqual(expect.objectContaining({ url: "/v1/pipeline/run", method: "POST" }));
    expect(invalidatedKeys()).toEqual([["datasets"], ["kpis"]]);
  });

  it("releases a quarantined message and refreshes quarantine and statistics", async () => {
    respondWith({ status: "released", forwarded_to: "inbox@vinse.app" });

    await runMutation(() => useReleaseQuarantine("vinse.app"), "q-1");

    expect(request()).toEqual(expect.objectContaining({ url: "/v1/quarantine/q-1/release?domain=vinse.app", method: "POST" }));
    expect(invalidatedKeys()).toEqual([["quarantine"], ["kpis"]]);
  });

  it("deletes a quarantined message and refreshes the quarantine only", async () => {
    respondWith({ status: "deleted" });

    await runMutation(() => useDeleteQuarantine("vinse.app"), "q-1");

    expect(request()).toEqual(expect.objectContaining({ url: "/v1/quarantine/q-1?domain=vinse.app", method: "DELETE" }));
    expect(invalidatedKeys()).toEqual([["quarantine"]]);
  });

  it("releases and whitelists a sender, refreshing quarantine, rules and statistics", async () => {
    respondWith({ status: "released", whitelisted_pattern: "*@partner.test" });

    await runMutation(() => useReleaseAndWhitelist("vinse.app"), "q-1");

    expect(request()).toEqual(expect.objectContaining({ url: "/v1/quarantine/q-1/whitelist?domain=vinse.app", method: "POST" }));
    expect(invalidatedKeys()).toEqual([["quarantine"], ["security-rules"], ["kpis"]]);
  });
});

describe("alert and rule mutations", () => {
  it("replaces the alert preferences and refreshes them", async () => {
    respondWith({ status: "saved" });
    const payload = {
      email_enabled: true,
      notify_phishing: true,
      notify_domain_shield: false,
      quiet_hours_enabled: true,
      quiet_hours_start: "22:00",
      quiet_hours_end: "07:00",
      timezone: "Europe/Paris",
    };

    await runMutation(() => useUpdateAlertPreferences("vinse.app"), payload);

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/alerts/preferences?domain=vinse.app",
      method: "PUT",
      body: JSON.stringify(payload),
    }));
    expect(invalidatedKeys()).toEqual([["alert-preferences"]]);
  });

  it("creates a security rule and refreshes the rules", async () => {
    respondWith({ id: "r-1", rule_type: "blocklist", pattern: "*@scam.test" });

    await runMutation(() => useCreateSecurityRule("vinse.app"), { rule_type: "blocklist", pattern: "*@scam.test" });

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/alerts/rules?domain=vinse.app",
      method: "POST",
      body: JSON.stringify({ rule_type: "blocklist", pattern: "*@scam.test" }),
    }));
    expect(invalidatedKeys()).toEqual([["security-rules"]]);
  });

  it("deletes a security rule and refreshes the rules", async () => {
    respondWith({ status: "deleted" });

    await runMutation(() => useDeleteSecurityRule("vinse.app"), "r-1");

    expect(request()).toEqual(expect.objectContaining({ url: "/v1/alerts/rules/r-1?domain=vinse.app", method: "DELETE" }));
    expect(invalidatedKeys()).toEqual([["security-rules"]]);
  });

  it("dismisses an alert and refreshes every alert history", async () => {
    respondWith({ status: "dismissed" });

    await runMutation(() => useDismissAlert("vinse.app"), "a-1");

    expect(request()).toEqual(expect.objectContaining({ url: "/v1/alerts/history/a-1/dismiss?domain=vinse.app", method: "POST" }));
    expect(invalidatedKeys()).toEqual([["alert-history"]]);
  });

  it("marks every alert of the domain as read and refreshes that domain's history", async () => {
    respondWith({ status: "read" });

    await runMutation(() => useMarkDomainAlertsRead("vinse.app"), undefined);

    expect(request()).toEqual(expect.objectContaining({ url: "/v1/alerts/history/read?domain=vinse.app", method: "POST" }));
    expect(invalidatedKeys()).toEqual([["alert-history", "vinse.app"]]);
  });

  it("marks one alert as read and refreshes that domain's history", async () => {
    respondWith({ status: "read" });

    await runMutation(() => useMarkAlertRead("vinse.app"), "a-1");

    expect(request()).toEqual(expect.objectContaining({ url: "/v1/alerts/history/a-1/read?domain=vinse.app", method: "POST" }));
    expect(invalidatedKeys()).toEqual([["alert-history", "vinse.app"]]);
  });
});

describe("domain shield mutations", () => {
  it("uploads a DMARC report with its own content type and refreshes the summary", async () => {
    respondWith({ status: "imported", record_count: 3 });
    const file = new File(["<feedback/>"], "report.xml", { type: "application/xml" });

    const outcome = await runMutation(() => useImportDmarcReport("vinse.app"), file);

    expect(outcome).toEqual({ status: "imported", record_count: 3 });
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/domain-shield/vinse.app/dmarc-reports/import",
      method: "POST",
      body: file,
      contentType: "application/xml",
    }));
    expect(invalidatedKeys()).toEqual([["dmarc-reports", "vinse.app"]]);
  });

  it("uploads a file of unknown type as an octet stream", async () => {
    respondWith({ status: "already_imported", record_count: 0 });
    const file = new File(["PK"], "report.zip", { type: "" });

    await runMutation(() => useImportDmarcReport("vinse.app"), file);

    expect(request().contentType).toBe("application/octet-stream");
  });

  it("refreshes the shield status, stores it and replaces the cached query data", async () => {
    respondWith(shield);
    client.setQueryData(["domain-shield", "vinse.app"], { ...shield, reputation_score: 40, score_grade: "D" });

    const outcome = await runMutation(useRefreshDomainShieldStatus, "vinse.app");

    expect(outcome).toEqual(shield);
    expect(request()).toEqual(expect.objectContaining({ url: "/v1/domain-shield/vinse.app/status?refresh=true", method: undefined }));
    expect(client.getQueryData(["domain-shield", "vinse.app"])).toEqual(shield);
    expect(JSON.parse(localStorage.getItem("sicurre_domain_shield_status:vinse.app") ?? "null")).toEqual(shield);
    expect(invalidate).not.toHaveBeenCalled();
  });
});
