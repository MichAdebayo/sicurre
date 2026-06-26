import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authClient } from "./auth-client";

const API_BASE_URL = "/v1";
const USER_NAME_KEY = "sicurre_user_name";
const USER_EMAIL_KEY = "sicurre_user_email";
const USER_ROLE_KEY = "sicurre_user_role";
const AUTH_PROVIDER_KEY = "sicurre_auth_provider";

export type AuthProvider = "password" | "google";

export interface AuthSession {
  id: string;
  email: string;
  display_name: string;
  role: string;
  workspace_id: string;
  workspace_name: string;
  is_platform_admin: boolean;
  has_cloudflare_integration: boolean;
  threat_count: number;
  onboarding_required: boolean;
}

export interface Dataset {
  id: string;
  version_tag: string;
  item_count: number;
  status: string;
  published_at: string | null;
}

export interface SessionSeed {
  displayName?: string;
  email?: string;
  role?: string;
  authProvider?: AuthProvider;
}

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
  sender: string;
  body_preview: string;
  verdict: "phishing" | "spam" | "legitimate";
  confidence: number;
  status: "active" | "trashed" | "restored";
  received_at: string;
}

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
}

export interface CfTokenVerifyPayload {
  cf_api_token: string;
  zone_name: string;
}

export interface CloudflareTeardownPayload {
  cf_api_token: string;
}

export function getStoredAuthProvider(): AuthProvider {
  return (localStorage.getItem(AUTH_PROVIDER_KEY) as AuthProvider | null) ?? "password";
}

export function seedStoredSession(seed: SessionSeed): void {
  if (seed.displayName) {
    localStorage.setItem(USER_NAME_KEY, seed.displayName);
  }
  if (seed.email) {
    localStorage.setItem(USER_EMAIL_KEY, seed.email);
  }
  if (seed.role) {
    localStorage.setItem(USER_ROLE_KEY, seed.role);
  }
  localStorage.setItem(AUTH_PROVIDER_KEY, seed.authProvider ?? "password");
}

export function persistSession(session: AuthSession, authProvider: AuthProvider = getStoredAuthProvider()): void {
  localStorage.setItem(USER_NAME_KEY, session.display_name);
  localStorage.setItem(USER_EMAIL_KEY, session.email);
  localStorage.setItem(USER_ROLE_KEY, session.role);
  localStorage.setItem(AUTH_PROVIDER_KEY, authProvider);
}

export function clearStoredSession(): void {
  localStorage.removeItem(USER_NAME_KEY);
  localStorage.removeItem(USER_EMAIL_KEY);
  localStorage.removeItem(USER_ROLE_KEY);
  localStorage.removeItem(AUTH_PROVIDER_KEY);
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.detail || "Request failed");
  }

  return response.json() as Promise<T>;
}

export function useCurrentSession(enabled = true) {
  return useQuery<AuthSession>({
    queryKey: ["auth-session"],
    queryFn: () => fetchJson<AuthSession>("/auth/session"),
    enabled,
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { email: string; password: string }) => {
      const result = await authClient.signIn.email({
        email: payload.email,
        password: payload.password,
      });
      if (result.error) {
        throw new Error(result.error.message || "Connexion impossible.");
      }
      return result;
    },
    onSuccess: async () => {
      localStorage.setItem(AUTH_PROVIDER_KEY, "password");
      queryClient.invalidateQueries({ queryKey: ["auth-session"] });
      const session = await queryClient.fetchQuery({
        queryKey: ["auth-session"],
        queryFn: () => fetchJson<AuthSession>("/auth/session"),
      });
      persistSession(session, "password");
    },
  });
}

export function useSignup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; email: string; password: string }) => {
      const result = await authClient.signUp.email({
        name: payload.name,
        email: payload.email,
        password: payload.password,
      });
      if (result.error) {
        throw new Error(result.error.message || "Inscription impossible.");
      }
      return result;
    },
    onSuccess: async () => {
      localStorage.setItem(AUTH_PROVIDER_KEY, "password");
      queryClient.invalidateQueries({ queryKey: ["auth-session"] });
      const session = await queryClient.fetchQuery({
        queryKey: ["auth-session"],
        queryFn: () => fetchJson<AuthSession>("/auth/session"),
      });
      persistSession(session, "password");
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const result = await authClient.signOut();
      if (result.error) {
        throw new Error(result.error.message || "Déconnexion impossible.");
      }
      return result;
    },
    onSettled: () => {
      clearStoredSession();
      queryClient.removeQueries({ queryKey: ["auth-session"] });
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { display_name: string }) =>
      fetchJson<AuthSession>("/auth/profile", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: (session) => {
      persistSession(session);
      queryClient.invalidateQueries({ queryKey: ["auth-session"] });
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (payload: { current_password: string; new_password: string }) => {
      const result = await authClient.changePassword({
        currentPassword: payload.current_password,
        newPassword: payload.new_password,
        revokeOtherSessions: true,
      });
      if (result.error) {
        throw new Error(result.error.message || "Impossible de modifier le mot de passe.");
      }
      return result;
    },
  });
}

export function useKPIStats() {
  return useQuery<KPIStats>({
    queryKey: ["kpis"],
    queryFn: () => fetchJson<KPIStats>("/stats/kpi"),
    refetchInterval: 10000,
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

const CF_BASE = "/integrations/cloudflare";

export function useCloudflareStatus() {
  return useQuery<CloudflareStatus>({
    queryKey: ["cf-integration"],
    queryFn: () => fetchJson<CloudflareStatus>(`${CF_BASE}/status`),
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cf-integration"] });
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cf-integration"] });
    },
  });
}

export function useDatasets() {
  return useQuery<Dataset[]>({
    queryKey: ["datasets"],
    queryFn: () => fetchJson<Dataset[]>("/datasets"),
  });
}

export function useRunPipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      fetchJson<{ run_id: string }>("/pipeline/run", {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}
