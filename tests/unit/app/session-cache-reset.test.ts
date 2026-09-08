/**
 * Signing out must take the workspace's data with it.
 *
 * Logout removed only the `auth-session` query, leaving twenty-six other keys
 * in the cache. Signing in as a different account in the same tab then rendered
 * the previous account's data until each query refetched and replaced it — the
 * "vinse.app connecté" flash on the connected-domains panel.
 *
 * The cache is memory-only, so a reload always cleared it. That is why the
 * symptom appeared once, on the first click, and never reproduced afterwards.
 */
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { discardSessionCache } from "../../../src/app/lib/session-cache";

/** The keys a signed-in workspace accumulates, as the app uses them. */
const TENANT_KEYS = [
  ["auth-session"],
  ["cf-integration"],
  ["cloudflare-list"],
  ["cf-workspace-token"],
  ["domain-shield", "vinse.app"],
  ["quarantine", "vinse.app"],
  ["threats", "vinse.app", "recent"],
  ["kpis", "workspace-a", "vinse.app"],
  ["dmarc-reports", "vinse.app"],
  ["alert-preferences", "vinse.app"],
  ["security-rules", "vinse.app"],
  ["admin-overview"],
] as const;

function signedInClient(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  for (const key of TENANT_KEYS) {
    queryClient.setQueryData([...key], { workspace: "workspace-a", domain: "vinse.app" });
  }
  return queryClient;
}

describe("session cache reset", () => {
  it("leaves nothing of the previous workspace behind", () => {
    const queryClient = signedInClient();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(TENANT_KEYS.length);

    discardSessionCache(queryClient);

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    for (const key of TENANT_KEYS) {
      expect(queryClient.getQueryData([...key])).toBeUndefined();
    }
  });

  it("does not stop at auth-session, which was the whole bug", () => {
    const queryClient = signedInClient();

    discardSessionCache(queryClient);

    // The connected-domain list is what actually flashed on screen.
    expect(queryClient.getQueryData(["cloudflare-list"])).toBeUndefined();
    expect(queryClient.getQueryData(["cf-integration"])).toBeUndefined();
    expect(queryClient.getQueryData(["domain-shield", "vinse.app"])).toBeUndefined();
  });

  it("a request already in flight cannot put the data back", async () => {
    // Removing a query destroys it, and destroying it cancels the fetch,
    // so a response arriving after sign-out is discarded rather than cached.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    });

    // A fetch issued as the previous user that resolves after they signed out.
    let release: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      release = resolve;
    });
    const inFlight = queryClient.fetchQuery({
      queryKey: ["cloudflare-list"],
      queryFn: () => pending.then(() => ({ domain: "vinse.app" })),
    });

    discardSessionCache(queryClient);
    release({ domain: "vinse.app" });
    await inFlight.catch(() => undefined);

    expect(queryClient.getQueryData(["cloudflare-list"])).toBeUndefined();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it("a fresh sign-in starts from an empty cache", () => {
    const queryClient = signedInClient();
    discardSessionCache(queryClient);

    queryClient.setQueryData(["cloudflare-list"], { workspace: "workspace-b", domain: null });

    expect(queryClient.getQueryData(["cloudflare-list"])).toEqual({
      workspace: "workspace-b",
      domain: null,
    });
    expect(queryClient.getQueryCache().getAll()).toHaveLength(1);
  });
});
