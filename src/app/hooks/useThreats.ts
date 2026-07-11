import { useThreatLogs, useUpdateThreatStatus } from "../lib/api";

/**
 * Hook custom pour gérer l'historique et le statut des menaces Sicurre.
 */
export function useThreats() {
  const { data: threats, isLoading, error } = useThreatLogs();
  const updateStatus = useUpdateThreatStatus();
  return { threats, isLoading, error, updateStatus };
}
