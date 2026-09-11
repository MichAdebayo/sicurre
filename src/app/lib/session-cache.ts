import type { QueryClient } from "@tanstack/react-query";

/**
 * Drop every cached query when a session ends.
 *
 * Every cached query holds data for the workspace that was signed in, so the
 * cache is cleared as a whole rather than key by key. `clear` also cancels
 * fetches still in flight, so a request issued as the previous user cannot
 * resolve afterwards and put their data back.
 */
export function discardSessionCache(queryClient: QueryClient): void {
  queryClient.clear();
}
