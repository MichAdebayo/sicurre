import { useKPIStats } from "../lib/api";

/**
 * Hook custom pour récupérer les statistiques KPI de Sicurre.
 */
export function useStats() {
  const { data: stats, isLoading, error } = useKPIStats();
  return { stats, isLoading, error };
}
