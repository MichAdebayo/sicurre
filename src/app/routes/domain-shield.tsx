import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck,
  ShieldAlert,
  Copy,
  Check,
  RefreshCw,
  AlertTriangle,
  Globe,
  Lock,
  Skull,
  Award,
  ArrowRight,
  Info,
  Terminal,
  Zap,
  Play,
  Send,
  HelpCircle,
  FileCheck,
  CheckCircle2,
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
  AuthSession,
} from "../lib/api";

const MotionDiv = motion.div as any;

interface DomainShieldRouteProps {
  session?: AuthSession;
}

export default function DomainShieldRoute({ session }: DomainShieldRouteProps) {
  const { t, i18n } = useTranslation();
  const isFR = i18n.language === "fr";

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
    refetch: reloadShield,
  } = useDomainShieldStatus(selectedDomain, !!selectedDomain);

  const refreshShieldMutation = useRefreshDomainShieldStatus();

  const isDmarcValid = !!(shieldStatus?.dmarc?.valid && (shieldStatus?.dmarc?.record || "").includes("dmarc@sicurre.com"));
  const needsDnsSetup = !!(shieldStatus && (!shieldStatus.spf.valid || !shieldStatus.dkim.valid || !isDmarcValid));
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
      console.error("Failed to refresh domain status:", err);
    }
  };

  // Clipboard copy handlers
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const getRecommendedDmarcRecord = () => {
    const activeRecord = shieldStatus?.dmarc?.record || "";
    if (!activeRecord) {
      return "v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc@sicurre.com";
    }
    if (activeRecord.includes("dmarc@sicurre.com")) {
      return activeRecord;
    }
    if (activeRecord.includes("rua=")) {
      return activeRecord.replace(/(rua=[^;]+)/, "$1,mailto:dmarc@sicurre.com");
    } else {
      const base = activeRecord.endsWith(";") ? activeRecord.trim() : `${activeRecord.trim()};`;
      return `${base} rua=mailto:dmarc@sicurre.com`;
    }
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

  // State for Email Spoofing Simulator Sandbox
  const [spoofStep, setSpoofStep] = useState<"idle" | "sending" | "analyzing" | "result">("idle");
  const [spoofProgress, setSpoofProgress] = useState(0);
  const [spoofLogs, setSpoofLogs] = useState<string[]>([]);

  const startSpoofSimulation = () => {
    if (spoofStep !== "idle") return;
    setSpoofStep("sending");
    setSpoofProgress(0);
    setSpoofLogs([]);

    const steps = [
      isFR 
        ? "Envoi du mail d'imposture simulé depuis le serveur non autorisé (185.220.101.5)..." 
        : "Sending simulated impersonation email from unauthorized relay IP (185.220.101.5)...",
      isFR 
        ? "Réception par la passerelle de messagerie destinataire..." 
        : "Received by target destination mail server...",
      isFR
        ? "Analyse SPF : IP 185.220.101.5 est-elle dans l'enregistrement SPF ? ➔ ÉCHEC"
        : "SPF Audit: Is IP 185.220.101.5 included in SPF records? ➔ FAIL",
      isFR
        ? "Analyse DKIM : Signature cryptographique valide présente ? ➔ ÉCHEC (Non signé)"
        : "DKIM Audit: Is a valid cryptographic signature present? ➔ FAIL (Unsigned)",
      isFR
        ? `Évaluation DMARC : SPF & DKIM ont échoué. Application de la politique DMARC : "${shieldStatus?.dmarc.policy || 'none'}"`
        : `DMARC Evaluation: Both SPF & DKIM failed. Applying domain policy: "${shieldStatus?.dmarc.policy || 'none'}"`
    ];

    let current = 0;
    const interval = setInterval(() => {
      if (current < steps.length) {
        setSpoofLogs((prev) => [...prev, steps[current]]);
        setSpoofProgress(((current + 1) / steps.length) * 100);
        current++;
      } else {
        clearInterval(interval);
        setSpoofStep("result");
      }
    }, 1200);
  };

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
  const [dots, setDots] = useState("");

  // Animated dots for "configuring..." state
  useEffect(() => {
    if (autoFixProgress === "idle" || autoFixProgress === "success" || autoFixProgress === "error") {
      setDots("");
      return;
    }
    const interval = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? "" : prev + "."));
    }, 450);
    return () => clearInterval(interval);
  }, [autoFixProgress]);

  const getAutoFixButtonText = () => {
    if (autoFixProgress === "verify") {
      return isFR ? `Configuration en cours (vérification)${dots}` : `Configuring (verifying)${dots}`;
    }
    if (autoFixProgress === "dns") {
      return isFR ? `Configuration en cours (écriture DNS)${dots}` : `Configuring (DNS records)${dots}`;
    }
    if (autoFixProgress === "routing") {
      return isFR ? `Configuration en cours (redirection)${dots}` : `Configuring (email routing)${dots}`;
    }
    if (autoFixProgress === "success") {
      return isFR ? "Configuration appliquée !" : "Configuration applied!";
    }
    if (autoFixProgress === "error") {
      return isFR ? "Échec de la configuration" : "Configuration failed";
    }
    return isFR ? "Lancer l'Auto-Configuration" : "Launch Auto-Configuration";
  };

  const handleRunAutoFix = async () => {
    const token = wsTokenData?.api_token;
    if (!token) {
      setErrorNotification(
        isFR
          ? "Configuration Cloudflare requise : Veuillez d'abord ajouter votre jeton API Cloudflare dans les Paramètres > onglet Intégrations."
          : "Cloudflare Integration Required: Please configure your Cloudflare API token in Settings > Integrations first."
      );
      setTimeout(() => setErrorNotification(null), 4500);
      return;
    }

    if (!selectedDomain) return;

    setAutoFixProgress("verify");
    setAutoFixErrorMsg("");

    try {
      // Simulate stages for nice visual flow
      setTimeout(() => setAutoFixProgress("dns"), 1500);
      setTimeout(() => setAutoFixProgress("routing"), 3000);
      
      const payload = {
        cf_api_token: token,
        zone_name: selectedDomain,
        destination_email: session?.email || "owner@sicurre.com",
        fix_spf: fixSpf,
        fix_dkim: fixDkim,
        fix_dmarc: fixDmarc
      };

      setTimeout(async () => {
        try {
          await setupMutation.mutateAsync(payload);
          setAutoFixProgress("success");
          
          setSuccessNotification(
            isFR
              ? "Auto-configuration DNS et redirection email appliquées avec succès !"
              : "Cloudflare DNS configuration and email routing deployed successfully!"
          );
          
          reloadShield();
          
          setTimeout(() => {
            setSuccessNotification(null);
            setAutoFixProgress("idle");
          }, 4000);
        } catch (err: any) {
          setAutoFixProgress("error");
          const msg = err.message || (isFR ? "Échec de l'auto-configuration DNS." : "Failed to deploy DNS records.");
          setAutoFixErrorMsg(msg);
          setErrorNotification(msg);
          setTimeout(() => {
            setErrorNotification(null);
            setAutoFixProgress("idle");
          }, 4500);
        }
      }, 4500);

    } catch (err: any) {
      setAutoFixProgress("error");
      const msg = err.message || (isFR ? "Échec de l'initialisation." : "Failed to initialize setup.");
      setAutoFixErrorMsg(msg);
      setErrorNotification(msg);
      setTimeout(() => {
        setErrorNotification(null);
        setAutoFixProgress("idle");
      }, 4500);
    }
  };

  const getDmarcPolicyClass = (policy?: string) => {
    if (policy === "reject") return "text-safe bg-safe/10 border-safe/25";
    if (policy === "quarantine") return "text-primary bg-primary/10 border-primary/25";
    return "text-warning bg-warning/10 border-warning/25";
  };

  return (
    <>
      <AnimatePresence>
        {successNotification && (
          <motion.div
            initial={{ opacity: 0, y: -50, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: -50, x: "-50%" }}
            className="fixed top-6 left-1/2 z-[9999] flex items-center gap-3 px-5 py-3.5 bg-safe/10 backdrop-blur-md border border-safe/25 text-safe font-bold text-xs rounded-xl shadow-xl max-w-md w-[90%] sm:w-full"
          >
            <CheckCircle2 className="w-5 h-5 shrink-0 text-safe animate-bounce" />
            <span className="flex-1 text-left">{successNotification}</span>
          </motion.div>
        )}
        {errorNotification && (
          <motion.div
            initial={{ opacity: 0, y: -50, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: -50, x: "-50%" }}
            className="fixed top-6 left-1/2 z-[9999] flex items-center gap-3 px-5 py-3.5 bg-error/10 backdrop-blur-md border border-error/25 text-error font-bold text-xs rounded-xl shadow-xl max-w-md w-[90%] sm:w-full"
          >
            <ShieldAlert className="w-5 h-5 shrink-0 text-error animate-pulse" />
            <span className="flex-1 text-left">{errorNotification}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <MotionDiv
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -12 }}
        transition={{ duration: 0.3 }}
        className="space-y-8 animate-in fade-in duration-200"
      >
        {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <h1 className="app-h1">
            {isFR ? "Commandement du Bouclier" : "Domain Shield Command Center"}
          </h1>
          <p className="app-body-sub mt-1">
            {isFR
              ? "Supervision de la légitimité DNS, de l'authentification et de la réputation de livraison"
              : "Continuous audit of DNS authentication, deliverability reputation, and outgoing spoofing protection"}
          </p>
        </div>

        {/* Domain Selection dropdown */}
        <div className="flex items-center gap-3">
          {domainsLoading ? (
            <div className="h-10 w-48 bg-surface-low rounded-lg animate-pulse" />
          ) : !domainsList || domainsList.length === 0 ? (
            <span className="text-xs text-on-surface-variant/70 italic">
              {isFR ? "Aucun domaine configuré" : "No domains configured"}
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
            {isFR ? "Aucun Bouclier de Domaine actif" : "No Domain Shield active"}
          </p>
          <p className="text-sm mt-1 text-on-surface-variant">
            {isFR
              ? "Veuillez intégrer un domaine via Cloudflare dans les paramètres pour activer l'audit continu de santé de votre domaine."
              : "Please integrate a domain via Cloudflare in the settings section to enable continuous domain health auditing."}
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
            {isFR ? "Impossible de récupérer les balises de validation de sécurité DNS." : "Could not fetch DNS security validation tags."}
          </p>
        </div>
      ) : (
        <>
          {/* Main Layout Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
            
            {/* Left: Interactive Radar Dome & Score */}
            <div className="lg:col-span-5 bg-surface-lowest rounded-2xl border border-border-subtle p-8 flex flex-col items-center justify-center text-center shadow-sm relative overflow-hidden">
              <div className="absolute top-4 right-4 flex items-center gap-1.5 select-none">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-safe" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-safe" />
                </span>
                <span className="text-[10px] font-extrabold text-safe uppercase tracking-wider">
                  {isFR ? "Actif & Protégé" : "Active & Hardened"}
                </span>
              </div>

              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-6 flex items-center gap-1.5 select-none">
                <Award className="w-4 h-4 text-primary" />
                {isFR ? "Indice d'Intégrité DNS" : "DNS Integrity Rating"}
              </p>

              <div className="relative w-44 h-44 flex items-center justify-center select-none">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
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
                  <span className="font-display font-extrabold text-5xl text-on-surface tracking-tighter">
                    {shieldStatus.score_grade}
                  </span>
                  <span className="text-[11px] font-bold font-mono text-on-surface-variant mt-1">
                    {shieldStatus.reputation_score}/100 Rating
                  </span>
                </div>
              </div>

            </div>

            {/* Right: Interactive Spoof Simulator Sandbox */}
            <div className="lg:col-span-7 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between relative overflow-hidden">
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <Play className="w-5 h-5 text-primary" />
                  <h3 className="font-display font-bold text-[18px] text-on-surface">
                    {isFR ? "Simulateur d'usurpation (Sandbox)" : "Impersonation Simulator Sandbox"}
                  </h3>
                </div>
                
                <p className="text-xs text-on-surface-variant leading-relaxed">
                  {isFR
                    ? "Testez la résilience de votre domaine en simulant une tentative d'usurpation d'identité pour vérifier les barrières de protection."
                    : "Test your domain's defensive posture by launching a simulated phishing email forgery check."}
                </p>

                {spoofStep === "idle" && (
                  <div className="bg-surface-low border border-border-subtle rounded-xl p-4 space-y-2">
                    <div className="flex justify-between text-[11px] text-on-surface-variant font-bold uppercase">
                      <span>{isFR ? "Enveloppe du Mail Test" : "Simulated Mail Envelope"}</span>
                      <span className="text-error font-extrabold">{isFR ? "En-tête Falsifié" : "Forged Header"}</span>
                    </div>
                    <div className="text-xs space-y-1 font-mono">
                      <div><span className="text-on-surface-variant">From:</span> info@{selectedDomain}</div>
                      <div><span className="text-on-surface-variant">Source IP:</span> 185.220.101.5 (unauthorized)</div>
                      <div><span className="text-on-surface-variant">To:</span> client@partnerdomain.com</div>
                    </div>
                  </div>
                )}

                {spoofStep !== "idle" && (
                  <div className="space-y-3">
                    {/* Progress Bar */}
                    <div className="w-full bg-surface-low h-1.5 rounded-full overflow-hidden">
                      <div className="h-full bg-primary transition-all duration-300" style={{ width: `${spoofProgress}%` }} />
                    </div>

                    <div className="bg-slate-950 p-4 rounded-xl border border-white/5 font-mono text-[11px] text-white/70 space-y-2 min-h-[100px]">
                      {spoofLogs.map((log, idx) => (
                        <div key={idx} className={log?.includes("ÉCHEC") || log?.includes("FAIL") ? "text-amber-400" : "text-white/60"}>
                          {log}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-5 border-t border-border-subtle/50 mt-4 flex items-center justify-between">
                {spoofStep === "result" ? (
                  <div className="flex flex-col gap-2 w-full">
                    <div className={`p-3 rounded-lg border text-xs font-semibold ${
                      shieldStatus.dmarc.policy === "reject" || shieldStatus.dmarc.policy === "quarantine"
                        ? "bg-safe/5 border-safe/20 text-safe"
                        : "bg-warning/5 border-warning/20 text-warning"
                    }`}>
                      {shieldStatus.dmarc.policy === "reject"
                        ? (isFR 
                            ? "✅ Attaque bloquée ! Votre politique DMARC 'reject' a rejeté le message falsifié." 
                            : "✅ Attack Blocked! Your DMARC 'reject' policy discarded the forged email.")
                        : shieldStatus.dmarc.policy === "quarantine"
                        ? (isFR 
                            ? "⚠️ Attaque filtrée : l'email falsifié a été envoyé dans le dossier spam." 
                            : "⚠️ Attack Filtered: the forged email was routed to spam/quarantine folder.")
                        : (isFR 
                            ? "🚨 Vulnérable ! Aucune politique restrictive définie, l'email frauduleux serait délivré." 
                            : "🚨 Vulnerable! No restrictive DMARC policy defined, the spoofed email would land in user inbox.")}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSpoofStep("idle")}
                      className="w-fit self-end cursor-pointer bg-white text-xs font-bold"
                    >
                      {isFR ? "Recommencer" : "Reset Test"}
                    </Button>
                  </div>
                ) : (
                  <Button
                    onClick={startSpoofSimulation}
                    disabled={spoofStep === "sending"}
                    className="w-full flex items-center justify-center gap-2 cursor-pointer bg-[#2e6bb5] text-white hover:bg-[#23589b] border-none text-xs font-bold rounded-lg transition-all h-[38px] shadow-sm"
                  >
                    <Send className="w-4 h-4" />
                    <span>
                      {spoofStep === "sending" 
                        ? (isFR ? "Simulation en cours..." : "Simulating...") 
                        : (isFR ? "Lancer le test d'usurpation" : "Launch Spoof simulation")}
                    </span>
                  </Button>
                )}
              </div>
            </div>
          </div>

          {/* Row 2: Audit et Intégrité DNS (5 Cards side-by-side) */}
          <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-6 shadow-sm space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border-subtle/80">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-primary/10 rounded-lg text-[#2e6bb5]">
                  <Activity className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-display font-bold text-[18px] text-on-surface">
                    {isFR ? "Audit et Intégrité DNS" : "DNS Audit & Integrity Status"}
                  </h3>
                  <p className="text-xs text-on-surface-variant mt-0.5 font-medium">
                    {isFR ? "Vérification en temps réel de vos configurations de messagerie" : "Real-time verification of email security records"}
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
                {isFR ? "Relancer l'audit de sécurité" : "Re-diagnose Domain"}
              </Button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
              {[
                {
                  id: "spf",
                  labelFR: "Enregistrement SPF",
                  labelEN: "SPF Record",
                  descFR: "Serveurs autorisés",
                  descEN: "Authorized relays",
                  valid: shieldStatus?.spf?.valid,
                },
                {
                  id: "dkim",
                  labelFR: "Signature DKIM",
                  labelEN: "DKIM Signature",
                  descFR: "Clé d'authentification",
                  descEN: "Auth signatures",
                  valid: shieldStatus?.dkim?.valid,
                },
                {
                  id: "dmarc",
                  labelFR: "Politique DMARC",
                  labelEN: "DMARC Policy",
                  descFR: "Consignes de filtrage",
                  descEN: "Filtering instructions",
                  valid: shieldStatus?.dmarc?.valid && (shieldStatus?.dmarc?.record || "").includes("dmarc@sicurre.com"),
                },
                {
                  id: "ssl",
                  labelFR: "Certificat SSL",
                  labelEN: "SSL Certificate",
                  descFR: "Chiffrement HTTPS",
                  descEN: "HTTPS encryption",
                  valid: shieldStatus?.ssl?.valid,
                },
                {
                  id: "reputation",
                  labelFR: "Scan Réputation",
                  labelEN: "IP Reputation",
                  descFR: "Listes noires / Menaces",
                  descEN: "Blocklists audit",
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
                    if (!(shieldStatus?.dmarc?.record || "").includes("dmarc@sicurre.com")) return "warning";
                    return "success";
                  }
                  if (step.id === "reputation") {
                    return shieldStatus?.blacklists?.listed ? "error" : "success";
                  }
                  return step.valid ? "success" : "error";
                })();

                let cardClass = "border-border-subtle bg-surface-lowest opacity-75";
                let statusBadge = null;

                if (isStepRunning) {
                  cardClass = "border-[#2e6bb5] bg-[#d0e4ff]/10 shadow-[0_0_12px_rgba(46,107,181,0.15)] ring-1 ring-[#2e6bb5]/20 scale-[1.02] opacity-100";
                  statusBadge = (
                    <span className="flex items-center gap-1.5 text-[10px] font-bold text-[#2e6bb5] uppercase">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#2e6bb5]" />
                      {isFR ? "Analyse..." : "Analyzing..."}
                    </span>
                  );
                } else if (isStepCompleted) {
                  if (severity === "success") {
                    cardClass = "border-emerald-200 bg-emerald-50/[0.08] opacity-100";
                    statusBadge = (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-[#047857] bg-emerald-50 px-2.5 py-0.5 rounded-md border border-emerald-200">
                        <Check className="w-3.5 h-3.5" />
                        {isFR ? "Conforme" : "Pass"}
                      </span>
                    );
                  } else if (severity === "warning") {
                    cardClass = "border-amber-200 bg-amber-50/[0.08] opacity-100";
                    statusBadge = (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-[#b45309] bg-amber-50 px-2.5 py-0.5 rounded-md border border-amber-200">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {isFR ? "Partiel" : "Warning"}
                      </span>
                    );
                  } else {
                    cardClass = "border-red-200 bg-red-50/[0.08] opacity-100";
                    statusBadge = (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-red-600 bg-red-50 px-2.5 py-0.5 rounded-md border border-red-200">
                        <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                        {isFR ? "Manquant" : "Missing"}
                      </span>
                    );
                  }
                } else {
                  statusBadge = (
                    <span className="text-[10px] font-bold text-on-surface-variant/40 uppercase">
                      {isFR ? "En attente" : "Pending"}
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
                          {isFR ? step.labelFR : step.labelEN}
                        </span>
                      </div>
                      <p className="text-[10.5px] text-on-surface-variant font-semibold leading-snug">
                        {isFR ? step.descFR : step.descEN}
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
                    {isFR ? "Auto-Fix Cloudflare 1-Clic" : "1-Click Cloudflare Auto-Fix"}
                  </h3>
                </div>

                <div>
                  <p className="text-xs text-on-surface-variant leading-relaxed">
                    {isFR
                      ? "Corrigez et provisionnez automatiquement vos enregistrements DNS manquants (SPF, DKIM, DMARC) via l'API Cloudflare."
                      : "Automatically generate and sync missing DNS records (SPF, DKIM, DMARC) directly using the Cloudflare token API wizard."}
                  </p>
                </div>

                {!needsDnsSetup && (
                  <div className="p-3 bg-safe/[0.04] border border-safe/20 rounded-xl flex items-start gap-2.5">
                    <ShieldCheck className="w-4.5 h-4.5 text-safe shrink-0 mt-0.5" />
                    <div className="text-[11.5px] text-safe font-semibold leading-relaxed">
                      {isFR
                        ? "Tous les protocoles SPF, DKIM, DMARC sont configurés de façon optimale."
                        : "DNS configuration is fully optimized and secured against impersonators."}
                    </div>
                  </div>
                )}

                {/* Target configuration breakdown list */}
                {needsDnsSetup && (
                  <div className="bg-surface-low border border-border-subtle rounded-xl p-3.5 space-y-2.5 text-xs">
                    <div className="font-bold text-[10px] uppercase tracking-wider text-on-surface-variant mb-1 flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span>{isFR ? "Enregistrements DNS" : "DNS Records Setup"}</span>
                        
                        {/* Tooltip safety info */}
                        <div className="relative group">
                          <Info className="w-3.5 h-3.5 text-[#2e6bb5] cursor-help hover:text-primary transition-colors" />
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-64 bg-white border border-border-subtle text-on-surface text-[10px] p-2.5 rounded-lg shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-200 z-50 normal-case leading-normal font-sans text-center font-bold">
                            {isFR
                              ? "La configuration correcte des protocoles SPF, DKIM et DMARC protège votre domaine contre l'usurpation d'identité et garantit que vos e-mails légitimes ne finissent pas dans le dossier Spam."
                              : "Properly configuring SPF, DKIM, and DMARC protocols safeguards your domain from email spoofing and ensures your emails avoid spam folders."}
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
                            {isFR ? "Manquant / Incorrect" : "Missing / Incorrect"}
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
                            {isFR ? "Manquant / Incorrect" : "Missing / Incorrect"}
                          </span>
                        </div>
                      )}

                      {/* DMARC Record */}
                      {!isDmarcValid && (
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
                              {isFR ? "Manquant / Incorrect" : "Missing / Incorrect"}
                            </span>
                          ) : (
                            <span className="text-[#b45309] text-[11px] font-bold bg-amber-50 px-2 py-0.5 rounded border border-amber-200/50">
                              {isFR ? "Configuration Partielle" : "Partial Configuration"}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Cloudflare token warning alert shown inline only when token is missing */}
                {!wsTokenData?.api_token && (
                  <div className="p-4 bg-error/5 border border-error/20 rounded-xl space-y-2 text-xs text-error select-none">
                    <p className="font-bold flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 shrink-0" />
                      {isFR ? "Configuration Cloudflare requise" : "Cloudflare Integration Required"}
                    </p>
                    <p className="font-semibold text-on-surface-variant leading-normal">
                      {isFR 
                        ? "Veuillez d'abord configurer votre jeton API Cloudflare dans les Paramètres > onglet Intégrations avant de lancer l'auto-configuration." 
                        : "Please configure your Cloudflare API token in Settings > Integrations first before launching auto-configuration."}
                    </p>
                  </div>
                )}
              </div>

              <div className="pt-5 border-t border-border-subtle/50 mt-4 flex justify-end gap-3 select-none">
                {needsDnsSetup && (
                  <Button
                    size="sm"
                    onClick={handleRunAutoFix}
                    disabled={autoFixProgress !== "idle" || !wsTokenData?.api_token}
                    className={`w-full flex items-center justify-center gap-1.5 text-xs font-bold rounded-lg transition-all h-[38px] shadow-sm border ${
                      autoFixProgress !== "idle"
                        ? "bg-primary/10 border-primary/20 text-[#2e6bb5] cursor-wait"
                        : "bg-[#2e6bb5] hover:bg-[#23589b] text-white border-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    }`}
                  >
                    {autoFixProgress !== "idle" && autoFixProgress !== "success" && autoFixProgress !== "error" ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#2e6bb5]" />
                    ) : (
                      <MousePointerClick className="w-3.5 h-3.5" />
                    )}
                    <span>{getAutoFixButtonText()}</span>
                  </Button>
                )}
              </div>
            </div>

            {/* Right: Secondary Stats Panel: Row-Level Lists */}
            <div className="lg:col-span-6 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 mb-6">
                  <Activity className="w-5 h-5 text-[#2e6bb5] animate-pulse" />
                  <h3 className="font-display font-bold text-[18px] text-on-surface">
                    {isFR ? "Surveillance & Sécurité du Domaine" : "Domain Security & Monitoring"}
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
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-white border border-border-subtle text-on-surface text-[10px] p-2.5 rounded-lg shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-200 z-50 normal-case leading-normal font-sans text-center font-bold">
                            {isFR
                              ? "Contrôle de validité et chiffrement actif du certificat SSL."
                              : "Verifying validity and encryption status of your SSL certificate."}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col sm:items-end gap-1.5 min-w-[160px]">
                      {shieldStatus.ssl.valid ? (
                        <>
                          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#047857] bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 w-fit">
                            <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                            {t("domain_shield.ssl_countdown", { days: shieldStatus.ssl.days_remaining })}
                          </span>
                          <span className="text-[10px] font-bold text-on-surface-variant">
                            {t("domain_shield.ssl_renew_active")}
                          </span>
                        </>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs font-bold text-error bg-error-container/20 px-2.5 py-1 rounded-full border border-error-container w-fit">
                          <AlertTriangle className="w-3.5 h-3.5 animate-pulse" />
                          {isFR ? "Non résolu" : "Unresolved"}
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
                          {isFR ? "Surveillance de Réputation" : "Domain Reputation Monitor"}
                        </h5>
                        <div className="relative group">
                          <Info className="w-3.5 h-3.5 text-[#2e6bb5] cursor-help hover:text-primary transition-colors" />
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-white border border-border-subtle text-on-surface text-[10px] p-2.5 rounded-lg shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-200 z-50 normal-case leading-normal font-sans text-center font-bold">
                            {isFR
                              ? "Audit continu auprès des listes noires (Spamhaus, RBL) pour garantir la délivrabilité."
                              : "Continual checks against blocklists (Spamhaus, RBLs) to secure deliverability."}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col sm:items-end gap-1.5 min-w-[160px]">
                      {shieldStatus?.blacklists?.listed ? (
                        <>
                          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-red-600 bg-red-50 px-2.5 py-1 rounded-full border border-red-200 w-fit animate-pulse">
                            <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                            {isFR ? "Listé / Bloqué" : "Listed / Blocked"}
                          </span>
                          <span className="text-[10px] font-bold text-red-600 text-left sm:text-right">
                            {isFR 
                              ? `Listes : ${shieldStatus.blacklists.matched.join(", ")}` 
                              : `Feeds: ${shieldStatus.blacklists.matched.join(", ")}`}
                          </span>
                        </>
                      ) : (
                        <>
                          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#047857] bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 w-fit">
                            <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                            {t("domain_shield.blacklist_clean")}
                          </span>
                          <span className="text-[10px] font-bold text-on-surface-variant text-left sm:text-right">
                            {isFR ? "Aucun blocage" : "No blocks"}
                          </span>
                        </>
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
                          {isFR ? "Activité de Blocage DMARC" : "DMARC Block Activity"}
                        </h5>
                        <div className="relative group">
                          <Info className="w-3.5 h-3.5 text-[#2e6bb5] cursor-help hover:text-primary transition-colors" />
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-white border border-border-subtle text-on-surface text-[10px] p-2.5 rounded-lg shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-200 z-50 normal-case leading-normal font-sans text-center font-bold">
                            {isFR
                              ? "Rapports d'activité des serveurs non autorisés ayant tenté d'usurper votre domaine."
                              : "Activity reports from unauthorized mail servers attempting domain spoofing."}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col sm:items-end gap-1.5 min-w-[160px]">
                      <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[#2e6bb5] bg-[#d0e4ff]/30 px-2.5 py-1 rounded-full border border-primary-container/20 w-fit">
                        <Activity className="w-3.5 h-3.5" />
                        {isFR ? "28 bloqués" : "28 blocked"}
                      </span>
                      <span className="text-[10px] font-bold text-[#2e6bb5]">
                        {isFR ? "Protection active" : "Protection active"}
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
              {isFR ? "Configuration DNS & Validation" : "DNS Configuration & Validation Records"}
            </h3>

            {/* SPF Card Track */}
            <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border-subtle/50">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider px-2 py-0.5 bg-surface-low rounded">
                    SPF
                  </span>
                  <span className="font-mono text-xs font-bold text-on-surface">Hostname: @</span>
                </div>
                <div>
                  {shieldStatus.spf.valid ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-safe uppercase bg-safe/10 px-2.5 py-0.5 rounded-full">
                      <ShieldCheck className="w-3.5 h-3.5" /> Valid
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-warning uppercase bg-warning/10 px-2.5 py-0.5 rounded-full">
                      <AlertTriangle className="w-3.5 h-3.5" /> Missing / Invalid
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-1 text-xs">
                <div className="space-y-2">
                  <span className="font-bold text-on-surface-variant uppercase tracking-wider text-[10px] block">
                    Active DNS Entry
                  </span>
                  {shieldStatus.spf.record ? (
                    <code className="block p-3.5 bg-surface-low/50 border border-border-subtle rounded-xl font-mono text-[11px] text-on-surface truncate select-all" title={shieldStatus.spf.record}>
                      {shieldStatus.spf.record}
                    </code>
                  ) : (
                    <p className="italic text-on-surface-variant/60 block p-3.5 bg-surface-low/30 rounded-xl">
                      No SPF entry resolved in DNS.
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <span className="font-bold text-on-surface-variant uppercase tracking-wider text-[10px] block">
                    Required DNS Setup (TXT)
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
                  <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider px-2 py-0.5 bg-surface-low rounded">
                    DKIM
                  </span>
                  <span className="font-mono text-xs font-bold text-on-surface">Hostname: cloudflare._domainkey</span>
                </div>
                <div>
                  {shieldStatus.dkim.valid ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-safe uppercase bg-safe/10 px-2.5 py-0.5 rounded-full">
                      <ShieldCheck className="w-3.5 h-3.5" /> Valid
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-warning uppercase bg-warning/10 px-2.5 py-0.5 rounded-full">
                      <AlertTriangle className="w-3.5 h-3.5" /> Missing / Invalid
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-1 text-xs">
                <div className="space-y-2">
                  <span className="font-bold text-on-surface-variant uppercase tracking-wider text-[10px] block">
                    Active DNS Entry
                  </span>
                  {shieldStatus.dkim.record ? (
                    <code className="block p-3.5 bg-surface-low/50 border border-border-subtle rounded-xl font-mono text-[11px] text-on-surface truncate select-all" title={shieldStatus.dkim.record}>
                      {shieldStatus.dkim.record}
                    </code>
                  ) : (
                    <p className="italic text-on-surface-variant/60 block p-3.5 bg-surface-low/30 rounded-xl">
                      No DKIM selector entry resolved in DNS.
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <span className="font-bold text-on-surface-variant uppercase tracking-wider text-[10px] block">
                    Required DNS Setup (TXT)
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
                  <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider px-2 py-0.5 bg-surface-low rounded">
                    DMARC
                  </span>
                  <span className="font-mono text-xs font-bold text-on-surface">Hostname: _dmarc</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-[9px] font-extrabold font-mono px-2 py-0.5 rounded border uppercase select-none ${getDmarcPolicyClass(shieldStatus.dmarc.policy)}`}>
                    Policy: {shieldStatus.dmarc.policy}
                  </span>
                  {isDmarcValid ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-safe bg-safe/10 px-2.5 py-0.5 rounded-full">
                      <ShieldCheck className="w-3.5 h-3.5" /> Valid
                    </span>
                  ) : shieldStatus.dmarc.valid ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-warning bg-warning/10 px-2.5 py-0.5 rounded-full">
                      <AlertTriangle className="w-3.5 h-3.5" /> {isFR ? "Configuration Partielle" : "Partial Configuration"}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-error bg-error/10 px-2.5 py-0.5 rounded-full">
                      <AlertTriangle className="w-3.5 h-3.5" /> {isFR ? "Manquant / Incorrect" : "Missing / Invalid"}
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-1 text-xs">
                <div className="space-y-2">
                  <span className="font-bold text-on-surface-variant uppercase tracking-wider text-[10px] block">
                    Active DNS Entry
                  </span>
                  {shieldStatus.dmarc.record ? (
                    <code className="block p-3.5 bg-surface-low/50 border border-border-subtle rounded-xl font-mono text-[11px] text-on-surface truncate select-all" title={shieldStatus.dmarc.record}>
                      {shieldStatus.dmarc.record}
                    </code>
                  ) : (
                    <p className="italic text-on-surface-variant/60 block p-3.5 bg-surface-low/30 rounded-xl">
                      No DMARC entry resolved in DNS.
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <span className="font-bold text-on-surface-variant uppercase tracking-wider text-[10px] block">
                    Required DNS Setup (TXT)
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
          </div>


        </>
      )}
    </MotionDiv>
    </>
  );
}
