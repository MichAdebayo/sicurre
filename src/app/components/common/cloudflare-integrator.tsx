import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  Cloud,
  CheckCircle2,
  XCircle,
  Loader2,
  ShieldCheck,
  Mail,
  ExternalLink,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Eye,
  EyeOff,
  Zap,
  HelpCircle,
} from "lucide-react";
import { Input } from "../ui/input";
import { Button } from "../ui/button";
import {
  useCloudflareStatus,
  useVerifyCloudflareToken,
  useSetupCloudflare,
  useTeardownCloudflare,
  type CloudflareStatus,
} from "../../lib/api";

const MotionDiv = motion.div as any;

function formatCloudflareError(t: TFunction, message?: string | null): string {
  if (!message) return t("domain_shield.cloudflare_unknown_error");
  const lower = message.toLowerCase();
  if (lower.includes("zone settings:edit")) {
    return t("domain_shield.cloudflare_zone_settings_permission_error");
  }
  if (lower.includes("dns_records") || lower.includes("dns update failed")) {
    return t("domain_shield.cloudflare_dns_permission_error");
  }
  if (lower.includes("workers/scripts")) {
    return t("domain_shield.cloudflare_worker_permission_error");
  }
  if (lower.includes("email/routing/rules")) {
    return t("domain_shield.cloudflare_routing_permission_error");
  }
  if (lower.includes("email/routing/addresses")) {
    return t("domain_shield.cloudflare_address_permission_error");
  }
  if (lower.includes("authentication error")) {
    return t("domain_shield.cloudflare_scope_error");
  }
  if (lower.includes("zone") && lower.includes("not found")) {
    return t("cloudflare.errors.zone_not_found");
  }
  if (lower.includes("token") && (lower.includes("failed") || lower.includes("invalid"))) {
    return t("cloudflare.errors.invalid_token");
  }
  return message;
}

// ── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const map: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
    not_configured:       { label: t("cloudflare.status_not_configured"), className: "text-on-surface-variant bg-surface-container border-border-subtle", icon: <Cloud className="w-3 h-3" /> },
    provisioning:         { label: t("cloudflare.status_provisioning"), className: "text-amber-600 bg-amber-50 border-amber-200", icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    pending_verification: { label: t("cloudflare.status_pending"), className: "text-amber-600 bg-amber-50 border-amber-200", icon: <Mail className="w-3 h-3" /> },
    active:               { label: t("cloudflare.status_active"), className: "text-safe bg-safe/[0.08] border-safe/20", icon: <Zap className="w-3 h-3" /> },
    error:                { label: t("cloudflare.status_error"), className: "text-error bg-error/[0.06] border-error/20", icon: <XCircle className="w-3 h-3" /> },
  };
  const cfg = map[status] ?? map.not_configured;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.1em] px-2.5 py-1 rounded-full border ${cfg.className}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

// ── Checklist interface ───────────────────────────────────────────────────────

interface IntegrationStage {
  id: string;
  label: string;
  description: string;
  status: "idle" | "loading" | "success" | "error";
  errorMsg?: string;
}

interface CloudflareIntegratorProps {
  userEmail: string;
  onSuccess?: () => void;
}

function integrationStages(
  t: TFunction,
  statuses: IntegrationStage["status"][],
): IntegrationStage[] {
  return (["verify", "dns", "worker", "routing"] as const).map((id, index) => ({
    id,
    label: t(`cloudflare.stage_${id}`),
    description: t(`cloudflare.stage_${id}_desc`),
    status: statuses[index] ?? "idle",
  }));
}

// ── Main component ────────────────────────────────────────────────────────────

export function CloudflareIntegrator({ userEmail, onSuccess }: CloudflareIntegratorProps) {
  const { t } = useTranslation();
  const { data: cfStatus, isLoading: statusLoading, refetch } = useCloudflareStatus();
  const verifyMutation = useVerifyCloudflareToken();
  const setupMutation  = useSetupCloudflare();
  const teardownMutation = useTeardownCloudflare();

  // Controlled form state
  const [cfToken, setCfToken]           = useState("");
  const [showToken, setShowToken]       = useState(false);
  const [zoneName, setZoneName]         = useState("");
  const [showHelp, setShowHelp]         = useState(false);

  // Integration progress state
  const [isIntegrating, setIsIntegrating] = useState(false);
  const [stages, setStages] = useState<IntegrationStage[]>(() =>
    integrationStages(t, ["idle", "idle", "idle", "idle"]),
  );

  // Teardown state
  const [showTeardown, setShowTeardown] = useState(false);

  // Sync background provisioning state with UI progress checklist
  useEffect(() => {
    if (cfStatus?.status === "provisioning" && !isIntegrating) {
      setIsIntegrating(true);
      setStages(integrationStages(t, ["success", "success", "success", "loading"]));
    }
  }, [cfStatus?.status, isIntegrating, t]);

  // React to status completion updates during routing step
  useEffect(() => {
    let timerId: NodeJS.Timeout | undefined;
    if (isIntegrating && stages.find(s => s.id === "routing")?.status === "loading") {
      if (cfStatus?.status === "pending_verification" || cfStatus?.status === "active") {
        setStages(prev => prev.map(s => s.id === "routing" ? { ...s, status: "success" } : s));
        timerId = setTimeout(() => {
          setIsIntegrating(false);
          onSuccess?.();
        }, 1500);
      } else if (cfStatus?.status === "error") {
        setStages(prev => prev.map(s => s.id === "routing" ? { ...s, status: "error", errorMsg: formatCloudflareError(t, cfStatus.error_message || t("cloudflare.final_setup_failed")) } : s));
      }
    }
    return () => {
      if (timerId) clearTimeout(timerId);
    };
  }, [cfStatus?.status, isIntegrating, stages, onSuccess, t]);

  // Poll status ONLY when integrating or provisioning in the background
  useEffect(() => {
    if (!isIntegrating && cfStatus?.status !== "provisioning") return;
    const id = setInterval(() => refetch(), 3000);
    return () => clearInterval(id);
  }, [isIntegrating, cfStatus?.status, refetch]);

  // ── Integration Orchestration ─────────────────────────────────────────────

  const handleIntegrate = async () => {
    if (!cfToken.trim() || !zoneName.trim()) return;

    setIsIntegrating(true);
    setStages(integrationStages(t, ["loading", "idle", "idle", "idle"]));

    try {
      // Step 1: Verify token
      const result = await verifyMutation.mutateAsync({
        cf_api_token: cfToken,
        zone_name: zoneName,
      });

      if (!result.valid) {
        setStages(prev => prev.map(s => s.id === "verify" ? { ...s, status: "error", errorMsg: formatCloudflareError(t, result.error || t("cloudflare.invalid_token_or_domain")) } : s));
        return;
      }

      setStages(prev => prev.map(s =>
        s.id === "verify" ? { ...s, status: "success" } :
        s.id === "dns" ? { ...s, status: "loading" } : s
      ));

      // The backend performs DNS and routing provisioning in the setup call.
      setStages(prev => prev.map(s =>
        s.id === "dns" ? { ...s, status: "success" } :
        s.id === "worker" ? { ...s, status: "loading" } : s
      ));

      // Step 3: Trigger setup
      await setupMutation.mutateAsync({
        cf_api_token: cfToken,
        zone_name: zoneName,
        destination_email: userEmail,
      });

      setStages(prev => prev.map(s =>
        s.id === "worker" ? { ...s, status: "success" } :
        s.id === "routing" ? { ...s, status: "loading" } : s
      ));

      // Step 4: Routing & validation will update via the useEffect watching status changes
      refetch();
    } catch (err: any) {
      setStages(prev => prev.map(s => {
        if (s.status === "loading") {
          return { ...s, status: "error", errorMsg: formatCloudflareError(t, err.message || t("cloudflare.stage_failed")) };
        }
        return s;
      }));
    }
  };

  // ── Teardown ──────────────────────────────────────────────────────────────

  const handleTeardown = async () => {
    if (!cfStatus?.id) return;
    try {
      await teardownMutation.mutateAsync({ integration_id: cfStatus.id });
      setShowTeardown(false);
      refetch();
    } catch {
      // error shown via teardownMutation.error
    }
  };

  const handleRetry = async () => {
    if (!cfStatus?.zone_name || !cfStatus.destination_email) return;
    try {
      await setupMutation.mutateAsync({
        zone_name: cfStatus.zone_name,
        destination_email: cfStatus.destination_email,
      });
      await refetch();
      setIsIntegrating(true);
      setStages(integrationStages(t, ["success", "success", "success", "loading"]));
    } catch {
      await refetch();
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  // Clean, quiet skeleton loader when status is checking for the first time
  if (statusLoading && !cfStatus) {
    return (
      <div className="space-y-6">
        <div className="bg-surface-lowest border border-border-subtle rounded-xl p-5 space-y-4 animate-pulse">
          <div className="h-6 bg-surface-container rounded-md w-1/3" />
          <div className="h-4 bg-surface-container rounded-md w-2/3" />
          <div className="grid grid-cols-1 gap-4">
            <div className="h-10 bg-surface-container rounded-md" />
            <div className="h-10 bg-surface-container rounded-md" />
          </div>
        </div>
        <div className="flex justify-end">
          <div className="h-10 bg-surface-container rounded-md w-32" />
        </div>
      </div>
    );
  }

  const intStatus: CloudflareStatus = cfStatus || { status: "not_configured" };

  // ── INTEGRATING / WIZARD CHECKLIST STATE ────────────────────────────────────
  if (isIntegrating) {
    const activeStage = stages.find(s => s.status === "loading" || s.status === "error");
    const hasError = stages.some(s => s.status === "error");

    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
        <div className="bg-surface-low/30 border border-border-subtle rounded-xl p-5 space-y-5">
          <div>
            <h4 className="font-display font-semibold text-[15px] text-on-surface">{t("cloudflare.progress_title")}</h4>
            <p className="text-xs text-on-surface-variant mt-0.5">
              {t("cloudflare.progress_desc")}
            </p>
          </div>

          <div className="space-y-4">
            {stages.map((stage) => (
              <div key={stage.id} className="flex items-start gap-3.5">
                <div className="mt-0.5 shrink-0">
                  {stage.status === "idle" && (
                    <div className="w-5 h-5 rounded-full border border-border-subtle bg-surface-lowest flex items-center justify-center text-[10px] text-on-surface-variant/40 font-bold" />
                  )}
                  {stage.status === "loading" && (
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                  )}
                  {stage.status === "success" && (
                    <CheckCircle2 className="w-5 h-5 text-safe" />
                  )}
                  {stage.status === "error" && (
                    <XCircle className="w-5 h-5 text-error" />
                  )}
                </div>
                <div className="space-y-0.5">
                  <p className={`text-sm font-semibold ${
                    stage.status === "error" ? "text-error" :
                    stage.status === "loading" ? "text-primary" :
                    stage.status === "success" ? "text-on-surface" : "text-on-surface-variant/60"
                  }`}>
                    {stage.label}
                  </p>
                  <p className="text-xs text-on-surface-variant/70 leading-relaxed">
                    {stage.description}
                  </p>
                  {stage.status === "error" && stage.errorMsg && (
                    <p className="mt-2.5 max-w-xl rounded border border-error/15 bg-error-container/40 px-3 py-2 text-[13px] font-semibold leading-5 text-on-error-container">
                      {stage.errorMsg}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>

          {hasError && (
            <div className="pt-2 border-t border-border-subtle flex gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsIntegrating(false)}
                className="text-[11px]"
              >
                {t("cloudflare.back_to_setup")}
              </Button>
            </div>
          )}
        </div>
      </MotionDiv>
    );
  }

  // ── ACTIVE STATE ──────────────────────────────────────────────────────────
  if (intStatus.status === "active") {
    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
        <div className="flex items-start justify-between gap-4 p-4 bg-safe/[0.05] border border-safe/20 rounded-xl">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-safe/10 rounded-lg flex items-center justify-center border border-safe/20">
              <ShieldCheck className="w-5 h-5 text-safe" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-bold text-sm text-on-surface">{intStatus.zone_name}</span>
                <StatusBadge status="active" />
              </div>
              <p className="text-xs text-on-surface-variant">
                {t("cloudflare.forwarding_to")} <strong>{intStatus.destination_email}</strong>
              </p>
              <p className="text-[10px] text-on-surface-variant/50 font-mono mt-0.5">
                Worker: {intStatus.worker_name}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="p-3 bg-surface-low border border-border-subtle rounded-lg text-center">
            <div className="font-bold text-on-surface text-sm mb-0.5">{t("threats.badge_phishing")}</div>
            <div className="text-on-surface-variant">{t("cloudflare.phishing_action")}</div>
          </div>
          <div className="p-3 bg-surface-low border border-border-subtle rounded-lg text-center">
            <div className="font-bold text-on-surface text-sm mb-0.5">{t("threats.badge_spam")}</div>
            <div className="text-on-surface-variant">{t("cloudflare.spam_action")}</div>
          </div>
          <div className="p-3 bg-surface-low border border-border-subtle rounded-lg text-center">
            <div className="font-bold text-on-surface text-sm mb-0.5">{t("threats.badge_legitimate")}</div>
            <div className="text-on-surface-variant">{t("cloudflare.legitimate_action")}</div>
          </div>
        </div>

        {/* Teardown section */}
        {!showTeardown ? (
          <button
            onClick={() => setShowTeardown(true)}
            className="flex items-center gap-1.5 text-xs text-error/70 hover:text-error transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            {t("cloudflare.disable")}
          </button>
        ) : (
          <div className="p-4 border border-error/20 bg-error/[0.03] rounded-xl space-y-3">
            <p className="text-xs font-semibold text-error">
              {t("cloudflare.disable_desc")}
            </p>
            {teardownMutation.isError && (
              <p className="text-xs text-error">{(teardownMutation.error as Error)?.message}</p>
            )}
            <div className="flex gap-2">
              <Button
                variant="danger"
                size="sm"
                onClick={handleTeardown}
                disabled={!intStatus.id || teardownMutation.isPending}
                className="gap-1.5 text-[11px]"
              >
                {teardownMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                {t("cloudflare.confirm_disable")}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowTeardown(false)} className="text-[11px]">
                {t("common.cancel")}
              </Button>
            </div>
          </div>
        )}
      </MotionDiv>
    );
  }

  // ── PENDING VERIFICATION ──────────────────────────────────────────────────
  if (intStatus.status === "pending_verification") {
    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl">
          <Mail className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-bold text-sm text-amber-800 mb-1">{t("cloudflare.verify_email")}</p>
            <p className="text-xs text-amber-700">
              {t("cloudflare.verify_email_desc")}{" "}
              <strong>{intStatus.destination_email}</strong>.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-on-surface-variant">
            {t("cloudflare.zone")} <strong>{intStatus.zone_name}</strong> · Worker: <code className="font-mono text-[10px] bg-surface-container px-1 rounded">{intStatus.worker_name}</code>
          </div>
          <StatusBadge status="pending_verification" />
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 text-xs text-primary hover:text-primary-dark transition-colors cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {t("cloudflare.refresh_status")}
        </button>
        {!showTeardown ? (
          <button onClick={() => setShowTeardown(true)} className="flex items-center gap-1.5 text-xs text-error/70 hover:text-error transition-colors cursor-pointer">
            <Trash2 className="w-3.5 h-3.5" /> {t("cloudflare.cancel_and_delete")}
          </button>
        ) : (
          <div className="p-4 border border-error/20 bg-error/[0.03] rounded-xl space-y-3">
            <p className="text-xs font-semibold text-error">
              {t("cloudflare.disable_desc")}
            </p>
            <div className="flex gap-2">
              <Button variant="danger" size="sm" onClick={handleTeardown} disabled={!intStatus.id || teardownMutation.isPending} className="gap-1.5 text-[11px]">
                {teardownMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                {t("cloudflare.delete")}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowTeardown(false)} className="text-[11px]">{t("common.cancel")}</Button>
            </div>
          </div>
        )}
      </MotionDiv>
    );
  }

  // ── ERROR STATE ───────────────────────────────────────────────────────────
  if (intStatus.status === "error") {
    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-error/[0.04] border border-error/20 rounded-xl">
          <AlertTriangle className="w-5 h-5 text-error shrink-0 mt-0.5" />
          <div>
            <p className="font-bold text-sm text-error mb-1">{t("cloudflare.provisioning_failed")}</p>
            <p className="text-[13px] leading-5 text-on-error-container">{formatCloudflareError(t, intStatus.error_message)}</p>
          </div>
        </div>
        <p className="text-[13px] text-on-surface-variant">{t("cloudflare.check_permissions")}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRetry}
          disabled={setupMutation.isPending}
          className="gap-1.5 text-[11px]"
        >
          {setupMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} {t("common.retry")}
        </Button>
      </MotionDiv>
    );
  }

  // ── WIZARD / INPUT FORM STATE (not_configured) ─────────────────────────────
  const isFormValid = cfToken.trim() !== "" && zoneName.trim() !== "";

  return (
    <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="bg-surface-low/30 border border-border-subtle rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 relative">
          <h4 className="font-display font-semibold text-[15px] text-on-surface">{t("cloudflare.configure")}</h4>
          <div
            className="relative inline-block"
            onMouseEnter={() => setShowHelp(true)}
            onMouseLeave={() => setShowHelp(false)}
          >
            <button
              type="button"
              onClick={() => setShowHelp(v => !v)}
              className="text-on-surface-variant/50 hover:text-primary transition-colors cursor-help p-0.5 rounded-full hover:bg-surface-low/50 flex items-center justify-center outline-none"
              aria-label={t("cloudflare.setup_help")}
            >
              <HelpCircle className="w-3.5 h-3.5" />
            </button>
            <AnimatePresence>
              {showHelp && (
                <MotionDiv
                  initial={{ opacity: 0, y: 8, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 8, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute left-6 -top-2 z-30 w-72 bg-white border border-border-subtle p-4 rounded-xl shadow-lg text-[11px] text-on-surface-variant/80 space-y-1.5 leading-normal"
                >
                  <p className="font-bold text-on-surface">{t("cloudflare.token_help_title")}</p>
                  <p>1. {t("cloudflare.token_help_login")} <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noreferrer" className="text-primary underline inline-flex items-center gap-0.5 font-semibold">dash.cloudflare.com <ExternalLink className="w-3 h-3" /></a>.</p>
                  <p>2. {t("cloudflare.token_help_permissions")}</p>
                  <ul className="list-disc pl-4 space-y-0.5 mt-1 font-medium text-on-surface">
                    <li>Zone › DNS › Edit</li>
                    <li>Workers Scripts › Edit</li>
                    <li>Email Routing › Edit</li>
                  </ul>
                </MotionDiv>
              )}
            </AnimatePresence>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 pt-2">
          <div>
            <Input
              label={t("cloudflare.api_token")}
              type={showToken ? "text" : "password"}
              value={cfToken}
              onChange={e => setCfToken(e.target.value)}
              placeholder={t("cloudflare.api_token_placeholder")}
              suffix={
                <button type="button" onClick={() => setShowToken(v => !v)} className="text-on-surface-variant/60 hover:text-on-surface transition-colors cursor-pointer">
                  {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              }
            />
          </div>

          <div>
            <Input
              label={t("cloudflare.domain")}
              type="text"
              value={zoneName}
              onChange={e => setZoneName(e.target.value.trim().toLowerCase())}
              placeholder={t("cloudflare.domain_placeholder")}
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <Button
          onClick={handleIntegrate}
          disabled={!isFormValid || verifyMutation.isPending || setupMutation.isPending}
          className="w-full sm:w-auto text-xs font-bold cursor-pointer"
        >
          {verifyMutation.isPending || setupMutation.isPending
            ? t("cloudflare.integrating")
            : t("cloudflare.integrate")}
        </Button>
      </div>
    </MotionDiv>
  );
}
