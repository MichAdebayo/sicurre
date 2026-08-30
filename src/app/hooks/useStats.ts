import { useKPIStats } from "../lib/api";

/**
 * Hook custom pour récupérer les statistiques KPI de Sicurre.
 */
export function useStats(workspaceId: string, domain: string) {
  const { data: stats, isLoading, error } = useKPIStats(workspaceId, domain);
  return { stats, isLoading, error };
}
