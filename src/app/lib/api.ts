import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const API_BASE_URL = "/v1";

// Types matching the OpenAPI schemas
export interface KPIStats {
  raw_records_count: number;
  normalized_messages_count: number;
  dataset_items_count: number;
  threats_phishing_count: number;
  threats_spam_count: number;
  threats_legitimate_count: number;
}

export interface ThreatLog {
  id: string;
  message_id: string;
  subject: string;
  body_preview: string;
  verdict: "phishing" | "spam" | "legitimate";
  confidence: number;
  status: "active" | "trashed" | "restored";
  received_at: string;
}

export interface DatasetVersion {
  id: string;
  version_tag: string;
  item_count: number;
  status: "draft" | "frozen";
  published_at: string | null;
}

// Fetch helper (replaces Axios to block supply chain vulnerabilities)
async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem("sicurre_session_token");
  const headers = new Headers(options?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.detail || "Request failed");
  }

  return response.json() as Promise<T>;
}

// App based scripts & hooks for React query integration
export function useKPIStats() {
  return useQuery<KPIStats>({
    queryKey: ["kpis"],
    queryFn: () => fetchJson<KPIStats>("/stats/kpi"),
    refetchInterval: 10000, // poll every 10s for live-like updating
  });
}

export function useThreatLogs() {
  return useQuery<ThreatLog[]>({
    queryKey: ["threats"],
    queryFn: () => fetchJson<ThreatLog[]>("/threats"),
  });
}

export function useUpdateThreatStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "trashed" | "restored" | "active" }) =>
      fetchJson<ThreatLog>(`/threats/${id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threats"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}

export function useDatasets() {
  return useQuery<DatasetVersion[]>({
    queryKey: ["datasets"],
    queryFn: () => fetchJson<DatasetVersion[]>("/datasets"),
  });
}

export function useRunPipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => fetchJson<{ run_id: string }>("/pipeline/run", { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threats"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}
