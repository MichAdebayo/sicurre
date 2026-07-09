import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authBaseURL, authClient } from "./auth-client";

const API_BASE_URL = "/v1";
const USER_NAME_KEY = "sicurre_user_name";
const USER_EMAIL_KEY = "sicurre_user_email";
const USER_ROLE_KEY = "sicurre_user_role";
const AUTH_PROVIDER_KEY = "sicurre_auth_provider";

export type AuthFailureReason =
  | "unknown_account"
  | "invalid_password"
  | "email_taken"
  | "invalid_email"
  | "weak_password"
  | "service_unavailable"
  | "login_failed"
  | "signup_failed";

export class AuthFlowError extends Error {
  readonly reason: AuthFailureReason;

  constructor(reason: AuthFailureReason, fallbackMessage: string) {
    super(fallbackMessage);
    this.name = "AuthFlowError";
    this.reason = reason;
  }
}

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
  sla_latency_ms: number;
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
  verdict: "phishing" | "spam" | "legitimate" | "quarantine";
  confidence: number;
  status: "active" | "trashed" | "restored";
  received_at: string;
  latency_ms?: number;
  explanation?: string;
}

export interface FeedbackPayload {
  event_id?: string;
  feedback_type: "false_negative" | "false_positive" | "true_positive" | "true_negative";
  corrected_verdict: "phishing" | "spam" | "legitimate" | "quarantine";
  reporter_note?: string;
}

export interface AdminOverview {
  summary: {
    workspaces_count: number;
    members_count: number;
    threat_events_count: number;
    feedback_count: number;
    false_negative_count: number;
    quarantine_held_count: number;
    cloudflare_integrations_count: number;
    cloudflare_active_count: number;
  };
  verdicts: { verdict: string; count: number }[];
  feedback_by_type: { feedback_type: string; count: number }[];
  cloudflare_domains: {
    zone_name: string | null;
    status: string | null;
    user_email: string | null;
    updated_at: string | null;
  }[];
  recent_feedback: {
    id: string;
    workspace_id: string;
    feedback_type: string;
    original_verdict: string | null;
    corrected_verdict: string;
    created_at: string;
    reporter_email: string | null;
  }[];
  recent_quarantine: {
    id: string;
    workspace_id: string;
    safety_verdict: string;
    composite_score: number;
    status: string;
    created_at: string;
    expires_at: string;
  }[];
}

export interface AdminRuntimeHealth {
  status: "ok" | "degraded" | "down" | "unknown";
  checked_at: string;
  public_api_host: string | null;
  inference_api_url: string | null;
  expected_worker_scan_url: string | null;
  components: {
    component: string;
    status: "ok" | "degraded" | "down" | "unknown";
    message: string;
    detail: string | null;
    checked_url: string | null;
    latency_ms: number | null;
  }[];
}

export interface CloudflareStatus {
  status: "not_configured" | "provisioning" | "pending_verification" | "active" | "error";
  id?: string;
  user_email?: string;
  zone_name?: string;
  destination_email?: string;
  worker_name?: string;
  api_token?: string | null;
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CloudflareSetupPayload {
  cf_api_token: string;
  zone_name: string;
  destination_email: string;
  fix_spf?: boolean;
  fix_dkim?: boolean;
  fix_dmarc?: boolean;
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

async function checkAuthEmailExists(email: string): Promise<boolean | null> {
  try {
    const response = await fetch(`${authBaseURL}/check-email`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!response.ok) {
      return null;
    }
    const body = await response.json().catch(() => ({}));
    return Boolean(body.exists);
  } catch {
    return null;
  }
}

function normalizeAuthProviderError(
  rawError: unknown,
  fallback: AuthFailureReason,
): AuthFailureReason {
  const errorLike = rawError as { code?: string; message?: string; statusText?: string } | null | undefined;
  const text = `${errorLike?.code ?? ""} ${errorLike?.message ?? ""} ${errorLike?.statusText ?? ""}`.toLowerCase();

  if (text.includes("user already exists") || text.includes("already exist") || text.includes("email already")) {
    return "email_taken";
  }
  if (text.includes("invalid email")) {
    return "invalid_email";
  }
  if (text.includes("password") && (text.includes("short") || text.includes("weak") || text.includes("length"))) {
    return "weak_password";
  }
  if (text.includes("invalid password") || text.includes("invalid email or password")) {
    return "invalid_password";
  }
  if (text.includes("user not found")) {
    return "unknown_account";
  }
  if (text.includes("fetch") || text.includes("network") || text.includes("failed to")) {
    return "service_unavailable";
  }

  return fallback;
}

function createAuthError(reason: AuthFailureReason): AuthFlowError {
  return new AuthFlowError(reason, reason);
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
      const accountExists = await checkAuthEmailExists(payload.email);
      if (accountExists === false) {
        throw createAuthError("unknown_account");
      }

      const result = await authClient.signIn.email({
        email: payload.email,
        password: payload.password,
      });
      if (result.error) {
        const reason = accountExists === true
          ? normalizeAuthProviderError(result.error, "invalid_password")
          : normalizeAuthProviderError(result.error, "login_failed");
        throw createAuthError(reason);
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
      const accountExists = await checkAuthEmailExists(payload.email);
      if (accountExists === true) {
        throw createAuthError("email_taken");
      }

      const result = await authClient.signUp.email({
        name: payload.name,
        email: payload.email,
        password: payload.password,
      });
      if (result.error) {
        throw createAuthError(normalizeAuthProviderError(result.error, "signup_failed"));
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

export function useAdminOverview() {
  return useQuery<AdminOverview>({
    queryKey: ["admin-overview"],
    queryFn: () => fetchJson<AdminOverview>("/admin/overview"),
    refetchInterval: 15000,
  });
}

export function useAdminRuntimeHealth(enabled = true) {
  return useQuery<AdminRuntimeHealth>({
    queryKey: ["admin-runtime-health"],
    queryFn: () => fetchJson<AdminRuntimeHealth>("/admin/runtime-health"),
    enabled,
    refetchInterval: 30000,
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

export function useCreateFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FeedbackPayload) =>
      fetchJson<{ id: string; event_id?: string; feedback_type: string; created_at: string }>("/feedback", {
        method: "POST",
        body: JSON.stringify(payload),
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
      queryClient.invalidateQueries({ queryKey: ["auth-session"] });
      queryClient.invalidateQueries({ queryKey: ["cloudflare-list"] });
      queryClient.invalidateQueries({ queryKey: ["cf-workspace-token"] });
      queryClient.invalidateQueries({ queryKey: ["domain-shield"] });
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
      queryClient.invalidateQueries({ queryKey: ["auth-session"] });
      queryClient.invalidateQueries({ queryKey: ["cloudflare-list"] });
      queryClient.invalidateQueries({ queryKey: ["cf-workspace-token"] });
      queryClient.invalidateQueries({ queryKey: ["domain-shield"] });
    },
  });
}

export function useWorkspaceCloudflareToken() {
  return useQuery<{ api_token: string | null }>({
    queryKey: ["cf-workspace-token"],
    queryFn: () => fetchJson<{ api_token: string | null }>(`${CF_BASE}/token`),
  });
}

export function useSaveWorkspaceCloudflareToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cf_api_token: string) =>
      fetchJson<{ status: string }>(`${CF_BASE}/token`, {
        method: "POST",
        body: JSON.stringify({ cf_api_token }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cf-workspace-token"] });
      queryClient.invalidateQueries({ queryKey: ["cloudflare-list"] });
    },
  });
}

export function useDeleteWorkspaceCloudflareToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      fetchJson<{ status: string }>(`${CF_BASE}/token`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cf-workspace-token"] });
      queryClient.invalidateQueries({ queryKey: ["cf-integration"] });
      queryClient.invalidateQueries({ queryKey: ["auth-session"] });
      queryClient.invalidateQueries({ queryKey: ["cloudflare-list"] });
      queryClient.invalidateQueries({ queryKey: ["domain-shield"] });
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

// ── Quarantine API Types & Hooks ──────────────────────────────────────────────

export interface QuarantineItem {
  id: string;
  message_id: string;
  sender: string;
  subject: string;
  body_text: string;
  safety_verdict: string;
  composite_score: number;
  status: string;
  created_at: string;
  expires_at: string;
}

export function useQuarantineItems() {
  return useQuery<QuarantineItem[]>({
    queryKey: ["quarantine"],
    queryFn: () => fetchJson<QuarantineItem[]>("/quarantine"),
  });
}

export function useReleaseQuarantine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string; forwarded_to: string }>(`/quarantine/${id}/release`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quarantine"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}

export function useDeleteQuarantine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string }>(`/quarantine/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quarantine"] });
    },
  });
}

export function useReleaseAndWhitelist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string; whitelisted_pattern: string }>(`/quarantine/${id}/whitelist`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quarantine"] });
      queryClient.invalidateQueries({ queryKey: ["security-rules"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}

// ── Alerts & Preference API Types & Hooks ─────────────────────────────────────

export interface AlertPreferences {
  notify_phishing: boolean;
  notify_spam: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
}

export function useAlertPreferences() {
  return useQuery<AlertPreferences>({
    queryKey: ["alert-preferences"],
    queryFn: () => fetchJson<AlertPreferences>("/alerts/preferences"),
  });
}

export function useUpdateAlertPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AlertPreferences) =>
      fetchJson<{ status: string }>("/alerts/preferences", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-preferences"] });
    },
  });
}

export interface SecurityRule {
  id: string;
  rule_type: "whitelist" | "blocklist";
  pattern: string;
  created_at: string;
}

export function useSecurityRules() {
  return useQuery<SecurityRule[]>({
    queryKey: ["security-rules"],
    queryFn: () => fetchJson<SecurityRule[]>("/alerts/rules"),
  });
}

export function useCreateSecurityRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { rule_type: string; pattern: string }) =>
      fetchJson<SecurityRule>("/alerts/rules", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-rules"] });
    },
  });
}

export function useDeleteSecurityRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string }>(`/alerts/rules/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-rules"] });
    },
  });
}

export interface AlertHistoryItem {
  id: string;
  title: string;
  message: string;
  created_at: string;
}

export function useAlertHistory() {
  return useQuery<AlertHistoryItem[]>({
    queryKey: ["alert-history"],
    queryFn: () => fetchJson<AlertHistoryItem[]>("/alerts/history"),
    refetchInterval: 10000,
  });
}

export function useDismissAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string }>(`/alerts/history/${id}/dismiss`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-history"] });
    },
  });
}

// ── Connected Domains & Domain Shield Status Types & Hooks ───────────────────

export function useCloudflareList() {
  return useQuery<CloudflareStatus[]>({
    queryKey: ["cloudflare-list"],
    queryFn: () => fetchJson<CloudflareStatus[]>("/integrations/cloudflare/list"),
  });
}

export interface DomainShieldStatus {
  spf: { valid: boolean; record: string | null; error: string | null };
  dkim: { valid: boolean; record: string | null; error: string | null };
  dmarc: { valid: boolean; record: string | null; policy: string; reporting_enabled?: boolean; error: string | null };
  ssl: { valid: boolean; days_remaining: number; auto_renew: boolean; error: string | null };
  reputation_score: number;
  score_grade: string;
  blacklists?: { listed: boolean; matched: string[]; error: string | null };
  updated_at?: string;
}

const domainShieldCacheKey = (domain: string) => `sicurre_domain_shield_status:${domain}`;

function readCachedDomainShieldStatus(domain: string): DomainShieldStatus | undefined {
  if (!domain || typeof window === "undefined") return undefined;
  try {
    const raw = window.localStorage.getItem(domainShieldCacheKey(domain));
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as DomainShieldStatus;
    if (typeof parsed?.reputation_score !== "number" || !parsed?.score_grade) return undefined;
    return parsed;
  } catch {
    window.localStorage.removeItem(domainShieldCacheKey(domain));
    return undefined;
  }
}

function persistDomainShieldStatus(domain: string, status: DomainShieldStatus): void {
  if (!domain || typeof window === "undefined") return;
  window.localStorage.setItem(domainShieldCacheKey(domain), JSON.stringify(status));
}

export interface DmarcReportSummary {
  domain: string;
  total_messages: number;
  aligned_messages: number;
  failed_messages: number;
  report_count: number;
  last_report_at: string | null;
  top_sources: {
    source_ip: string;
    message_count: number;
    disposition: string;
    dkim_result: string;
    spf_result: string;
  }[];
}

export function useDomainShieldStatus(domain: string, enabled = true) {
  return useQuery<DomainShieldStatus>({
    queryKey: ["domain-shield", domain],
    queryFn: async () => {
      const status = await fetchJson<DomainShieldStatus>(`/domain-shield/${domain}/status`);
      persistDomainShieldStatus(domain, status);
      return status;
    },
    enabled: enabled && !!domain,
    initialData: () => readCachedDomainShieldStatus(domain),
    staleTime: 1000 * 60 * 60, // Consider data fresh for 1 hour to prevent unnecessary refetches
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

export function useDmarcReportSummary(domain: string, enabled = true) {
  return useQuery<DmarcReportSummary>({
    queryKey: ["dmarc-reports", domain],
    queryFn: () => fetchJson<DmarcReportSummary>(`/domain-shield/${domain}/dmarc-reports`),
    enabled: enabled && !!domain,
  });
}

export function useRefreshDomainShieldStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (domain: string) =>
      fetchJson<DomainShieldStatus>(`/domain-shield/${domain}/status?refresh=true`),
    onSuccess: (data, domain) => {
      persistDomainShieldStatus(domain, data);
      queryClient.setQueryData(["domain-shield", domain], data);
    },
  });
}
