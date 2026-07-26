import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  ShieldCheck,
  ShieldAlert,
  Copy,
  Check,
  BadgeCheck,
  RefreshCw,
  AlertTriangle,
  Globe,
  Lock,
  Skull,
  ArrowRight,
  Info,
  Terminal,
  Zap,
  HelpCircle,
  FileCheck,
  BarChart3,
  Lock as LockIcon,
  Server,
  Activity,
  MousePointerClick,
  Mouse,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  useCloudflareList,
  useDomainShieldStatus,
  useSetupCloudflare,
  useRefreshDomainShieldStatus,
  useWorkspaceCloudflareToken,
  useDmarcReportSummary,
  useCloudflareStatus,
  AuthSession,
} from "../lib/api";
import { AppToast } from "../components/common/app-toast";

const MotionDiv = motion.div as any;

interface DomainShieldRouteProps {
  session?: AuthSession;
}

export default function DomainShieldRoute({ session }: DomainShieldRouteProps) {
  const { t } = useTranslation();

  // Load configured cloudflare domains
  const { data: domainsList, isLoading: domainsLoading } = useCloudflareList();
  const [selectedDomain, setSelectedDomain] = useState("");

  // Select first active domain by default once list loads
  useEffect(() => {
    if (domainsList && domainsList.length > 0) {
      const activeZone = domainsList.find((d) => d.status === "active") || domainsList[0];
      if (activeZone?.zone_name) {
        setSelectedDomain(activeZone.zone_name);
      }
    }
  }, [domainsList]);

  // Query DNS Shield metrics
  const {
    data: shieldStatus,
    isLoading: shieldLoading,
    error: shieldError,
  } = useDomainShieldStatus(selectedDomain, !!selectedDomain);
  const {
    data: dmarcReports,
    isLoading: dmarcReportsLoading,
    isError: dmarcReportsFailed,
    refetch: refetchDmarcReports,
  } = useDmarcReportSummary(selectedDomain, !!selectedDomain);
  const { refetch: refetchCloudflareStatus } = useCloudflareStatus();

  const refreshShieldMutation = useRefreshDomainShieldStatus();

  const hasRestrictiveDmarcPolicy = shieldStatus?.dmarc?.policy === "reject" || shieldStatus?.dmarc?.policy === "quarantine";
  const hasSicurreDmarcReporting = !!shieldStatus?.dmarc?.reporting_enabled || !!(shieldStatus?.dmarc?.record || "").includes("dmarc@sicurre.com");
  const isDmarcValid = !!(shieldStatus?.dmarc?.valid && hasRestrictiveDmarcPolicy);
  const isDmarcComplete = isDmarcValid && hasSicurreDmarcReporting;
  const needsDnsSetup = !!(shieldStatus && (!shieldStatus.spf.valid || !shieldStatus.dkim.valid || !isDmarcValid || !hasSicurreDmarcReporting));
  const isShieldLoading = shieldLoading || refreshShieldMutation.isPending;

  const handleManualRefresh = async () => {
    if (!selectedDomain) return;
    try {
      await refreshShieldMutation.mutateAsync(selectedDomain);
      if (typeof window !== "undefined") {
        sessionStorage.removeItem(`diagnosed_${selectedDomain}`);
      }
      runStepDiagnostics();
    } catch (err) {
      setSuccessNotification(null);
      setErrorNotification(
        err instanceof Error && err.message
          ? err.message
          : t("domain_shield.refresh_failed")
      );
    }
  };

  // Clipboard copy handlers
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const getRecommendedDmarcRecord = () => {
    const activeRecord = shieldStatus?.dmarc?.record || "";
    if (activeRecord.includes("dmarc@sicurre.com")) {
      return activeRecord;
    }
    if (!activeRecord) {
      return "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com";
    }
    if (activeRecord.includes("rua=")) {
      const withPolicy = activeRecord.replace(/p=[^;]+/, "p=reject");
      return withPolicy.replace(/(rua=[^;]+)/, "$1,mailto:dmarc@sicurre.com");
    }
    const base = activeRecord.endsWith(";") ? activeRecord.trim() : `${activeRecord.trim()};`;
    return `${base} rua=mailto:dmarc@sicurre.com`;
  };

  const handleCopy = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };



  // State for Mock DNS Resolver Stepped Progress
  const [isTerminalRunning, setIsTerminalRunning] = useState(false);
  const diagnosticIntervalRef = useRef<any>(null);
  const sessionKey = `diagnosed_${selectedDomain}`;
  const [activeStepIndex, setActiveStepIndex] = useState(() => {
    if (typeof window !== "undefined" && sessionStorage.getItem(sessionKey)) {
      return 5;
    }
    return -1;
  });

  useEffect(() => {
    return () => {
      if (diagnosticIntervalRef.current) {
        clearInterval(diagnosticIntervalRef.current);
      }
    };
  }, []);

  const runStepDiagnostics = () => {
    if (!selectedDomain || !shieldStatus) return;

    if (diagnosticIntervalRef.current) {
      clearInterval(diagnosticIntervalRef.current);
    }

    setIsTerminalRunning(true);
    setActiveStepIndex(0);

    let currentStep = 0;
    diagnosticIntervalRef.current = setInterval(() => {
      currentStep++;
      setActiveStepIndex(currentStep);
      if (currentStep >= 5) {
        clearInterval(diagnosticIntervalRef.current);
        diagnosticIntervalRef.current = null;
        setIsTerminalRunning(false);
        if (typeof window !== "undefined") {
          sessionStorage.setItem(sessionKey, "true");
        }
      }
    }, 1000);
  };

  // Run diagnostics automatically when status loads/changes for domain (session-preserved)
  useEffect(() => {
    if (shieldStatus && selectedDomain && !isShieldLoading) {
      const diagnosedBefore = typeof window !== "undefined" && sessionStorage.getItem(sessionKey);
      if (!diagnosedBefore) {
        runStepDiagnostics();
      } else {
        setActiveStepIndex(5);
      }
    }
  }, [shieldStatus, selectedDomain, isShieldLoading]);

  // Workspace Cloudflare API token query
  const { data: wsTokenData } = useWorkspaceCloudflareToken();

  // State for Cloudflare Auto-Fix Wizard
  const [autoFixProgress, setAutoFixProgress] = useState<"idle" | "verify" | "dns" | "routing" | "success" | "error">("idle");
  const [autoFixErrorMsg, setAutoFixErrorMsg] = useState("");
  const [fixSpf, setFixSpf] = useState(true);
  const [fixDkim, setFixDkim] = useState(true);
  const [fixDmarc, setFixDmarc] = useState(true);
  const setupMutation = useSetupCloudflare();

  const [successNotification, setSuccessNotification] = useState<string | null>(null);
  const [errorNotification, setErrorNotification] = useState<string | null>(null);
  const isAutoFixRunning = autoFixProgress !== "idle" && autoFixProgress !== "success" && autoFixProgress !== "error";

  const getAutoFixButtonText = () => {
    if (autoFixProgress === "verify") {
      return t("domain_shield.autofix_verifying");
    }
    if (autoFixProgress === "dns") {
      return t("domain_shield.autofix_writing_dns");
    }
    if (autoFixProgress === "routing") {
      return t("domain_shield.autofix_routing");
    }
    if (autoFixProgress === "success") {
      return t("domain_shield.autofix_applied");
    }
    if (autoFixProgress === "error") {
      return t("domain_shield.autofix_failed");
    }
    return t("domain_shield.autofix_launch");
  };

  const handleRunAutoFix = async () => {
    if (!wsTokenData?.configured) {
      setSuccessNotification(null);
      setErrorNotification(t("domain_shield.cloudflare_required"));
      return;
    }

    if (!selectedDomain) return;

    setAutoFixProgress("verify");
    setAutoFixErrorMsg("");
    setSuccessNotification(null);
    setErrorNotification(null);

    try {
      const payload = {
        zone_name: selectedDomain,
        destination_email: session?.email || "owner@sicurre.com",
        fix_spf: fixSpf,
        fix_dkim: fixDkim,
        fix_dmarc: fixDmarc
      };

      setAutoFixProgress("dns");
      const result = await setupMutation.mutateAsync(payload);
      setAutoFixProgress(result.status === "provisioning" ? "routing" : "success");

      setSuccessNotification(
        result.status === "provisioning"
          ? t("domain_shield.setup_started")
          : t("domain_shield.setup_applied")
      );

      let finalStatus = result.status;
      for (let attempt = 0; finalStatus === "provisioning" && attempt < 15; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const statusResult = await refetchCloudflareStatus();
        finalStatus = statusResult.data?.status || finalStatus;
        if (finalStatus === "error") {
          throw new Error(statusResult.data?.error_message || t("cloudflare.final_setup_failed"));
        }
      }

      if (finalStatus === "active" || finalStatus === "pending_verification") {
        setAutoFixProgress("success");
        await refreshShieldMutation.mutateAsync(selectedDomain);
        setSuccessNotification(t("domain_shield.setup_applied"));
      } else {
        setAutoFixProgress("routing");
        setSuccessNotification(t("domain_shield.setup_in_progress"));
      }

    } catch (err: any) {
      setAutoFixProgress("error");
      const rawMsg = err.message || "";
      const msg = rawMsg.includes("Authentication error") || rawMsg.includes("Cloudflare DNS update failed")
        ? t("domain_shield.cloudflare_dns_permission_error")
        : rawMsg || t("domain_shield.setup_initialization_failed");
      setAutoFixErrorMsg(msg);
      setSuccessNotification(null);
      setErrorNotification(msg);
    }
  };

  const getDmarcPolicyClass = (policy?: string) => {
    if (policy === "reject") return "text-safe bg-safe/10 border-safe/25";
    if (policy === "quarantine") return "text-primary bg-primary/10 border-primary/25";
    return "text-warning bg-warning/10 border-warning/25";
  };

  return (
    <>
      <AppToast
        tone="success"
        message={successNotification || ""}
        visible={!!successNotification}
        onClose={() => {
          setSuccessNotification(null);
          setAutoFixProgress("idle");
        }}
      />
      <AppToast
        tone="error"
        message={errorNotification || ""}
        visible={!!errorNotification}
        onClose={() => {
          setErrorNotification(null);
          setAutoFixProgress("idle");
        }}
      />

      <MotionDiv
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -12 }}
        transition={{ duration: 0.3 }}
        className="space-y-8 animate-in fade-in duration-200"
      >
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
          <div>
            <h1 className="app-h1">
              {t("domain_shield.title")}
            </h1>
            <p className="app-body-sub mt-1">
              {t("domain_shield.subtitle")}
            </p>
          </div>

          {/* Domain Selection dropdown */}
          <div className="flex items-center gap-3">
            {domainsLoading ? (
              <div className="h-10 w-48 bg-surface-low rounded-lg animate-pulse" />
            ) : !domainsList || domainsList.length === 0 ? (
              <span className="text-xs text-on-surface-variant/70 italic">
                {t("domain_shield.no_domains")}
              </span>
            ) : (
              <select
                value={selectedDomain}
                onChange={(e) => setSelectedDomain(e.target.value)}
                className="px-3.5 py-2 bg-surface-lowest border border-border-subtle rounded-lg text-sm text-on-surface-variant font-bold focus:outline-none focus:border-primary transition-all cursor-pointer shadow-sm h-[38px]"
              >
                {domainsList.map((d) => (
                  <option key={d.id} value={d.zone_name}>
                    {d.zone_name}
                  </option>
                ))}
              </select>
            )}

            {selectedDomain && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleManualRefresh}
                disabled={isShieldLoading}
                className="p-2 min-h-[38px] flex items-center justify-center cursor-pointer bg-white"
              >
                <RefreshCw className={`w-4 h-4 ${isShieldLoading ? "animate-spin text-primary" : ""}`} />
              </Button>
            )}
          </div>
        </div>

        {!selectedDomain ? (
          <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-12 text-center text-on-surface-variant/50 max-w-lg mx-auto flex flex-col items-center justify-center shadow-sm">
            <Globe className="w-12 h-12 text-on-surface-variant/30 mb-3 animate-pulse" />
            <p className="font-bold text-base text-on-surface">
              {t("domain_shield.no_active_shield")}
            </p>
            <p className="text-sm mt-1 text-on-surface-variant">
              {t("domain_shield.no_active_shield_desc")}
            </p>
          </div>
        ) : (shieldLoading && !shieldStatus) ? (
          <div className="space-y-6">
            <div className="h-44 bg-surface-low rounded-2xl animate-pulse" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="h-32 bg-surface-low rounded-2xl animate-pulse" />
              <div className="h-32 bg-surface-low rounded-2xl animate-pulse" />
            </div>
          </div>
        ) : shieldError || !shieldStatus ? (
          <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-8 text-center text-on-surface flex flex-col items-center justify-center max-w-md mx-auto">
            <ShieldAlert className="w-10 h-10 text-error mb-3" />
            <p className="font-bold text-sm">{t("common.error_occurred")}</p>
            <p className="text-xs text-on-surface-variant mt-1 font-semibold">
              {t("domain_shield.fetch_failed")}
            </p>
          </div>
        ) : (
          <>
            <section className="flex flex-col items-center justify-between gap-6 border-b border-border-subtle py-7 sm:flex-row">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-safe" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-safe" />
                  </span>
                  <span className="text-xs font-semibold text-safe">
                    {t("domain_shield.protection_active")}
                  </span>
                </div>
                <h2 className="mt-2 text-xl font-bold text-on-surface">
                  {t("domain_shield.integrity_title")}
                </h2>
                <p className="mt-1 max-w-xl text-sm text-on-surface-variant">
                  {t("domain_shield.integrity_desc")}
                </p>
              </div>
              <div className="relative flex w-full shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border-subtle bg-surface-lowest p-3 shadow-sm sm:w-40">
                <div className="absolute inset-x-5 top-0 h-[3px] rounded-b-md bg-primary" />
                <div className="relative flex h-28 w-28 items-center justify-center">
                  <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="#f1f5f9"
                    strokeWidth="7"
                    fill="transparent"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="var(--color-primary, #4a90d9)"
                    strokeWidth="7"
                    fill="transparent"
                    strokeDasharray={251.2}
                    strokeDashoffset={251.2 - (251.2 * shieldStatus.reputation_score) / 100}
                    strokeLinecap="round"
                    className="transition-all duration-1000 ease-out"
                  />
                  </svg>
                  <div className="absolute flex flex-col items-center justify-center">
                    <span className="font-display text-4xl font-extrabold text-on-surface">
                      {shieldStatus.score_grade}
                    </span>
                    <span className="mt-1 font-mono text-[11px] font-bold text-on-surface-variant">
                      {shieldStatus.reputation_score}/100
                    </span>
                  </div>
                </div>
              </div>
            </section>

            {/* Row 2: Audit et Intégrité DNS (5 Cards side-by-side) */}
            <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-6 shadow-sm space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border-subtle/80">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 bg-primary/10 rounded-lg text-[#2e6bb5]">
                    <Activity className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-display font-bold text-[18px] text-on-surface">
                      {t("domain_shield.audit_title")}
                    </h3>
                    <p className="text-xs text-on-surface-variant mt-0.5 font-medium">
                      {t("domain_shield.audit_desc")}
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (typeof window !== "undefined") {
                      sessionStorage.removeItem(`diagnosed_${selectedDomain}`);
                    }
                    runStepDiagnostics();
                  }}
                  disabled={isTerminalRunning || isShieldLoading}
                  className="gap-2 cursor-pointer bg-white text-xs font-bold border-border-subtle hover:bg-surface-low/30 text-on-surface transition-all h-[36px]"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isTerminalRunning ? "animate-spin text-[#2e6bb5]" : "text-on-surface-variant"}`} />
                  {t("domain_shield.rerun_audit")}
                </Button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
                {[
                  {
                    id: "spf",
                    labelKey: "domain_shield.audit_spf",
                    descriptionKey: "domain_shield.audit_spf_desc",
                    valid: shieldStatus?.spf?.valid,
                  },
                  {
                    id: "dkim",
                    labelKey: "domain_shield.audit_dkim",
                    descriptionKey: "domain_shield.audit_dkim_desc",
                    valid: shieldStatus?.dkim?.valid,
                  },
                  {
                    id: "dmarc",
                    labelKey: "domain_shield.audit_dmarc",
                    descriptionKey: "domain_shield.audit_dmarc_desc",
                    valid: isDmarcValid,
                  },
                  {
                    id: "ssl",
                    labelKey: "domain_shield.audit_ssl",
                    descriptionKey: "domain_shield.audit_ssl_desc",
                    valid: shieldStatus?.ssl?.valid,
                  },
                  {
                    id: "reputation",
                    labelKey: "domain_shield.audit_reputation",
                    descriptionKey: "domain_shield.audit_reputation_desc",
                    valid: !shieldStatus?.blacklists?.listed,
                  },
                ].map((step, idx) => {
                  const isStepRunning = activeStepIndex === idx;
                  const isStepCompleted = activeStepIndex > idx;
                  const isStepIdle = activeStepIndex < idx;

                  const severity = (() => {
                    if (step.id === "dmarc") {
                      if (!shieldStatus?.dmarc?.valid) return "error";
                      if (shieldStatus?.dmarc?.policy === "none") return "warning";
                      if (!hasRestrictiveDmarcPolicy) return "warning";
                      if (!hasSicurreDmarcReporting) return "warning";
                      return "success";
                    }
                    if (step.id === "reputation") {
                      if (shieldStatus?.blacklists?.error) return "warning";
                      return shieldStatus?.blacklists?.listed ? "error" : "success";
                    }
                    return step.valid ? "success" : "error";
                  })();

                  let cardClass = "border-border-subtle bg-surface-lowest opacity-75";
                  let statusBadge = null;

                  if (isStepRunning) {
                    cardClass = "border-primary/35 bg-primary/[0.03] ring-1 ring-primary/15 opacity-100";
                    statusBadge = (
                      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-primary">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        {t("domain_shield.analyzing")}
                      </span>
                    );
                  } else if (isStepCompleted) {
                    cardClass = "border-border-subtle bg-surface-lowest opacity-100";
                    if (severity === "success") {
                      statusBadge = (
                        <span className="inline-flex items-center gap-1 rounded-md bg-safe-bg px-2.5 py-0.5 text-[11px] font-semibold text-safe">
                          <Check className="w-3.5 h-3.5" />
                          {t("domain_shield.status_conform")}
                        </span>
                      );
                    } else if (severity === "warning") {
                      statusBadge = (
                        <span className="inline-flex items-center gap-1 rounded-md bg-warning-bg px-2.5 py-0.5 text-[11px] font-semibold text-warning">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          {step.id === "reputation" && shieldStatus?.blacklists?.error
                            ? t("domain_shield.not_verified")
                            : t("domain_shield.status_partial")}
                        </span>
                      );
                    } else {
                      statusBadge = (
                        <span className="inline-flex items-center gap-1 rounded-md bg-danger-bg px-2.5 py-0.5 text-[11px] font-semibold text-danger">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          {t("domain_shield.status_missing")}
                        </span>
                      );
                    }
                  } else {
                    statusBadge = (
                      <span className="text-[11px] font-semibold text-on-surface-variant/55">
                        {t("domain_shield.pending")}
                      </span>
                    );
                  }

                  return (
                    <div
                      key={step.id}
                      className={`border rounded-xl p-4 flex flex-col justify-between min-h-[140px] transition-all duration-300 ${cardClass}`}
                    >
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold font-display text-on-surface">
                            {t(step.labelKey)}
                          </span>
                        </div>
                        <p className="text-[10.5px] text-on-surface-variant font-semibold leading-snug">
                          {t(step.descriptionKey)}
                        </p>
                      </div>

                      <div className="mt-4 pt-3 border-t border-border-subtle/50 flex items-center justify-between gap-1 overflow-hidden">
                        {statusBadge}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Row 3: Auto-Fix & Reputation Monitoring side-by-side */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
              {/* Left: Cloudflare Inline Auto-Fix Wizard */}
              <div className="lg:col-span-6 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between">
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Mouse className="w-5 h-5 text-[#2e6bb5] animate-pulse" />
                    <h3 className="font-display font-bold text-[18px] text-on-surface">
                      {t("domain_shield.autofix_title")}
                    </h3>
                  </div>

                  <div>
                    <p className="text-xs text-on-surface-variant leading-relaxed">
                      {t("domain_shield.autofix_desc")}
                    </p>
                  </div>

                  {!needsDnsSetup && (
                    <div className="p-3 bg-safe/[0.04] border border-safe/20 rounded-xl flex items-start gap-2.5">
                      <ShieldCheck className="w-4.5 h-4.5 text-safe shrink-0 mt-0.5" />
                      <div className="text-[11.5px] text-safe font-semibold leading-relaxed">
                        {t("domain_shield.autofix_complete")}
                      </div>
                    </div>
                  )}

                  {/* Target configuration breakdown list */}
                  {needsDnsSetup && (
                    <div className="bg-surface-low border border-border-subtle rounded-xl p-3.5 space-y-2.5 text-xs">
                      <div className="mb-1 flex items-center justify-between text-xs font-bold text-on-surface-variant">
                        <div className="flex items-center gap-1.5">
                          <span>{t("domain_shield.dns_records")}</span>

                          {/* Tooltip safety info */}
                          <div className="relative group">
                            <Info className="w-3.5 h-3.5 text-[#2e6bb5] cursor-help hover:text-primary transition-colors" />
                            <div className="absolute bottom-full right-0 mb-1.5 w-64 max-w-[calc(100vw-3rem)] rounded-lg border border-border-subtle bg-white p-2.5 text-center font-sans text-[10px] font-bold normal-case leading-normal text-on-surface opacity-0 shadow-xl transition-opacity duration-200 pointer-events-none group-hover:opacity-100 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-50">
                              {t("domain_shield.dns_records_help")}
                            </div>
                          </div>
                        </div>
                        <span className="text-[9.5px] font-mono lowercase text-on-surface-variant/60 font-semibold">@{selectedDomain}</span>
                      </div>
                      <div className="space-y-2.5 pt-0.5">
                        {/* SPF Record */}
                        {!shieldStatus.spf.valid && (
                          <div className="flex items-center justify-between font-semibold border-b border-border-subtle/50 pb-2 last:border-b-0">
                            <div className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={fixSpf}
                                onChange={(e) => setFixSpf(e.target.checked)}
                                className="w-4 h-4 text-primary bg-white border-border-subtle rounded cursor-pointer focus:ring-0"
                              />
                              <span className="text-on-surface">SPF (TXT @)</span>
                            </div>
                            <span className="text-error text-[11px] font-bold bg-error/[0.04] px-2 py-0.5 rounded border border-error/20">
                              {t("domain_shield.status_missing_incorrect")}
                            </span>
                          </div>
                        )}

                        {/* DKIM Record */}
                        {!shieldStatus.dkim.valid && (
                          <div className="flex items-center justify-between font-semibold border-b border-border-subtle/50 pb-2 last:border-b-0">
                            <div className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={fixDkim}
                                onChange={(e) => setFixDkim(e.target.checked)}
                                className="w-4 h-4 text-primary bg-white border-border-subtle rounded cursor-pointer focus:ring-0"
                              />
                              <span className="text-on-surface">DKIM (TXT cloudflare._domainkey)</span>
                            </div>
                            <span className="text-error text-[11px] font-bold bg-error/[0.04] px-2 py-0.5 rounded border border-error/20">
                              {t("domain_shield.status_missing_incorrect")}
                            </span>
                          </div>
                        )}

                        {/* DMARC Record */}
                        {(!isDmarcValid || !hasSicurreDmarcReporting) && (
                          <div className="flex items-center justify-between font-semibold last:border-b-0">
                            <div className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={fixDmarc}
                                onChange={(e) => setFixDmarc(e.target.checked)}
                                className="w-4 h-4 text-primary bg-white border-border-subtle rounded cursor-pointer focus:ring-0"
                              />
                              <span className="text-on-surface">DMARC (TXT _dmarc)</span>
                            </div>
                            {!shieldStatus.dmarc.valid ? (
                              <span className="text-error text-[11px] font-bold bg-error/[0.04] px-2 py-0.5 rounded border border-error/20">
                                {t("domain_shield.status_missing_incorrect")}
                              </span>
                            ) : isDmarcValid && !hasSicurreDmarcReporting ? (
                              <span className="text-[#b45309] text-[11px] font-bold bg-amber-50 px-2 py-0.5 rounded border border-amber-200/50">
                                {t("domain_shield.reporting_missing")}
                              </span>
                            ) : (
                              <span className="text-[#b45309] text-[11px] font-bold bg-amber-50 px-2 py-0.5 rounded border border-amber-200/50">
                                {t("domain_shield.status_partial")}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Cloudflare token warning alert shown inline only when token is missing */}
                  {!wsTokenData?.configured && (
                    <div className="p-4 bg-error/5 border border-error/20 rounded-xl space-y-2 text-xs text-error select-none">
                      <p className="font-bold flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4 shrink-0" />
                        {t("domain_shield.cloudflare_required_title")}
                      </p>
                      <p className="font-semibold text-on-surface-variant leading-normal">
                        {t("domain_shield.cloudflare_required_desc")}
                      </p>
                    </div>
                  )}
                </div>

                <div className="pt-5 border-t border-border-subtle/50 mt-4 flex justify-end gap-3 select-none">
                  {needsDnsSetup && (
                    <button
                      type="button"
                      onClick={handleRunAutoFix}
                      disabled={autoFixProgress !== "idle" || !wsTokenData?.configured}
                      className={`inline-flex h-10 w-full min-w-[13rem] items-center justify-center gap-2 rounded-lg border px-4 text-xs font-bold transition-[background-color,border-color,color,transform] duration-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 ${isAutoFixRunning
                          ? "border-primary/25 bg-primary-container text-on-primary-container cursor-wait"
                          : "border-transparent bg-[#2e6bb5] text-white hover:bg-[#255da0] cursor-pointer"
                        }`}
                    >
                      {isAutoFixRunning ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-current" />
                      ) : (
                        <MousePointerClick className="w-3.5 h-3.5" />
                      )}
                      <span className="min-w-[8.5rem] text-center">{getAutoFixButtonText()}</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Right: Secondary Stats Panel: Row-Level Lists */}
              <div className="lg:col-span-6 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-6">
                    <Activity className="w-5 h-5 text-[#2e6bb5] animate-pulse" />
                    <h3 className="font-display font-bold text-[18px] text-on-surface">
                      {t("domain_shield.monitoring_title")}
                    </h3>
                  </div>

                  <div className="divide-y divide-border-subtle/50 flex flex-col justify-center">
                    {/* Row 1: SSL Status */}
                    <div className="py-4.5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 first:pt-0">
                      <div className="flex items-center gap-4">
                        <div className="p-3 bg-primary/[0.06] rounded-xl text-[#2e6bb5] shrink-0">
                          <Lock className="w-5.5 h-5.5 stroke-[1.5]" />
                        </div>
                        <div className="flex items-center gap-1.5">
                          <h5 className="font-semibold text-[14.5px] text-on-surface">
                            {t("domain_shield.ssl_expiry")}
                          </h5>
                          <div className="relative group">
                            <Info className="w-3.5 h-3.5 text-[#2e6bb5] cursor-help hover:text-primary transition-colors" />
                            <div className="absolute bottom-full right-0 mb-1.5 w-60 max-w-[calc(100vw-3rem)] rounded-lg border border-border-subtle bg-white p-2.5 text-center font-sans text-[10px] font-bold normal-case leading-normal text-on-surface opacity-0 shadow-xl transition-opacity duration-200 pointer-events-none group-hover:opacity-100 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-50">
                              {t("domain_shield.ssl_help")}
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-col sm:items-end gap-1.5 min-w-[160px]">
                        {shieldStatus.ssl.valid ? (
                          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#047857] bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 w-fit">
                            <BadgeCheck className="w-4 h-4 stroke-[2]" />
                            {t("domain_shield.ssl_countdown", { days: shieldStatus.ssl.days_remaining })}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-error bg-error-container/20 px-2.5 py-1 rounded-full border border-error-container w-fit">
                            <AlertTriangle className="w-3.5 h-3.5 animate-pulse" />
                            {t("domain_shield.unresolved")}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Row 2: Blacklist Status */}
                    <div className="py-4.5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div className="flex items-center gap-4">
                        <div className="p-3 bg-primary/[0.06] rounded-xl text-[#2e6bb5] shrink-0">
                          <Skull className="w-5.5 h-5.5 stroke-[1.5]" />
                        </div>
                        <div className="flex items-center gap-1.5">
                          <h5 className="font-semibold text-[14.5px] text-on-surface">
                            {t("domain_shield.reputation_check")}
                          </h5>
                          <div className="relative group">
                            <Info className="w-3.5 h-3.5 text-[#2e6bb5] cursor-help hover:text-primary transition-colors" />
                            <div className="absolute bottom-full right-0 mb-1.5 w-60 max-w-[calc(100vw-3rem)] rounded-lg border border-border-subtle bg-white p-2.5 text-center font-sans text-[10px] font-bold normal-case leading-normal text-on-surface opacity-0 shadow-xl transition-opacity duration-200 pointer-events-none group-hover:opacity-100 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-50">
                              {t("domain_shield.reputation_help")}
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-col sm:items-end gap-1.5 min-w-[160px]">
                        {shieldStatus?.blacklists?.listed ? (
                          <>
                            <span className="inline-flex items-center gap-1.5 text-xs font-bold text-red-600 bg-red-50 px-2.5 py-1 rounded-full border border-red-200 w-fit animate-pulse">
                              <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                              {t("domain_shield.listed")}
                            </span>
                            <span className="text-[10px] font-bold text-red-600 text-left sm:text-right">
                              {t("domain_shield.matched_feeds", { feeds: shieldStatus.blacklists.matched.join(", ") })}
                            </span>
                          </>
                        ) : shieldStatus?.blacklists?.error ? (
                          <>
                            <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-warning/25 bg-warning-bg px-2.5 py-1 text-xs font-bold text-warning">
                              <AlertTriangle className="h-3.5 w-3.5" />
                              {t("domain_shield.reputation_unavailable")}
                            </span>
                            <span className="max-w-64 text-left text-[11px] font-semibold text-on-surface-variant sm:text-right">
                              {t("domain_shield.reputation_unavailable_desc")}
                            </span>
                          </>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#047857] bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 w-fit">
                            <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                            {t("domain_shield.blacklist_clean")}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Row 3: DMARC Reports Activity */}
                    <div className="py-4.5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 last:pb-0 border-b-0">
                      <div className="flex items-center gap-4">
                        <div className="p-3 bg-primary/[0.06] rounded-xl text-[#2e6bb5] shrink-0">
                          <Activity className="w-5.5 h-5.5 stroke-[1.5]" />
                        </div>
                        <div className="flex items-center gap-1.5">
                          <h5 className="font-semibold text-[14.5px] text-on-surface">
                            {t("domain_shield.dmarc_failures")}
                          </h5>
                          <div className="relative group">
                            <Info className="w-3.5 h-3.5 text-[#2e6bb5] cursor-help hover:text-primary transition-colors" />
                            <div className="absolute bottom-full right-0 mb-1.5 w-60 max-w-[calc(100vw-3rem)] rounded-lg border border-border-subtle bg-white p-2.5 text-center font-sans text-[10px] font-bold normal-case leading-normal text-on-surface opacity-0 shadow-xl transition-opacity duration-200 pointer-events-none group-hover:opacity-100 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-50">
                              {t("domain_shield.dmarc_failures_help")}
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-col sm:items-end gap-1.5 min-w-[160px]">
                        <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#2e6bb5] bg-[#d0e4ff]/30 px-2.5 py-1 rounded-full border border-primary-container/20 w-fit">
                          <Activity className="w-3.5 h-3.5" />
                          {t("domain_shield.failed_count", { count: dmarcReports?.failed_messages ?? 0 })}
                        </span>
                        <span className="text-[10px] font-bold text-[#2e6bb5]">
                          {dmarcReports?.report_count
                            ? t("domain_shield.report_count_received", { count: dmarcReports.report_count })
                            : t("domain_shield.no_reports_received")}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>


            {/* DNS Record Verification Matrix */}
            <div className="space-y-6">
              <h3 className="font-display font-bold text-xl text-on-surface">
                {t("domain_shield.dns_validation_title")}
              </h3>

              {/* SPF Card Track */}
              <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border-subtle/50">
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    <span className="rounded bg-surface-low px-2 py-0.5 text-xs font-bold text-on-surface-variant">
                      SPF
                    </span>
                    <span className="font-mono text-xs font-bold text-on-surface">Hostname: @</span>
                  </div>
                  <div>
                    {shieldStatus.spf.valid ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-safe/10 px-2.5 py-0.5 text-xs font-bold text-safe">
                        <ShieldCheck className="w-3.5 h-3.5" /> {t("domain_shield.status_conform")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2.5 py-0.5 text-xs font-bold text-warning">
                        <AlertTriangle className="w-3.5 h-3.5" /> {t("domain_shield.status_missing")}
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-1 text-xs">
                  <div className="space-y-2">
                    <span className="block text-xs font-bold text-on-surface-variant">
                      {t("domain_shield.active_dns_entry")}
                    </span>
                    {shieldStatus.spf.record ? (
                      <code className="block p-3.5 bg-surface-low/50 border border-border-subtle rounded-xl font-mono text-[11px] text-on-surface truncate select-all" title={shieldStatus.spf.record}>
                        {shieldStatus.spf.record}
                      </code>
                    ) : (
                      <p className="italic text-on-surface-variant/60 block p-3.5 bg-surface-low/30 rounded-xl">
                        {t("domain_shield.no_spf_record")}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <span className="block text-xs font-bold text-on-surface-variant">
                      {t("domain_shield.required_dns_setup")}
                    </span>
                    <div className="flex gap-2 items-center">
                      <code className="flex-1 block p-3.5 bg-surface-low/50 border border-border-subtle text-on-surface rounded-xl font-mono text-[11px] truncate select-all">
                        v=spf1 include:spf.cloudflare.com include:sicurre.com ~all
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopy("spf", "v=spf1 include:spf.cloudflare.com include:sicurre.com ~all")}
                        className="px-3 h-10 cursor-pointer text-xs gap-1 font-bold rounded-xl bg-white"
                      >
                        {copiedKey === "spf" ? (
                          <Check className="w-4 h-4 text-safe" />
                        ) : (
                          <Copy className="w-4 h-4 text-on-surface-variant" />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>

              {/* DKIM Card Track */}
              <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border-subtle/50">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-surface-low px-2 py-0.5 text-xs font-bold text-on-surface-variant">
                      DKIM
                    </span>
                    <span className="font-mono text-xs font-bold text-on-surface">Hostname: cloudflare._domainkey</span>
                  </div>
                  <div>
                    {shieldStatus.dkim.valid ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-safe/10 px-2.5 py-0.5 text-xs font-bold text-safe">
                        <ShieldCheck className="w-3.5 h-3.5" /> {t("domain_shield.status_conform")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2.5 py-0.5 text-xs font-bold text-warning">
                        <AlertTriangle className="w-3.5 h-3.5" /> {t("domain_shield.status_missing")}
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-1 text-xs">
                  <div className="space-y-2">
                    <span className="block text-xs font-bold text-on-surface-variant">
                      {t("domain_shield.active_dns_entry")}
                    </span>
                    {shieldStatus.dkim.record ? (
                      <code className="block p-3.5 bg-surface-low/50 border border-border-subtle rounded-xl font-mono text-[11px] text-on-surface truncate select-all" title={shieldStatus.dkim.record}>
                        {shieldStatus.dkim.record}
                      </code>
                    ) : (
                      <p className="italic text-on-surface-variant/60 block p-3.5 bg-surface-low/30 rounded-xl">
                        {t("domain_shield.no_dkim_record")}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <span className="block text-xs font-bold text-on-surface-variant">
                      {t("domain_shield.required_dns_setup")}
                    </span>
                    <div className="flex gap-2 items-center">
                      <code className="flex-1 block p-3.5 bg-surface-low/50 border border-border-subtle text-on-surface rounded-xl font-mono text-[11px] truncate select-all">
                        v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1+z7s...
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopy("dkim", "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1+z7s...")}
                        className="px-3 h-10 cursor-pointer text-xs gap-1 font-bold rounded-xl bg-white"
                      >
                        {copiedKey === "dkim" ? (
                          <Check className="w-4 h-4 text-safe" />
                        ) : (
                          <Copy className="w-4 h-4 text-on-surface-variant" />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>

              {/* DMARC Card Track */}
              <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border-subtle/50">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-surface-low px-2 py-0.5 text-xs font-bold text-on-surface-variant">
                      DMARC
                    </span>
                    <span className="font-mono text-xs font-bold text-on-surface">Hostname: _dmarc</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`select-none rounded border px-2 py-0.5 font-mono text-xs font-bold ${getDmarcPolicyClass(shieldStatus.dmarc.policy)}`}>
                      {t("domain_shield.policy")} : {shieldStatus.dmarc.policy}
                    </span>
                    {isDmarcComplete ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-safe bg-safe/10 px-2.5 py-0.5 rounded-full">
                        <ShieldCheck className="w-3.5 h-3.5" /> {t("domain_shield.status_conform")}
                      </span>
                    ) : shieldStatus.dmarc.valid || isDmarcValid ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-warning bg-warning/10 px-2.5 py-0.5 rounded-full">
                        <AlertTriangle className="w-3.5 h-3.5" /> {t("domain_shield.status_partial")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-error bg-error/10 px-2.5 py-0.5 rounded-full">
                        <AlertTriangle className="w-3.5 h-3.5" /> {t("domain_shield.status_missing")}
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-1 text-xs">
                  <div className="space-y-2">
                    <span className="block text-xs font-bold text-on-surface-variant">
                      {t("domain_shield.active_dns_entry")}
                    </span>
                    {shieldStatus.dmarc.record ? (
                      <code className="block p-3.5 bg-surface-low/50 border border-border-subtle rounded-xl font-mono text-[11px] text-on-surface truncate select-all" title={shieldStatus.dmarc.record}>
                        {shieldStatus.dmarc.record}
                      </code>
                    ) : (
                      <p className="italic text-on-surface-variant/60 block p-3.5 bg-surface-low/30 rounded-xl">
                        {t("domain_shield.no_dmarc_record")}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <span className="block text-xs font-bold text-on-surface-variant">
                      {t("domain_shield.sicurre_recommendation")}
                    </span>
                    <div className="flex gap-2 items-center">
                      <code className="flex-1 block p-3.5 bg-surface-low/50 border border-border-subtle text-on-surface rounded-xl font-mono text-[11px] truncate select-all" title={getRecommendedDmarcRecord()}>
                        {getRecommendedDmarcRecord()}
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopy("dmarc", getRecommendedDmarcRecord())}
                        className="px-3 h-10 cursor-pointer text-xs gap-1 font-bold rounded-xl bg-white"
                      >
                        {copiedKey === "dmarc" ? (
                          <Check className="w-4 h-4 text-safe" />
                        ) : (
                          <Copy className="w-4 h-4 text-on-surface-variant" />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>

              {/* DMARC Aggregate Reports */}
              <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <BarChart3 className="h-4 w-4 text-primary" />
                      <p className="text-xs font-bold text-on-surface">{t("domain_shield.report_title")}</p>
                    </div>
                    <p className="max-w-2xl text-[11px] leading-relaxed text-on-surface-variant">
                      {hasSicurreDmarcReporting ? t("domain_shield.report_enabled_desc") : t("domain_shield.report_missing_desc")}
                    </p>
                  </div>
                  <span className={`w-fit rounded-md border px-2.5 py-1 text-[11px] font-semibold ${dmarcReports?.report_count ? "border-safe/20 bg-safe/10 text-safe" : "border-warning/25 bg-warning/10 text-warning"}`}>
                    {dmarcReports?.report_count
                      ? t("domain_shield.reports_received")
                      : hasSicurreDmarcReporting
                        ? t("domain_shield.awaiting_report")
                        : t("domain_shield.status_partial")}
                  </span>
                </div>
                {dmarcReportsLoading ? (
                  <div className="mt-4 h-20 animate-pulse rounded-lg bg-surface-low" />
                ) : dmarcReportsFailed ? (
                  <div role="alert" className="mt-4 rounded-lg border border-error/25 bg-error-container/35 p-4 text-sm text-on-surface">
                    <p className="font-semibold">{t("common.load_error")}</p>
                    <button type="button" onClick={() => void refetchDmarcReports()} className="mt-2 font-bold text-primary hover:text-primary-hover">
                      {t("common.retry")}
                    </button>
                  </div>
                ) : (
                  <><div className="mt-4 grid gap-3 sm:grid-cols-4">
                    {[
                      { label: t("domain_shield.report_count"), value: dmarcReports?.report_count ?? 0 },
                      { label: t("domain_shield.report_messages"), value: dmarcReports?.total_messages ?? 0 },
                      { label: t("domain_shield.report_aligned"), value: dmarcReports?.aligned_messages ?? 0 },
                      { label: t("domain_shield.report_failed"), value: dmarcReports?.failed_messages ?? 0 },
                    ].map((metric) => (
                      <div key={metric.label} className="rounded-lg border border-border-subtle bg-surface-lowest p-3">
                        <p className="text-xs font-bold text-on-surface-variant">{metric.label}</p>
                        <p className="mt-1 font-mono text-lg font-extrabold text-on-surface">{metric.value}</p>
                      </div>
                    ))}
                  </div>
                    {dmarcReports?.top_sources?.length ? (
                      <div className="mt-3 divide-y divide-border-subtle overflow-hidden rounded-lg border border-border-subtle bg-surface-lowest">
                        {dmarcReports.top_sources.map((source) => (
                          <div key={source.source_ip} className="grid grid-cols-[1fr_auto] gap-3 px-3 py-2 text-[11px]">
                            <span className="font-mono text-on-surface">{source.source_ip}</span>
                            <span className="font-semibold text-on-surface-variant">
                              {source.message_count} · DKIM {source.dkim_result} · SPF {source.spf_result}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-3 text-[11px] font-semibold text-on-surface-variant">
                        {t("domain_shield.report_empty")}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>


          </>
        )}
      </MotionDiv>
    </>
  );
}
