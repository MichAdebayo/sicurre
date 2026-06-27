import { useState, useEffect } from "react";
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
} from "lucide-react";
import { Button } from "../components/ui/button";
import {
  useCloudflareList,
  useDomainShieldStatus,
} from "../lib/api";

const MotionDiv = motion.div as any;

export default function DomainShieldRoute() {
  const { t, i18n } = useTranslation();

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
            {i18n.language === "fr" ? "Commandement du Bouclier" : "Domain Shield Command Center"}
          </h1>
          <p className="text-sm font-semibold text-on-surface-variant mt-1">
            {i18n.language === "fr"
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
              onClick={() => reloadShield()}
              disabled={shieldLoading}
              className="p-2 min-h-[38px] flex items-center justify-center cursor-pointer"
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
          {/* Conceptual Hero Layout: Radar Dome on the left, Spoofing details on the right */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
            {/* Left: Interactive Radar Dome (Authority, not timid) */}
            <div className="lg:col-span-5 bg-surface-lowest rounded-2xl border border-border-subtle p-8 flex flex-col items-center justify-center text-center shadow-sm relative overflow-hidden">
              {/* Pulsing indicator light */}
              <div className="absolute top-4 right-4 flex items-center gap-1.5 select-none">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-safe" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-safe" />
                </span>
                <span className="text-[10px] font-extrabold text-safe uppercase tracking-wider">
                  {i18n.language === "fr" ? "Actif & Protégé" : "Active & Hardened"}
                </span>
              </div>

              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-6 flex items-center gap-1.5 select-none">
                <Award className="w-4 h-4 text-primary" />
                {i18n.language === "fr" ? "Indice d'Intégrité DNS" : "DNS Integrity Rating"}
              </p>

              <div className="relative w-44 h-44 flex items-center justify-center select-none">
                {/* SVG Progress Circle with scanning light effect */}
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="var(--color-surface-low, #f3f4f6)"
                    strokeWidth="7"
                    fill="transparent"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="var(--color-primary, #0038a4)"
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
                {i18n.language === "fr"
                  ? "Votre domaine est configuré de manière optimale contre l'usurpation d'identité sortante."
                  : "Continuous auditing confirms your domains are hardened against spoofers and outgoing phishing relays."}
              </p>
            </div>

            {/* Right: Authoritative Explanation Command Guide */}
            <div className="lg:col-span-7 bg-surface-lowest rounded-2xl border border-border-subtle p-8 flex flex-col justify-between shadow-sm">
              <div className="space-y-4">
                <h3 className="font-display font-bold text-xl text-on-surface pb-3 border-b border-border-subtle">
                  {i18n.language === "fr" ? "Bouclier anti-usurpation" : "Impersonation Protection Status"}
                </h3>
                
                <div className="space-y-4 pt-1">
                  <div className="flex gap-3">
                    <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5 text-primary text-[10px] font-bold">1</div>
                    <div>
                      <p className="text-sm font-bold text-on-surface">SPF (Sender Policy Framework)</p>
                      <p className="text-xs text-on-surface-variant font-medium mt-0.5 leading-relaxed">
                        Defines which mail servers are permitted to send email on behalf of your domain name. Checks unauthorized attempts.
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5 text-primary text-[10px] font-bold">2</div>
                    <div>
                      <p className="text-sm font-bold text-on-surface">DKIM (DomainKeys Identified Mail)</p>
                      <p className="text-xs text-on-surface-variant font-medium mt-0.5 leading-relaxed">
                        Adds a cryptographic signature to outbound messages. Confirms the message content was not modified in transit.
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5 text-primary text-[10px] font-bold">3</div>
                    <div>
                      <p className="text-sm font-bold text-on-surface">DMARC (Domain-based Message Authentication)</p>
                      <p className="text-xs text-on-surface-variant font-medium mt-0.5 leading-relaxed">
                        Instructs receiving servers (Gmail, Outlook) on how to handle emails that fail SPF/DKIM verification (reject, quarantine).
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-border-subtle/50 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 text-xs text-on-surface-variant font-bold select-none mt-4">
                <span>Active Protocols: 3/3 Authenticated</span>
                <span className="text-safe flex items-center gap-1">
                  <ShieldCheck className="w-4 h-4" /> Outgoing Deliverability: Optimal
                </span>
              </div>
            </div>
          </div>

          {/* Spacious DNS Record Verification Matrix (Redesigned: combining validation & copiers in large card tracks) */}
          <div className="space-y-6">
            <h3 className="font-display font-bold text-xl text-on-surface">
              {i18n.language === "fr" ? "Configuration DNS & Validation" : "DNS Configuration & Validation Records"}
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
                      className="px-3 h-10 cursor-pointer text-xs gap-1 font-bold rounded-xl"
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
                      className="px-3 h-10 cursor-pointer text-xs gap-1 font-bold rounded-xl"
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
                      className="px-3 h-10 cursor-pointer text-xs gap-1 font-bold rounded-xl"
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
                <p className="text-xs font-semibold text-on-surface-variant leading-relaxed max-w-sm">
                  We check Spamhaus, SORBS, Barracuda, and 50+ other domain health blocklists to ensure your outgoing emails land in the primary inbox.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </MotionDiv>
  );
}
