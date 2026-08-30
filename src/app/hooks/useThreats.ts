import { useThreatLogs, useUpdateThreatStatus } from "../lib/api";

/**
 * Hook custom pour gérer l'historique et le statut des menaces Sicurre.
 */
export function useThreats(domain: string) {
  const { data: threats, isLoading, error } = useThreatLogs(domain);
  const updateStatus = useUpdateThreatStatus(domain);
  return { threats, isLoading, error, updateStatus };
}
