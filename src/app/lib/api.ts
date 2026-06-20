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

// ── Cloudflare Integration ────────────────────────────────────────────────────

export interface CloudflareStatus {
  status: "not_configured" | "provisioning" | "pending_verification" | "active" | "error";
  id?: string;
  user_email?: string;
  zone_name?: string;
  destination_email?: string;
  worker_name?: string;
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CloudflareSetupPayload {
  cf_api_token: string;
  zone_name: string;
  destination_email: string;
  user_email: string;
}

export interface CfTokenVerifyPayload {
  cf_api_token: string;
  zone_name: string;
}

export interface CloudflareTeardownPayload {
  cf_api_token: string;
  user_email: string;
}

const CF_BASE = "/integrations/cloudflare";

export function useCloudflareStatus(userEmail: string) {
  return useQuery<CloudflareStatus>({
    queryKey: ["cf-integration", userEmail],
    queryFn: () => fetchJson<CloudflareStatus>(`${CF_BASE}/status?user_email=${encodeURIComponent(userEmail)}`),
    refetchInterval: 5000,
    enabled: !!userEmail,
  });
}

export function useVerifyCloudflareToken() {
  return useMutation({
    mutationFn: (payload: CfTokenVerifyPayload) =>
      fetchJson<{ valid: boolean; zone_id?: string; error?: string }>(
        `${CF_BASE}/verify-token`,
        { method: "POST", body: JSON.stringify(payload) },
      ),
  });
}

export function useSetupCloudflare() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CloudflareSetupPayload) =>
      fetchJson<{ integration_id: string; status: string }>(
        `${CF_BASE}/setup`,
        { method: "POST", body: JSON.stringify(payload) },
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["cf-integration", variables.user_email] });
    },
  });
}

export function useTeardownCloudflare() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CloudflareTeardownPayload) =>
      fetchJson<{ status: string }>(
        `${CF_BASE}`,
        { method: "DELETE", body: JSON.stringify(payload) },
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["cf-integration", variables.user_email] });
    },
  });
}
