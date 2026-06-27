import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  Copy,
  Check,
  RefreshCw,
  AlertTriangle,
  Globe,
  Lock,
  Skull,
  Award,
} from "lucide-react";
import { Button } from "../components/ui/button";
import {
  useCloudflareList,
  useDomainShieldStatus,
  DomainShieldStatus,
} from "../lib/api";

const MotionDiv = motion.div as any;

export default function DomainShieldRoute() {
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
      className="space-y-8"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
            {t("domain_shield.title")}
          </h1>
          <p className="text-sm text-on-surface-variant mt-1">
            {t("domain_shield.subtitle")}
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
              className="px-3.5 py-2 bg-white border border-border-subtle rounded-lg text-sm text-on-surface-variant font-semibold focus:outline-none focus:border-primary transition-all cursor-pointer shadow-sm"
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
        <div className="bg-white rounded-xl border border-border-subtle p-12 text-center text-on-surface-variant/50 max-w-lg mx-auto flex flex-col items-center justify-center shadow-sm">
          <Globe className="w-12 h-12 text-on-surface-variant/30 mb-3" />
          <p className="font-semibold text-sm text-on-surface">No Domain Shield active</p>
          <p className="text-xs mt-1">
            Please integrate a domain via Cloudflare in the settings section to enable continuous domain health auditing.
          </p>
        </div>
      ) : shieldLoading ? (
        <div className="space-y-6">
          <div className="h-40 bg-surface-low rounded-xl animate-pulse" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="h-32 bg-surface-low rounded-xl animate-pulse" />
            <div className="h-32 bg-surface-low rounded-xl animate-pulse" />
            <div className="h-32 bg-surface-low rounded-xl animate-pulse" />
          </div>
        </div>
      ) : shieldError || !shieldStatus ? (
        <div className="bg-white rounded-xl border border-border-subtle p-8 text-center text-on-surface flex flex-col items-center justify-center max-w-md mx-auto">
          <ShieldAlert className="w-10 h-10 text-error mb-3" />
          <p className="font-semibold text-sm">{t("common.error_occurred")}</p>
          <p className="text-xs text-on-surface-variant mt-1">Could not fetch DNS security validation tags.</p>
        </div>
      ) : (
        <>
          {/* Main Hero row: Reputation Score Grade */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-stretch">
            {/* Reputation Ring */}
            <div className="md:col-span-4 bg-white rounded-xl border border-border-subtle p-6 flex flex-col items-center justify-center text-center shadow-sm relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary via-safe to-secondary" />
              <p className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant/70 mb-4 flex items-center gap-1.5">
                <Award className="w-3.5 h-3.5 text-primary" />
                {t("domain_shield.reputation")}
              </p>

              <div className="relative w-36 h-36 flex items-center justify-center">
                {/* SVG Progress Circle */}
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="#f3f4f6"
                    strokeWidth="8"
                    fill="transparent"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="var(--color-primary, #6366f1)"
                    strokeWidth="8"
                    fill="transparent"
                    strokeDasharray={251.2}
                    strokeDashoffset={251.2 - (251.2 * shieldStatus.reputation_score) / 100}
                    strokeLinecap="round"
                    className="transition-all duration-1000 ease-out"
                  />
                </svg>
                <div className="absolute flex flex-col items-center justify-center">
                  <span className="font-display font-bold text-5xl text-on-surface tracking-tighter">
                    {shieldStatus.score_grade}
                  </span>
                  <span className="text-[11px] font-bold font-mono text-on-surface-variant/60 mt-0.5">
                    {shieldStatus.reputation_score}/100
                  </span>
                </div>
              </div>
              <p className="text-[11px] text-on-surface-variant/60 mt-4 leading-relaxed max-w-[200px]">
                {t("domain_shield.grade_desc")}
              </p>
            </div>

            {/* DNS Protocol Monitors */}
            <div className="md:col-span-8 grid grid-cols-1 sm:grid-cols-3 gap-6">
              {/* SPF Record Card */}
              <div className="bg-white rounded-xl border border-border-subtle p-5 flex flex-col justify-between shadow-sm">
                <div>
                  <span className="text-[10px] font-bold text-on-surface-variant/60 uppercase block tracking-wider">
                    {t("domain_shield.dns_spf")}
                  </span>
                  <h3 className="font-display font-semibold text-lg text-on-surface mt-1.5 truncate select-all">
                    {selectedDomain}
                  </h3>
                </div>

                <div className="mt-4 pt-3 border-t border-border-subtle/50 space-y-2">
                  <div className="flex items-center gap-1.5">
                    {shieldStatus.spf.valid ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-safe">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        {t("domain_shield.status_valid")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-warning">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {t("domain_shield.status_missing")}
                      </span>
                    )}
                  </div>
                  {shieldStatus.spf.record ? (
                    <p className="text-[10px] font-mono text-on-surface-variant/70 leading-normal truncate select-all" title={shieldStatus.spf.record}>
                      {shieldStatus.spf.record}
                    </p>
                  ) : (
                    <p className="text-[10px] text-on-surface-variant/50 leading-normal italic">
                      No SPF TXT record returned.
                    </p>
                  )}
                </div>
              </div>

              {/* DKIM Selector Card */}
              <div className="bg-white rounded-xl border border-border-subtle p-5 flex flex-col justify-between shadow-sm">
                <div>
                  <span className="text-[10px] font-bold text-on-surface-variant/60 uppercase block tracking-wider">
                    {t("domain_shield.dns_dkim")}
                  </span>
                  <h3 className="font-display font-semibold text-lg text-on-surface mt-1.5 truncate select-all">
                    cloudflare._domainkey
                  </h3>
                </div>

                <div className="mt-4 pt-3 border-t border-border-subtle/50 space-y-2">
                  <div className="flex items-center gap-1.5">
                    {shieldStatus.dkim.valid ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-safe">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        {t("domain_shield.status_valid")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-warning">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {t("domain_shield.status_missing")}
                      </span>
                    )}
                  </div>
                  {shieldStatus.dkim.record ? (
                    <p className="text-[10px] font-mono text-on-surface-variant/70 leading-normal truncate select-all" title={shieldStatus.dkim.record}>
                      {shieldStatus.dkim.record}
                    </p>
                  ) : (
                    <p className="text-[10px] text-on-surface-variant/50 leading-normal italic">
                      No key found for selector.
                    </p>
                  )}
                </div>
              </div>

              {/* DMARC Policy Card */}
              <div className="bg-white rounded-xl border border-border-subtle p-5 flex flex-col justify-between shadow-sm">
                <div>
                  <span className="text-[10px] font-bold text-on-surface-variant/60 uppercase block tracking-wider">
                    {t("domain_shield.dns_dmarc")}
                  </span>
                  <h3 className="font-display font-semibold text-lg text-on-surface mt-1.5 truncate select-all">
                    _dmarc.{selectedDomain}
                  </h3>
                </div>

                <div className="mt-4 pt-3 border-t border-border-subtle/50 space-y-2">
                  <div className="flex items-center gap-1.5 justify-between">
                    {shieldStatus.dmarc.valid ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-safe">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        {t("domain_shield.status_valid")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-warning">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {t("domain_shield.status_missing")}
                      </span>
                    )}
                    <span className={`text-[9px] font-bold font-mono px-1.5 py-0.5 rounded border uppercase ${getDmarcPolicyClass(shieldStatus.dmarc.policy)}`}>
                      {shieldStatus.dmarc.policy === "none" ? t("domain_shield.policy_none").split(" ")[0] : shieldStatus.dmarc.policy}
                    </span>
                  </div>
                  {shieldStatus.dmarc.record ? (
                    <p className="text-[10px] font-mono text-on-surface-variant/70 leading-normal truncate select-all" title={shieldStatus.dmarc.record}>
                      {shieldStatus.dmarc.record}
                    </p>
                  ) : (
                    <p className="text-[10px] text-on-surface-variant/50 leading-normal italic">
                      No DMARC policy configured.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Secondary Stats Row: SSL cert countdown, blacklist status */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* SSL Status Card */}
            <div className="bg-white rounded-xl border border-border-subtle p-6 shadow-sm flex items-start gap-4">
              <div className="p-3 bg-primary/[0.06] rounded-xl text-primary shrink-0">
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
                    <p className="text-xs text-on-surface-variant/60">
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
            <div className="bg-white rounded-xl border border-border-subtle p-6 shadow-sm flex items-start gap-4">
              <div className="p-3 bg-primary/[0.06] rounded-xl text-primary shrink-0">
                <Skull className="w-6 h-6 stroke-[1.5]" />
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-on-surface">
                  {t("domain_shield.blacklist_monitor")}
                </h4>
                <p className="text-sm font-semibold text-safe">
                  {t("domain_shield.blacklist_clean")}
                </p>
                <p className="text-xs text-on-surface-variant/60 leading-normal max-w-sm">
                  We check Spamhaus, SORBS, Barracuda, and 50+ other domain health blocklists to ensure your outgoing emails land in the primary inbox.
                </p>
              </div>
            </div>
          </div>

          {/* copyable wizard TXT records card */}
          <div className="bg-white rounded-xl border border-border-subtle p-6 shadow-sm space-y-6">
            <div>
              <h3 className="font-display font-semibold text-[17px] text-on-surface">
                {t("domain_shield.wizard_title")}
              </h3>
              <p className="text-xs text-on-surface-variant/70 mt-0.5">
                {t("domain_shield.wizard_desc")}
              </p>
            </div>

            <div className="space-y-4">
              {/* SPF Record Copier */}
              <div className="bg-surface-low/30 rounded-xl p-4 border border-border-subtle/50 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div className="space-y-1 min-w-0">
                  <span className="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-wider block">
                    SPF TXT RECORD (Hostname: @)
                  </span>
                  <code className="text-xs font-mono font-semibold text-primary block truncate max-w-lg select-all">
                    v=spf1 include:spf.cloudflare.com include:sicurre.com ~all
                  </code>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopy("spf", "v=spf1 include:spf.cloudflare.com include:sicurre.com ~all")}
                  className="gap-1.5 text-xs self-end sm:self-center"
                >
                  {copiedKey === "spf" ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-safe" />
                      <span>{t("domain_shield.copied")}</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-on-surface-variant" />
                      <span>{t("domain_shield.copy_record")}</span>
                    </>
                  )}
                </Button>
              </div>

              {/* DKIM Record Copier */}
              <div className="bg-surface-low/30 rounded-xl p-4 border border-border-subtle/50 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div className="space-y-1 min-w-0">
                  <span className="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-wider block">
                    DKIM TXT RECORD (Hostname: cloudflare._domainkey)
                  </span>
                  <code className="text-xs font-mono font-semibold text-primary block truncate max-w-lg select-all">
                    v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1+z7s...
                  </code>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopy("dkim", "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1+z7s...")}
                  className="gap-1.5 text-xs self-end sm:self-center"
                >
                  {copiedKey === "dkim" ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-safe" />
                      <span>{t("domain_shield.copied")}</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-on-surface-variant" />
                      <span>{t("domain_shield.copy_record")}</span>
                    </>
                  )}
                </Button>
              </div>

              {/* DMARC Record Copier */}
              <div className="bg-surface-low/30 rounded-xl p-4 border border-border-subtle/50 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div className="space-y-1 min-w-0">
                  <span className="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-wider block">
                    DMARC TXT RECORD (Hostname: _dmarc)
                  </span>
                  <code className="text-xs font-mono font-semibold text-primary block truncate max-w-lg select-all">
                    v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc@sicurre.com
                  </code>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopy("dmarc", "v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc@sicurre.com")}
                  className="gap-1.5 text-xs self-end sm:self-center"
                >
                  {copiedKey === "dmarc" ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-safe" />
                      <span>{t("domain_shield.copied")}</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-on-surface-variant" />
                      <span>{t("domain_shield.copy_record")}</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </>
      )}
    </MotionDiv>
  );
}
