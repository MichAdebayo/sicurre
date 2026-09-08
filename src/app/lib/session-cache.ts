import type { QueryClient } from "@tanstack/react-query";

/**
 * Drop every cached query when a session ends.
 *
 * Each cached query holds data belonging to the workspace that was signed in.
 * Logout used to remove only `auth-session`, leaving the other twenty-six keys
 * - quarantine, threats, kpis, the connected-domain list - in memory, so the
 * next account to sign in on the same tab was shown the previous account's
 * data until each query refetched and replaced it.
 *
 * `clear` is enough on its own to make that safe: removing a query destroys it,
 * and destroying it cancels any fetch still in flight, so a request issued as
 * the previous user cannot resolve afterwards and put their data back.
 *
 * The cache is memory-only, so none of this survived a reload - which is why
 * the symptom was a flash on first render rather than a lasting leak.
 */
export function discardSessionCache(queryClient: QueryClient): void {
  queryClient.clear();
}
