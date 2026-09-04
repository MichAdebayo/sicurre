import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authBaseURL, authClient } from "./auth-client";
import { isReusableDomainShieldStatus } from "./domain-shield-cache";

const API_BASE_URL = "/v1";
const USER_NAME_KEY = "sicurre_user_name";
const USER_EMAIL_KEY = "sicurre_user_email";
const USER_ROLE_KEY = "sicurre_user_role";
const AUTH_PROVIDER_KEY = "sicurre_auth_provider";

export type AuthFailureReason =
  | "unknown_account"
  | "invalid_password"
  | "invalid_credentials"
  | "email_unverified"
  | "email_taken"
  | "invalid_email"
  | "weak_password"
  | "bot_verification_required"
  | "bot_verification_failed"
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
  domain: string;
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
  /** Model that produced this verdict. Absent when a blocklist rule decided it
   *  without consulting the model, or for events predating identity capture. */
  model_version?: string | null;
  model_revision?: string | null;
  privacy_reference: string;
  content_redacted: boolean;
}

export interface ThreatPage {
  items: ThreatLog[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface ThreatQuery {
  page?: number;
  pageSize?: number;
  verdict?: "all" | "phishing" | "spam" | "legitimate";
  dateRange?: "all" | "today" | "7d" | "month" | "last_month";
  search?: string;
  hidden?: boolean;
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
    reported_email_count: number;
    quarantine_held_count: number;
    cloudflare_integrations_count: number;
    cloudflare_active_count: number;
    support_open_count: number;
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
  recent_support: {
    id: string;
    workspace_id: string;
    requester_email: string;
    category: string;
    status: string;
    created_at: string;
  }[];
}

export interface AdminDomainPage {
  items: AdminOverview["cloudflare_domains"];
  page: number;
  page_size: number;
  total: number;
  pages: number;
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

export type OperationalExerciseType = "api_unavailable" | "high_latency" | "elevated_5xx";

export interface OperationalExercise {
  id: string;
  exercise_type: OperationalExerciseType;
  initiated_by: string;
  started_at: string;
  expires_at: string;
  status?: "active" | "recovered";
  recovered_at?: string | null;
}

export interface OperationalExerciseState {
  enabled: boolean;
  active: OperationalExercise | null;
  recent: OperationalExercise[];
  supported_types: OperationalExerciseType[];
}

export interface CloudflareStatus {
  status: "not_configured" | "provisioning" | "pending_verification" | "active" | "error";
  id?: string;
  user_email?: string;
  zone_name?: string;
  destination_email?: string;
  worker_name?: string;
  token_configured?: boolean;
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CloudflareSetupPayload {
  cf_api_token?: string;
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
  integration_id: string;
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

/**
 * Preferences that describe the device, not the tenant. These survive logout
 * because clearing them would reset the person's theme and language every time
 * they sign out, and none of them says anything about who was signed in.
 */
const DEVICE_PREFERENCE_KEYS = new Set([
  "sicurre_theme",
  "sicurre_lang",
  "sicurre_rail_collapsed",
]);

/**
 * Remove everything the signed-in session put in browser storage.
 *
 * This sweeps by prefix rather than naming keys. Several are named after the
 * data they hold — `sicurre:active-domain:<workspaceId>`,
 * `sicurre:kpis:<workspaceId>:<domain>`, `sicurre_domain_shield_status:<domain>`
 * — so they cannot be listed ahead of time, and the previous version removed
 * four fixed keys and left the rest behind. After logout a shared browser still
 * held the domain the previous user managed, that domain's SPF/DKIM/DMARC
 * posture, their threat counts and their workspace id.
 *
 * Sweeping also means a tenant-scoped key added later is cleared without anyone
 * remembering to update this function, which is the failure the fixed list had.
 */
export function clearStoredSession(): void {
  for (const store of [localStorage, sessionStorage]) {
    try {
      const doomed = Object.keys(store).filter(
        (key) => key.startsWith("sicurre") && !DEVICE_PREFERENCE_KEYS.has(key),
      );
      for (const key of doomed) store.removeItem(key);
    } catch {
      // Storage can be unavailable (private mode, blocked site data). Losing
      // the sweep must not stop the sign-out that is already in progress.
    }
  }
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");

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

function normalizeAuthProviderError(
  rawError: unknown,
  fallback: AuthFailureReason,
): AuthFailureReason {
  const errorLike = rawError as { code?: string; message?: string; statusText?: string } | null | undefined;
  const text = `${errorLike?.code ?? ""} ${errorLike?.message ?? ""} ${errorLike?.statusText ?? ""}`.toLowerCase();

  if (text.includes("user already exists") || text.includes("already exist") || text.includes("email already")) {
    return "email_taken";
  }
  if (text.includes("invalid email or password")) return "invalid_credentials";
  if (text.includes("email_not_verified") || text.includes("email not verified")) {
    return "email_unverified";
  }
  if (text.includes("invalid email")) return "invalid_email";
  if (text.includes("password") && (text.includes("short") || text.includes("weak") || text.includes("length"))) {
    return "weak_password";
  }
  if (text.includes("invalid password")) {
    return "invalid_password";
  }
  if (text.includes("user not found")) {
    return "invalid_credentials";
  }
  if (text.includes("turnstile_required")) {
    return "bot_verification_required";
  }
  if (text.includes("turnstile_failed")) {
    return "bot_verification_failed";
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
      const result = await authClient.signIn.email({
        email: payload.email,
        password: payload.password,
      });
      if (result.error) {
        throw createAuthError(normalizeAuthProviderError(result.error, "invalid_credentials"));
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
  return useMutation({
    mutationFn: async (payload: { name: string; email: string; password: string; turnstileToken?: string }) => {
      const result = await authClient.signUp.email({
        name: payload.name,
        email: payload.email,
        password: payload.password,
        // Verification returns to sign-in; signup does not create a session.
        callbackURL: `${window.location.origin}/?verified=1`,
        fetchOptions: payload.turnstileToken
          ? { headers: { "x-turnstile-token": payload.turnstileToken } }
          : undefined,
      });
      if (result.error) {
        throw createAuthError(normalizeAuthProviderError(result.error, "signup_failed"));
      }
      return result;
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const response = await fetch(`${authBaseURL}/sign-out`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!response.ok) {
        throw new Error("Déconnexion impossible.");
      }
      return response.json() as Promise<{ success: boolean }>;
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

function readCachedKpis(workspaceId: string, domain: string): KPIStats | undefined {
  if (!workspaceId || typeof window === "undefined") return undefined;
  try {
    const raw = window.sessionStorage.getItem(`sicurre:kpis:${workspaceId}:${domain}`);
    return raw ? (JSON.parse(raw) as KPIStats) : undefined;
  } catch {
    return undefined;
  }
}

export function useKPIStats(workspaceId: string, domain: string) {
  return useQuery<KPIStats>({
    queryKey: ["kpis", workspaceId, domain],
    queryFn: async () => {
      const data = await fetchJson<KPIStats>(`/stats/kpi?domain=${encodeURIComponent(domain)}`);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(`sicurre:kpis:${workspaceId}:${domain}`, JSON.stringify(data));
      }
      return data;
    },
    initialData: () => readCachedKpis(workspaceId, domain),
    enabled: !!domain,
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
  });
}

export function useAdminOverview() {
  return useQuery<AdminOverview>({
    queryKey: ["admin-overview"],
    queryFn: () => fetchJson<AdminOverview>("/admin/overview"),
    retry: false,
    refetchInterval: (query) => query.state.status === "error" ? false : 60000,
    refetchIntervalInBackground: false,
  });
}

export function useAdminDomains(page: number, search: string, enabled = true) {
  const params = new URLSearchParams({ page: String(page), page_size: "20", search });
  return useQuery<AdminDomainPage>({
    queryKey: ["admin-domains", page, search],
    queryFn: () => fetchJson<AdminDomainPage>(`/admin/domains?${params.toString()}`),
    enabled,
    placeholderData: (previous) => previous,
  });
}

export function useAdminRuntimeHealth(enabled = true) {
  return useQuery<AdminRuntimeHealth>({
    queryKey: ["admin-runtime-health"],
    queryFn: () => fetchJson<AdminRuntimeHealth>("/admin/runtime-health"),
    enabled,
    retry: false,
    refetchInterval: (query) => query.state.status === "error" ? false : 60000,
    refetchIntervalInBackground: false,
  });
}

export function useOperationalExercises(enabled = true) {
  return useQuery<OperationalExerciseState>({
    queryKey: ["admin-operational-exercises"],
    queryFn: () => fetchJson<OperationalExerciseState>("/admin/operational-exercises"),
    enabled,
    retry: false,
    refetchInterval: (query) => query.state.status === "error" ? false : query.state.data?.active ? 5000 : 30000,
    refetchIntervalInBackground: false,
  });
}

export function useStartOperationalExercise() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { exercise_type: OperationalExerciseType; duration_seconds: number }) =>
      fetchJson<OperationalExercise>("/admin/operational-exercises", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-operational-exercises"] }),
  });
}

export function useRecoverOperationalExercise() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (exerciseId: string) =>
      fetchJson<OperationalExercise>(`/admin/operational-exercises/${exerciseId}/recover`, {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-operational-exercises"] }),
  });
}

export function useThreatPage(domain: string, query: ThreatQuery = {}) {
  const params = new URLSearchParams({
    page: String(query.page ?? 1),
    page_size: String(query.pageSize ?? 10),
    verdict: query.verdict ?? "all",
    date_range: query.dateRange ?? "all",
    search: query.search ?? "",
    hidden: String(query.hidden ?? false),
    domain,
  });
  return useQuery<ThreatPage>({
    queryKey: ["threats", domain, query],
    queryFn: () => fetchJson<ThreatPage>(`/threats?${params.toString()}`),
    enabled: !!domain,
    placeholderData: (previous) => previous,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
}

export function useThreatLogs(domain: string) {
  return useQuery<ThreatLog[]>({
    queryKey: ["threats", domain, "recent"],
    queryFn: async () => (await fetchJson<ThreatPage>(`/threats?page=1&page_size=100&date_range=all&domain=${encodeURIComponent(domain)}`)).items,
    enabled: !!domain,
    placeholderData: (previous) => previous,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
}

export function useSetThreatVisibility(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { ids: string[]; hidden: boolean }) =>
      fetchJson<{ updated: number; hidden: boolean }>(`/threats/visibility?domain=${encodeURIComponent(domain)}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["threats"] }),
  });
}

export function useReportAddress() {
  return useQuery<{ address: string }>({
    queryKey: ["feedback-report-address"],
    queryFn: () => fetchJson<{ address: string }>("/feedback/report-address"),
    staleTime: 5 * 60 * 1000,
  });
}

export interface ReportedEmailSummary {
  id: string;
  received_at: string;
  size_bytes: number;
  status: string;
}

/**
 * Forwarded false-negative reports for the signed-in workspace.
 *
 * Metadata only by design: the ingest pipeline anonymises the message into
 * private R2 so the forwarded content stops circulating, and the endpoint
 * returns nothing that would put it back on screen.
 */
export function useReportedEmails() {
  return useQuery<{ items: ReportedEmailSummary[] }>({
    queryKey: ["feedback-reports"],
    queryFn: () => fetchJson<{ items: ReportedEmailSummary[] }>("/feedback/reports"),
    staleTime: 60 * 1000,
  });
}

export function useUpdateThreatStatus(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "trashed" | "restored" | "active" }) =>
      fetchJson<ThreatLog>(`/threats/${id}/status?domain=${encodeURIComponent(domain)}`, {
        method: "POST",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threats"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}

export function useCreateFeedback(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FeedbackPayload) =>
      fetchJson<{ id: string; event_id?: string; feedback_type: string; created_at: string }>(`/feedback?domain=${encodeURIComponent(domain)}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threats"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}

export function useCreateSupportRequest() {
  return useMutation({
    mutationFn: (payload: {
      requester_name: string;
      requester_email: string;
      category: string;
      message: string;
    }) =>
      fetchJson<{ id: string; status: string; created_at: string }>("/support/requests", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
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
  return useQuery<{ configured: boolean }>({
    queryKey: ["cf-workspace-token"],
    queryFn: () => fetchJson<{ configured: boolean }>(`${CF_BASE}/token`),
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

export function useDatasets(enabled = true) {
  return useQuery<Dataset[]>({
    queryKey: ["datasets"],
    queryFn: () => fetchJson<Dataset[]>("/datasets"),
    enabled,
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
  domain: string;
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

export function useQuarantineItems(domain: string) {
  return useQuery<QuarantineItem[]>({
    queryKey: ["quarantine", domain],
    queryFn: () => fetchJson<QuarantineItem[]>(`/quarantine?domain=${encodeURIComponent(domain)}`),
    enabled: !!domain,
  });
}

export function useReleaseQuarantine(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string; forwarded_to: string }>(`/quarantine/${id}/release?domain=${encodeURIComponent(domain)}`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quarantine"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
    },
  });
}

export function useDeleteQuarantine(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string }>(`/quarantine/${id}?domain=${encodeURIComponent(domain)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quarantine"] });
    },
  });
}

export function useReleaseAndWhitelist(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string; whitelisted_pattern: string }>(`/quarantine/${id}/whitelist?domain=${encodeURIComponent(domain)}`, {
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
  domain: string;
  email_enabled: boolean;
  notify_phishing: boolean;
  notify_domain_shield: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  timezone: string;
}

export function useAlertPreferences(domain: string) {
  return useQuery<AlertPreferences>({
    queryKey: ["alert-preferences", domain],
    queryFn: () => fetchJson<AlertPreferences>(`/alerts/preferences?domain=${encodeURIComponent(domain)}`),
    enabled: !!domain,
  });
}

export function useUpdateAlertPreferences(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Omit<AlertPreferences, "domain">) =>
      fetchJson<{ status: string }>(`/alerts/preferences?domain=${encodeURIComponent(domain)}`, {
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
  domain: string;
  rule_type: "whitelist" | "blocklist";
  pattern: string;
  created_at: string;
}

export function useSecurityRules(domain: string) {
  return useQuery<SecurityRule[]>({
    queryKey: ["security-rules", domain],
    queryFn: () => fetchJson<SecurityRule[]>(`/alerts/rules?domain=${encodeURIComponent(domain)}`),
    enabled: !!domain,
  });
}

export function useCreateSecurityRule(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { rule_type: string; pattern: string }) =>
      fetchJson<SecurityRule>(`/alerts/rules?domain=${encodeURIComponent(domain)}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-rules"] });
    },
  });
}

export function useDeleteSecurityRule(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string }>(`/alerts/rules/${id}?domain=${encodeURIComponent(domain)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-rules"] });
    },
  });
}

export interface AlertHistoryItem {
  id: string;
  domain: string;
  event_type: string;
  action_page: string | null;
  title: string;
  message: string;
  created_at: string;
  is_read: boolean;
}

export function useAlertHistory(domain: string) {
  return useQuery<AlertHistoryItem[]>({
    queryKey: ["alert-history", domain],
    queryFn: () => fetchJson<AlertHistoryItem[]>(`/alerts/history?domain=${encodeURIComponent(domain)}`),
    enabled: !!domain,
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
  });
}

export function useDismissAlert(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetchJson<{ status: string }>(`/alerts/history/${id}/dismiss?domain=${encodeURIComponent(domain)}`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-history"] });
    },
  });
}

export function useMarkDomainAlertsRead(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => fetchJson<{ status: string }>(`/alerts/history/read?domain=${encodeURIComponent(domain)}`, {
      method: "POST",
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alert-history", domain] }),
  });
}

export function useMarkAlertRead(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => fetchJson<{ status: string }>(
      `/alerts/history/${id}/read?domain=${encodeURIComponent(domain)}`,
      { method: "POST" },
    ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alert-history", domain] }),
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
    if (!isReusableDomainShieldStatus(parsed)) return undefined;
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

export interface DmarcImportResult {
  status: "imported" | "already_imported";
  record_count: number;
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

export function useImportDmarcReport(domain: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => fetchJson<DmarcImportResult>(
      `/domain-shield/${domain}/dmarc-reports/import`,
      {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      },
    ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dmarc-reports", domain] }),
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
