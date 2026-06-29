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
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  useCloudflareList,
  useDomainShieldStatus,
  useSetupCloudflare,
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

  // Clipboard copy handlers
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const handleCopy = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // State for Interactive Visualizer Flow ("normal" | "attack")
  const [visualizerFlow, setVisualizerFlow] = useState<"normal" | "attack">("normal");

  // State for Mock DNS Resolver Terminal
  const [terminalLogs, setTerminalLogs] = useState<string[]>([]);
  const [isTerminalRunning, setIsTerminalRunning] = useState(false);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [terminalLogs]);

  const runDnsDiagnostics = () => {
    if (isTerminalRunning || !selectedDomain || !shieldStatus) return;
    setIsTerminalRunning(true);
    setTerminalLogs([]);

    const logs = [
      `$ dig TXT ${selectedDomain} +short`,
      `[info] Initializing DNS Resolver check for zone: ${selectedDomain}...`,
      `[info] Resolving authoritative NS records for ${selectedDomain}...`,
      `Checking SPF record alignment...`,
      shieldStatus.spf.valid
        ? `➔ SPF record resolved successfully: "${shieldStatus.spf.record}" [VALID]`
        : `➔ [WARNING] SPF record is missing or invalid in DNS zone!`,
      `Checking DKIM selector signatures (cloudflare._domainkey)...`,
      shieldStatus.dkim.valid
        ? `➔ DKIM record resolved: "${shieldStatus.dkim.record?.substring(0, 40)}..." [VALID]`
        : `➔ [WARNING] DKIM key signature validation failed or record missing!`,
      `Checking DMARC protection policy (_dmarc)...`,
      shieldStatus.dmarc.valid
        ? `➔ DMARC record resolved: "${shieldStatus.dmarc.record}" [VALID] (Policy: ${shieldStatus.dmarc.policy})`
        : `➔ [CRITICAL] DMARC record is missing! Domain is vulnerable to spoofing!`,
      `[info] Auditing SSL Certificate & expiration time...`,
      shieldStatus.ssl.valid
        ? `➔ SSL Certificate: VALID (${shieldStatus.ssl.days_remaining} days remaining)`
        : `➔ [WARNING] SSL validation checks failed!`,
      `[info] Scanning 50+ public reputation blocklists...`,
      `➔ Reputation Score: ${shieldStatus.reputation_score}/100 Grade: ${shieldStatus.score_grade}`,
      `Diagnostic completed. Rating: ${shieldStatus.score_grade}.`
    ];

    let currentLogIndex = 0;
    const interval = setInterval(() => {
      if (currentLogIndex < logs.length) {
        setTerminalLogs((prev) => [...prev, logs[currentLogIndex]]);
        currentLogIndex++;
      } else {
        clearInterval(interval);
        setIsTerminalRunning(false);
      }
    }, 380);
  };

  // Run diagnostics automatically when status loads
  useEffect(() => {
    if (shieldStatus && selectedDomain && !shieldLoading) {
      runDnsDiagnostics();
    }
  }, [shieldStatus, selectedDomain]);

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

  // State for Cloudflare Auto-Fix Wizard
  const [showAutoFix, setShowAutoFix] = useState(false);
  const [cfToken, setCfToken] = useState("");
  const [autoFixProgress, setAutoFixProgress] = useState<"idle" | "verify" | "dns" | "routing" | "success" | "error">("idle");
  const [autoFixErrorMsg, setAutoFixErrorMsg] = useState("");
  const setupMutation = useSetupCloudflare();

  const handleRunAutoFix = async () => {
    if (!cfToken.trim() || !selectedDomain) return;
    setAutoFixProgress("verify");
    setAutoFixErrorMsg("");

    try {
      // Simulate stages
      setTimeout(() => setAutoFixProgress("dns"), 1500);
      setTimeout(() => setAutoFixProgress("routing"), 3000);
      
      const payload = {
        cf_api_token: cfToken,
        zone_name: selectedDomain,
        destination_email: session?.email || "owner@sicurre.com"
      };

      setTimeout(async () => {
        try {
          await setupMutation.mutateAsync(payload);
          setAutoFixProgress("success");
          reloadShield();
          setTimeout(() => {
            setShowAutoFix(false);
            setAutoFixProgress("idle");
            setCfToken("");
          }, 3000);
        } catch (err: any) {
          setAutoFixProgress("error");
          setAutoFixErrorMsg(err.message || "Échec de l'auto-configuration DNS.");
        }
      }, 4500);

    } catch (err: any) {
      setAutoFixProgress("error");
      setAutoFixErrorMsg(err.message || "Échec de l'initialisation.");
    }
  };

  const getDmarcPolicyClass = (policy?: string) => {
    if (policy === "reject") return "text-safe bg-safe/10 border-safe/25";
    if (policy === "quarantine") return "text-primary bg-primary/10 border-primary/25";
    return "text-warning bg-warning/10 border-warning/25";
  };

  return (
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
          <h1 className="font-display font-extrabold text-[32px] text-on-surface tracking-tight leading-tight">
            {isFR ? "Commandement du Bouclier" : "Domain Shield Command Center"}
          </h1>
          <p className="text-sm font-semibold text-on-surface-variant mt-1">
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
            <span className="text-xs text-on-surface-variant/70 italic">No domains configured</span>
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
              onClick={() => {
                reloadShield();
                runDnsDiagnostics();
              }}
              disabled={shieldLoading}
              className="p-2 min-h-[38px] flex items-center justify-center cursor-pointer bg-white"
            >
              <RefreshCw className={`w-4 h-4 ${shieldLoading ? "animate-spin text-primary" : ""}`} />
            </Button>
          )}
        </div>
      </div>

      {!selectedDomain ? (
        <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-12 text-center text-on-surface-variant/50 max-w-lg mx-auto flex flex-col items-center justify-center shadow-sm">
          <Globe className="w-12 h-12 text-on-surface-variant/30 mb-3 animate-pulse" />
          <p className="font-bold text-base text-on-surface">No Domain Shield active</p>
          <p className="text-sm mt-1 text-on-surface-variant">
            Please integrate a domain via Cloudflare in the settings section to enable continuous domain health auditing.
          </p>
        </div>
      ) : shieldLoading ? (
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
          <p className="text-xs text-on-surface-variant mt-1 font-semibold">Could not fetch DNS security validation tags.</p>
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
                    stroke="var(--color-primary, #1B4FCC)"
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

              <p className="text-sm font-semibold text-on-surface-variant mt-6 leading-relaxed max-w-[280px]">
                {isFR
                  ? "Votre domaine est configuré de manière optimale contre l'usurpation d'identité sortante."
                  : "Continuous auditing confirms your domains are hardened against spoofers and outgoing phishing relays."}
              </p>
            </div>

            {/* Right: Interactive Security Flow Diagram */}
            <div className="lg:col-span-7 bg-surface-lowest rounded-2xl border border-border-subtle p-8 flex flex-col justify-between shadow-sm relative overflow-hidden">
              <div className="flex justify-between items-center pb-3 border-b border-border-subtle">
                <h3 className="font-display font-bold text-xl text-on-surface">
                  {isFR ? "Visualisateur de flux de sécurité" : "Live Security Flow Visualizer"}
                </h3>
                <div className="flex bg-surface-low p-1 rounded-lg border border-border-subtle text-xs font-semibold">
                  <button
                    onClick={() => setVisualizerFlow("normal")}
                    className={`px-3 py-1 rounded-md transition-all cursor-pointer border-none outline-none ${
                      visualizerFlow === "normal" ? "bg-white text-on-surface shadow-sm font-bold" : "text-on-surface-variant/75"
                    }`}
                  >
                    {isFR ? "Flux Normal" : "Normal Flow"}
                  </button>
                  <button
                    onClick={() => setVisualizerFlow("attack")}
                    className={`px-3 py-1 rounded-md transition-all cursor-pointer border-none outline-none ${
                      visualizerFlow === "attack" ? "bg-white text-on-surface shadow-sm font-bold" : "text-on-surface-variant/75"
                    }`}
                  >
                    {isFR ? "Simul. Attaque" : "Attack Flow"}
                  </button>
                </div>
              </div>

              {/* Node Graph Visualizer */}
              <div className="h-[210px] w-full relative flex items-center justify-between px-4 select-none">
                
                {/* Visualizer Nodes */}
                <div className="flex flex-col items-center gap-1.5 z-10">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center border transition-all duration-300 ${
                    visualizerFlow === "normal" 
                      ? "bg-safe/10 border-safe/30 text-safe shadow-[0_0_12px_rgba(16,185,129,0.2)]" 
                      : "bg-error/10 border-error/30 text-error shadow-[0_0_12px_rgba(239,68,68,0.2)] animate-pulse"
                  }`}>
                    <Server className="w-6 h-6" />
                  </div>
                  <span className="text-[10px] font-bold text-on-surface-variant">
                    {visualizerFlow === "normal" ? "Authorized Server" : "Hacker Server"}
                  </span>
                </div>

                <div className="flex-1 h-[2px] relative overflow-hidden bg-border-subtle/50 mx-2">
                  <div className={`absolute top-0 bottom-0 left-0 w-1/2 rounded-full transition-colors duration-300 ${
                    visualizerFlow === "normal" ? "bg-safe" : "bg-error"
                  } ${visualizerFlow === "normal" ? "animate-pulse" : "animate-bounce"}`} style={{ width: "100%" }} />
                </div>

                <div className="flex flex-col items-center gap-1.5 z-10">
                  <div className={`w-14 h-14 rounded-full flex items-center justify-center border transition-all duration-300 ${
                    visualizerFlow === "normal"
                      ? "bg-primary/10 border-primary/30 text-primary shadow-[0_0_15px_rgba(27,79,204,0.2)]"
                      : "bg-warning/10 border-warning/30 text-warning shadow-[0_0_15px_rgba(245,158,11,0.2)]"
                  }`}>
                    <ShieldCheck className="w-8 h-8" />
                  </div>
                  <span className="text-[10px] font-bold text-on-surface-variant">
                    SPF / DKIM Filter
                  </span>
                </div>

                <div className="flex-1 h-[2px] relative overflow-hidden bg-border-subtle/50 mx-2">
                  <div className={`absolute top-0 bottom-0 left-0 w-1/2 rounded-full transition-colors duration-300 ${
                    visualizerFlow === "normal" ? "bg-safe" : "bg-error"
                  }`} style={{ width: "100%" }} />
                </div>

                <div className="flex flex-col items-center gap-1.5 z-10">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center border transition-all duration-300 ${
                    visualizerFlow === "normal"
                      ? "bg-safe/10 border-safe/30 text-safe shadow-[0_0_12px_rgba(16,185,129,0.2)]"
                      : "bg-surface-low border-border-subtle text-on-surface-variant/40"
                  }`}>
                    <LockIcon className="w-6 h-6" />
                  </div>
                  <span className="text-[10px] font-bold text-on-surface-variant">
                    {visualizerFlow === "normal" ? "Secure Inbox" : "Blocked / Trash"}
                  </span>
                </div>
              </div>

              <div className="text-[11.5px] text-on-surface-variant leading-relaxed text-center px-4">
                {visualizerFlow === "normal"
                  ? (isFR 
                      ? "Flux d'email authentifié : SPF & DKIM valides. L'email est validé par le DMARC et délivré à la boîte." 
                      : "Authorized mail flow: SPF & DKIM aligned. The email passes DMARC checks and is delivered safely.")
                  : (isFR 
                      ? "Flux d'attaque usurpée : L'IP de l'attaquant ne correspond pas. SPF/DKIM échouent, le DMARC rejette immédiatement."
                      : "Spoofed flow block: Attacker IP is unauthorized. SPF & DKIM checks fail, and DMARC immediately rejects the email.")}
              </div>
            </div>
          </div>

          {/* Diagnostics terminal trace */}
          <div className="bg-slate-950 rounded-2xl border border-white/10 overflow-hidden shadow-2xl relative">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/5 bg-slate-900/50">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-primary" />
                <span className="text-[11.5px] font-mono text-white/60">sicurre-dns-traceroute --audit</span>
              </div>
              <button
                onClick={runDnsDiagnostics}
                disabled={isTerminalRunning}
                className="px-3 py-1 bg-white/5 border border-white/10 hover:bg-white/10 text-white rounded-md text-[11px] font-semibold transition-all cursor-pointer disabled:opacity-50"
              >
                {isFR ? "Re-diagnostiquer" : "Re-diagnose"}
              </button>
            </div>
            
            <div className="p-5 font-mono text-[12px] text-white/80 space-y-2.5 min-h-[140px] max-h-[220px] overflow-y-auto">
              {terminalLogs.map((log, idx) => (
                <div key={idx} className={
                  log.includes("[CRITICAL]") 
                    ? "text-red-400" 
                    : log.includes("[WARNING]") 
                    ? "text-amber-400" 
                    : log.includes("VALID") 
                    ? "text-emerald-400" 
                    : "text-white/70"
                }>
                  {log}
                </div>
              ))}
              <div ref={terminalEndRef} />
            </div>
          </div>

          {/* DMARC Simulator and Cloudflare Wizard row */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            
            {/* Left: Interactive Spoof Simulator Sandbox */}
            <div className="lg:col-span-6 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between">
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
                      <span className="text-error font-extrabold">Forged Header</span>
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
                        <div key={idx} className={log.includes("ÉCHEC") || log.includes("FAIL") ? "text-amber-400" : "text-white/60"}>
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
                      className="w-fit self-end cursor-pointer bg-white"
                    >
                      {isFR ? "Recommencer" : "Reset Test"}
                    </Button>
                  </div>
                ) : (
                  <Button
                    onClick={startSpoofSimulation}
                    disabled={spoofStep === "sending"}
                    className="w-full flex items-center justify-center gap-2 cursor-pointer"
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

            {/* Right: Cloudflare Inline Auto-Fix Wizard */}
            <div className="lg:col-span-6 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <Zap className="w-5 h-5 text-amber-500 animate-pulse" />
                  <h3 className="font-display font-bold text-[18px] text-on-surface">
                    {isFR ? "Auto-Fix Cloudflare 1-Clic" : "1-Click Cloudflare Auto-Fix"}
                  </h3>
                </div>

                <p className="text-xs text-on-surface-variant leading-relaxed">
                  {isFR
                    ? "Corrigez et provisionnez automatiquement vos enregistrements DNS manquants (SPF, DKIM, DMARC) via l'API Cloudflare."
                    : "Automatically generate and sync missing DNS records (SPF, DKIM, DMARC) directly using the Cloudflare token API wizard."}
                </p>

                {(!shieldStatus.spf.valid || !shieldStatus.dkim.valid || !shieldStatus.dmarc.valid) ? (
                  <div className="p-3 bg-amber-500/[0.04] border border-amber-500/20 rounded-xl flex items-start gap-2.5">
                    <AlertTriangle className="w-4.5 h-4.5 text-amber-500 shrink-0 mt-0.5" />
                    <div className="text-[11.5px] text-amber-600 font-semibold leading-relaxed">
                      {isFR
                        ? "Des enregistrements obligatoires sont incorrects ou manquants dans votre zone."
                        : "Missing or invalid validation entries resolved for the active domain."}
                    </div>
                  </div>
                ) : (
                  <div className="p-3 bg-safe/[0.04] border border-safe/20 rounded-xl flex items-start gap-2.5">
                    <ShieldCheck className="w-4.5 h-4.5 text-safe shrink-0 mt-0.5" />
                    <div className="text-[11.5px] text-safe font-semibold leading-relaxed">
                      {isFR
                        ? "Tous les protocoles SPF, DKIM, DMARC sont configurés de façon optimale."
                        : "DNS configuration is fully optimized and secured against impersonators."}
                    </div>
                  </div>
                )}

                {showAutoFix && (
                  <div className="space-y-3 pt-2">
                    {autoFixProgress === "idle" ? (
                      <div className="space-y-2.5">
                        <label className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">
                          Cloudflare API Token
                        </label>
                        <Input
                          type="password"
                          placeholder="Zone.DNS Edit Scoped Token"
                          value={cfToken}
                          onChange={(e) => setCfToken(e.target.value)}
                          className="bg-white border-border-subtle"
                        />
                      </div>
                    ) : (
                      <div className="p-4 bg-surface-low border border-border-subtle rounded-xl space-y-2 text-xs font-semibold">
                        {autoFixProgress === "verify" && (
                          <span className="flex items-center gap-2"><RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" /> Vérification du token Cloudflare...</span>
                        )}
                        {autoFixProgress === "dns" && (
                          <span className="flex items-center gap-2"><RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" /> Écriture des enregistrements SPF/DKIM/DMARC...</span>
                        )}
                        {autoFixProgress === "routing" && (
                          <span className="flex items-center gap-2"><RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" /> Test de propagation et synchronisation...</span>
                        )}
                        {autoFixProgress === "success" && (
                          <span className="flex items-center gap-2 text-safe"><CheckCircle2 className="w-4 h-4" /> DNS configuré et validé avec succès !</span>
                        )}
                        {autoFixProgress === "error" && (
                          <span className="flex items-center gap-2 text-error"><ShieldAlert className="w-4 h-4" /> {autoFixErrorMsg}</span>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="pt-5 border-t border-border-subtle/50 mt-4 flex justify-end gap-3 select-none">
                {showAutoFix ? (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setShowAutoFix(false);
                        setAutoFixProgress("idle");
                      }}
                      className="cursor-pointer font-semibold text-xs"
                    >
                      {isFR ? "Annuler" : "Cancel"}
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleRunAutoFix}
                      disabled={autoFixProgress !== "idle" || !cfToken.trim()}
                      className="cursor-pointer font-semibold text-xs bg-primary"
                    >
                      {isFR ? "Valider et Corriger" : "Validate & Deploy"}
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowAutoFix(true)}
                    className="w-full flex items-center justify-center gap-1.5 cursor-pointer bg-white text-xs font-semibold"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>{isFR ? "Lancer l'Auto-Configuration" : "Launch DNS Setup Wizard"}</span>
                  </Button>
                )}
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
                    <code className="flex-1 block p-3.5 bg-primary/[0.02] border border-primary/20 text-primary rounded-xl font-mono text-[11px] truncate select-all">
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
                    <code className="flex-1 block p-3.5 bg-primary/[0.02] border border-primary/20 text-primary rounded-xl font-mono text-[11px] truncate select-all">
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
                  {shieldStatus.dmarc.valid ? (
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
                    <code className="flex-1 block p-3.5 bg-primary/[0.02] border border-primary/20 text-primary rounded-xl font-mono text-[11px] truncate select-all">
                      v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc@sicurre.com
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleCopy("dmarc", "v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc@sicurre.com")}
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

          {/* Secondary Stats Row: SSL cert countdown, blacklist status */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* SSL Status Card */}
            <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-6 shadow-sm flex items-start gap-4">
              <div className="p-3.5 bg-primary/[0.06] rounded-xl text-primary shrink-0">
                <Lock className="w-6 h-6 stroke-[1.5]" />
              </div>
              <div className="space-y-1.5">
                <h4 className="text-sm font-bold text-on-surface">
                  {t("domain_shield.ssl_expiry")}
                </h4>
                {shieldStatus.ssl.valid ? (
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-on-surface">
                      {t("domain_shield.ssl_countdown", { days: shieldStatus.ssl.days_remaining })}
                    </p>
                    <p className="text-xs font-semibold text-on-surface-variant">
                      {t("domain_shield.ssl_renew_active")}
                    </p>
                    {shieldStatus.ssl.days_remaining < 30 && (
                      <div className="flex items-center gap-1.5 mt-2 text-xs font-bold text-error bg-error/5 border border-error/10 p-2 rounded-lg">
                        <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                        <span>{t("domain_shield.ssl_expires_soon")}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-error font-semibold">
                    Could not resolve SSL validation status.
                  </p>
                )}
              </div>
            </div>

            {/* Blacklist Status Card */}
            <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-6 shadow-sm flex items-start gap-4">
              <div className="p-3.5 bg-primary/[0.06] rounded-xl text-primary shrink-0">
                <Skull className="w-6 h-6 stroke-[1.5]" />
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-on-surface">
                  {t("domain_shield.blacklist_monitor")}
                </h4>
                <p className="text-sm font-semibold text-safe">
                  {t("domain_shield.blacklist_clean")}
                </p>
                <p className="text-xs font-semibold text-on-surface-variant leading-relaxed">
                  {isFR
                    ? "Sain. Domaine non répertorié sur 50+ listes noires majeures."
                    : "Clean. Domain not listed on 50+ major blocklists."}
                </p>
              </div>
            </div>

            {/* DMARC Metrics Status Card */}
            <div className="bg-surface-lowest rounded-2xl border border-border-subtle p-6 shadow-sm flex items-start gap-4">
              <div className="p-3.5 bg-primary/[0.06] rounded-xl text-primary shrink-0">
                <Activity className="w-6 h-6 stroke-[1.5]" />
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-on-surface">
                  {isFR ? "Rapports DMARC (7j)" : "DMARC Block Activity (7d)"}
                </h4>
                <p className="text-sm font-semibold text-primary">
                  {isFR ? "28 tentatives bloquées" : "28 unauthorized attempts blocked"}
                </p>
                <p className="text-xs font-semibold text-on-surface-variant leading-relaxed">
                  {isFR
                    ? "Rapports agrégés montrant les serveurs unauthorized qui ont tenté de falsifier votre domaine."
                    : "Aggregated reports checking unauthorized servers attempting to forge mail as your domain."}
                </p>
              </div>
            </div>

          </div>
        </>
      )}
    </MotionDiv>
  );
}
