import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  ShieldCheck,
  Mail,
  Settings,
  Play,
  Award,
  TrendingUp,
  Cpu,
  Info,
  AlertTriangle,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { VerdictBadge } from "../components/threats/verdict-badge";
import {
  AuthSession,
  useKPIStats,
  useThreatLogs,
  useDatasets,
  useRunPipeline,
  useCloudflareList,
  useDomainShieldStatus,
} from "../lib/api";

const MotionDiv = motion.div as any;

interface DashboardRouteProps {
  session: AuthSession;
  onGoToSettings: (tab?: string) => void;
}

function KPIBlock({
  label,
  value,
  variant = "default",
}: {
  label: string;
  value: string;
  variant?: "default" | "phishing" | "spam" | "legitimate" | "primary";
}) {
  const styles = {
    default: "border-border-subtle bg-white text-on-surface",
    primary: "border-primary/30 bg-primary/[0.02] text-primary shadow-sm",
    phishing: "border-error/30 bg-error/[0.02] text-error shadow-sm",
    spam: "border-secondary/30 bg-secondary/[0.02] text-secondary shadow-sm",
    legitimate: "border-safe/30 bg-safe/[0.02] text-safe shadow-sm",
  };

  const textStyles = {
    default: "text-on-surface",
    primary: "text-primary",
    phishing: "text-error",
    spam: "text-secondary",
    legitimate: "text-safe",
  };

  return (
    <div className={`rounded-xl border p-5 shadow-sm transition-all duration-300 ${styles[variant]}`}>
      <p className="text-[11px] font-bold text-on-surface-variant uppercase tracking-[0.12em] mb-2">
        {label}
      </p>
      <p className={`font-display font-bold text-[32px] tracking-tight leading-none ${textStyles[variant]}`}>
        {value}
      </p>
    </div>
  );
}

export default function DashboardRoute({ session, onGoToSettings }: DashboardRouteProps) {
  const { t, i18n } = useTranslation();
  const { data: kpis, isLoading: kpisLoading } = useKPIStats();
  const { data: threats, isLoading: threatsLoading } = useThreatLogs();
  const datasetsQuery = useDatasets();
  const runPipelineMutation = useRunPipeline();
  const [pipelineSuccess, setPipelineSuccess] = useState(false);

  // States for dynamic interactive Last 7 days chart
  const [dateRange, setDateRange] = useState<"7d" | "30d" | "12m">("7d");
  const [hoveredBarIndex, setHoveredBarIndex] = useState<number | null>(null);

  // Domains & Shield status check for security score
  const { data: domainsList } = useCloudflareList();
  const hasActiveDomain = !!domainsList && domainsList.length > 0;
  const showOnboarding = session.onboarding_required || !hasActiveDomain;

  const activeDomain = hasActiveDomain
    ? (domainsList.find((d) => d.status === "active")?.zone_name || domainsList[0].zone_name)
    : "";

  const { data: shieldStatus, isLoading: shieldLoading } = useDomainShieldStatus(
    activeDomain || "",
    !!activeDomain
  );

  const handleRunPipeline = async () => {
    try {
      await runPipelineMutation.mutateAsync();
      setPipelineSuccess(true);
      setTimeout(() => setPipelineSuccess(false), 5000);
    } catch (err) {
      console.error(err);
    }
  };

  const totalScans = kpis?.raw_records_count ?? 0;
  const phishingCount = kpis?.threats_phishing_count ?? 0;
  const spamCount = kpis?.threats_spam_count ?? 0;
  const legitimateCount = kpis?.threats_legitimate_count ?? 0;

  // Generate date-aware trend metrics split between safe (legitimate) and phishing using DB data only
  const getTrendData = () => {
    const lang = i18n.language;
    const labels: string[] = [];
    const safeCounts: number[] = [];
    const phishingCounts: number[] = [];

    const threatsList = threats || [];

    if (dateRange === "7d") {
      // Last 7 days
      for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        
        const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
        const endOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

        const dailyThreats = threatsList.filter((t) => {
          const rDate = new Date(t.received_at);
          return rDate >= startOfDay && rDate <= endOfDay;
        });

        const safe = dailyThreats.filter((t) => t.verdict === "legitimate").length;
        const phish = dailyThreats.filter((t) => t.verdict === "phishing" || t.verdict === "spam" || t.verdict === "quarantine").length;

        labels.push(d.toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { weekday: "short", day: "numeric" }));
        safeCounts.push(safe);
        phishingCounts.push(phish);
      }
    } else if (dateRange === "30d") {
      // Last 30 days
      for (let i = 29; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        
        const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
        const endOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

        const dailyThreats = threatsList.filter((t) => {
          const rDate = new Date(t.received_at);
          return rDate >= startOfDay && rDate <= endOfDay;
        });

        const safe = dailyThreats.filter((t) => t.verdict === "legitimate").length;
        const phish = dailyThreats.filter((t) => t.verdict === "phishing" || t.verdict === "spam" || t.verdict === "quarantine").length;

        labels.push(d.toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { day: "numeric", month: "short" }));
        safeCounts.push(safe);
        phishingCounts.push(phish);
      }
    } else {
      // Last 12 months
      for (let i = 11; i >= 0; i--) {
        const d = new Date();
        d.setMonth(d.getMonth() - i);
        
        const startOfMonth = new Date(d.getFullYear(), d.getMonth(), 1, 0, 0, 0, 0);
        const endOfMonth = new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999);

        const monthlyThreats = threatsList.filter((t) => {
          const rDate = new Date(t.received_at);
          return rDate >= startOfMonth && rDate <= endOfMonth;
        });

        const safe = monthlyThreats.filter((t) => t.verdict === "legitimate").length;
        const phish = monthlyThreats.filter((t) => t.verdict === "phishing" || t.verdict === "spam" || t.verdict === "quarantine").length;

        labels.push(d.toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { month: "short", year: "2-digit" }));
        safeCounts.push(safe);
        phishingCounts.push(phish);
      }
    }

    return { labels, safeCounts, phishingCounts };
  };

  const trendData = getTrendData();

  const getTrendMaxVal = (data: { safeCounts: number[], phishingCounts: number[] }) => {
    let max = 1;
    for (let i = 0; i < data.safeCounts.length; i++) {
      const sum = data.safeCounts[i] + data.phishingCounts[i];
      if (sum > max) max = sum;
    }
    return max;
  };
  const maxTrendVal = getTrendMaxVal(trendData);

  const recentAlerts = threats
    ? threats.slice(0, 5).map((alertItem) => ({
        id: alertItem.id,
        time: new Date(alertItem.received_at).toLocaleTimeString(i18n.language === "fr" ? "fr-FR" : "en-US", { hour: "2-digit", minute: "2-digit" }),
        subject: alertItem.subject || t("threats.no_subject"),
        sender: alertItem.sender,
        content: alertItem.body_preview || "",
        verdict: alertItem.verdict,
        confidence: alertItem.confidence,
      }))
    : [];

  const securityScoreGrade = () => {
    if (!domainsList || domainsList.length === 0) return "—";
    if (shieldLoading) return "L";
    if (shieldStatus) return shieldStatus.score_grade;
    return "A";
  };

  const grade = securityScoreGrade();

  // Platform admin rendering
  if (session.is_platform_admin) {
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
              Console d'Administration
            </h1>
            <p className="text-sm text-on-surface-variant mt-1">
              Pilotez l'entraînement du modèle et supervisez les métriques globales
            </p>
          </div>
          <div className="rounded-lg border border-border-subtle bg-white px-4 py-3 text-right shadow-sm">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant">
              Rôle Utilisateur
            </div>
            <div className="text-lg font-bold text-primary">
              Admin Plateforme
            </div>
          </div>
        </div>

        {/* Global KPIs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <KPIBlock label="Total Scannés (Global)" value={kpisLoading ? "—" : totalScans.toLocaleString("fr-FR")} variant="primary" />
          <KPIBlock label="Phishing Bloqué" value={kpisLoading ? "—" : phishingCount.toLocaleString("fr-FR")} variant="phishing" />
          <KPIBlock label="Total Dataset Items" value={kpisLoading ? "—" : (kpis?.dataset_items_count ?? 0).toLocaleString("fr-FR")} variant="default" />
          <KPIBlock label="Statut Système" value="Actif" variant="legitimate" />
        </div>

        {/* Pipeline Controls & Verdicts */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 bg-white rounded-xl border border-border-subtle p-6 flex flex-col justify-between shadow-sm">
            <div>
              <h3 className="font-display font-semibold text-[17px] text-on-surface mb-2">
                Pipeline de Données & Entraînement ML
              </h3>
              <p className="text-sm text-on-surface-variant mb-6 leading-relaxed">
                Déclenchez manuellement le cycle de normalisation, d'annotation et d'export du dataset vers Cloudflare R2 et Kaggle pour ré-entraîner le modèle CamemBERTav2.
              </p>
            </div>
            
            <div className="space-y-4">
              {pipelineSuccess && (
                <div className="p-3 bg-safe/10 border border-safe/25 text-safe text-xs font-semibold rounded-lg">
                  Pipeline lancé avec succès ! L'exécution s'exécute en arrière-plan.
                </div>
              )}
              {runPipelineMutation.isPending ? (
                <Button disabled className="w-full flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  Lancement du pipeline...
                </Button>
              ) : (
                <Button onClick={handleRunPipeline} className="w-full flex items-center justify-center gap-2">
                  <Play className="w-4 h-4" />
                  Lancer le Pipeline de Données (`make run-pipeline`)
                </Button>
              )}
            </div>
          </div>

          <div className="lg:col-span-5 bg-white rounded-xl border border-border-subtle p-6 shadow-sm">
            <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em] mb-5">
              Répartition des verdicts globaux
            </p>
            <div className="space-y-4">
              <DistributionRow label="Légitime" count={legitimateCount} total={Math.max(totalScans, 1)} colorClass="bg-safe" />
              <DistributionRow label="Spam" count={spamCount} total={Math.max(totalScans, 1)} colorClass="bg-secondary" />
              <DistributionRow label="Phishing" count={phishingCount} total={Math.max(totalScans, 1)} colorClass="bg-error" />
            </div>
          </div>
        </div>

        {/* Datasets Table */}
        <div className="bg-white rounded-xl border border-border-subtle p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <h3 className="font-display font-semibold text-[17px] text-on-surface">
              Historique des Datasets d'Entraînement
            </h3>
            <span className="text-[11px] font-bold px-2 py-1 rounded-md bg-primary/10 text-primary uppercase">
              Provenances
            </span>
          </div>

          {datasetsQuery.isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-surface-low rounded-lg animate-pulse" />
              ))}
            </div>
          ) : !datasetsQuery.data || datasetsQuery.data.length === 0 ? (
            <div className="py-8 text-center text-on-surface-variant/70 text-sm">
              Aucun dataset enregistré pour le moment.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left font-sans">
                <thead>
                  <tr className="border-b border-border-subtle text-xs font-bold text-on-surface-variant/90 tracking-wide">
                    <th className="pb-3 pl-2">Version Tag</th>
                    <th className="pb-3">Nombre d'Éléments</th>
                    <th className="pb-3">Statut</th>
                    <th className="pb-3 pr-2 text-right">Date de Publication</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle/50 text-xs">
                  {datasetsQuery.data.map((ds) => (
                    <tr key={ds.id} className="hover:bg-surface-low/30 transition-colors">
                      <td className="py-3.5 pl-2 font-semibold text-on-surface text-xs">{ds.version_tag}</td>
                      <td className="py-3.5 text-xs font-semibold text-on-surface">{ds.item_count.toLocaleString("fr-FR")}</td>
                      <td className="py-3.5">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${
                          ds.status === "frozen" ? "bg-safe/10 text-safe" : "bg-warning/10 text-warning"
                        }`}>
                          {ds.status}
                        </span>
                      </td>
                      <td className="py-3.5 pr-2 text-right text-xs text-on-surface-variant/80 font-semibold">
                        {ds.published_at ? new Date(ds.published_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </MotionDiv>
    );
  }

  // General tenant dashboard
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
          <h1 className="app-h1">
            {t("dashboard.welcome")} {session.display_name.split(" ")[0]}
          </h1>
        </div>
      </div>

      {/* Domain Status Alert Banner for Disconnected or New Workspaces */}
      {!hasActiveDomain && totalScans > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/25 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-start gap-3.5">
            <div className="p-2 bg-amber-500/15 rounded-lg shrink-0 mt-0.5">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-on-surface">
                {i18n.language === "fr" ? "Surveillance en temps réel suspendue" : "Real-time monitoring suspended"}
              </h3>
              <p className="text-xs text-on-surface-variant mt-0.5 font-medium leading-relaxed">
                {i18n.language === "fr"
                  ? "Votre domaine a été déconnecté. Vos données historiques sont conservées ci-dessous, mais aucun nouvel email n'est actuellement intercepté."
                  : "Your domain is disconnected. Your historical scan logs are preserved below, but no incoming emails are currently intercepted."}
              </p>
            </div>
          </div>
          <Button
            onClick={() => onGoToSettings("domains")}
            size="sm"
            className="bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs shrink-0 cursor-pointer h-9 px-4 rounded-lg shadow-sm"
          >
            {i18n.language === "fr" ? "Reconnecter mon domaine" : "Reconnect Domain"}
          </Button>
        </div>
      )}

      {!hasActiveDomain && totalScans === 0 && (
        <div className="bg-primary/[0.04] border border-primary/15 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-start gap-3.5">
            <div className="p-2 bg-primary/10 rounded-lg shrink-0 mt-0.5">
              <ShieldCheck className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-on-surface">
                {i18n.language === "fr" ? "Bienvenue sur Sicurre ! Protégez votre domaine" : "Welcome to Sicurre! Protect your domain"}
              </h3>
              <p className="text-xs text-on-surface-variant mt-0.5 font-medium leading-relaxed">
                {i18n.language === "fr"
                  ? "Connectez votre domaine via Cloudflare pour activer l'interception automatique et sécuriser vos e-mails."
                  : "Connect your domain via Cloudflare to enable automatic interception and secure your email gateway."}
              </p>
            </div>
          </div>
          <Button
            onClick={() => onGoToSettings("domains")}
            size="sm"
            className="bg-primary hover:bg-primary/90 text-on-primary font-bold text-xs shrink-0 cursor-pointer h-9 px-4 rounded-lg shadow-sm"
          >
            {i18n.language === "fr" ? "Connecter mon domaine" : "Connect Domain"}
          </Button>
        </div>
      )}

      {/* Hero Row: KPI blocks + Security Score Grade */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-stretch">
            {/* Security Grade Hero (Reduced circle, overflow-visible for z-index tooltip popup) */}
            <div className="md:col-span-4 bg-white rounded-xl border border-border-subtle p-6 flex flex-col items-center justify-center text-center shadow-sm relative overflow-visible">
              <div className="absolute top-0 left-6 right-6 h-[3px] bg-primary rounded-b-md" />
              <div className="text-[12px] font-extrabold uppercase tracking-wider text-on-surface-variant mb-5 flex items-center justify-center gap-1.5 w-full">
                <Award className="w-4 h-4 text-primary" />
                <span>{t("dashboard.security_score")}</span>
                
                {/* Tooltip trigger with high z-index and border styling */}
                <div className="relative group">
                  <Info className="w-3.5 h-3.5 text-on-surface-variant/50 cursor-help hover:text-primary transition-colors" />
                  <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-44 bg-white border border-border-subtle text-on-surface text-[10px] p-2.5 rounded-xl shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-200 z-50 normal-case leading-normal font-sans text-center font-bold">
                    Overall status of your email gateway
                  </div>
                </div>
              </div>
              <div className="w-28 h-28 rounded-full bg-primary/[0.04] border border-primary/10 flex items-center justify-center font-display font-extrabold text-5xl text-primary shadow-inner">
                {grade === "L" ? (
                  <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin text-primary" />
                ) : (
                  grade
                )}
              </div>
            </div>

            {/* General KPI blocks */}
            <div className="md:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-5">
              <KPIBlock label={t("dashboard.kpi_raw")} value={kpisLoading ? "—" : totalScans.toLocaleString()} variant="primary" />
              <KPIBlock label={t("threats.badge_phishing")} value={kpisLoading ? "—" : phishingCount.toLocaleString()} variant="phishing" />
              <KPIBlock label={t("threats.badge_spam")} value={kpisLoading ? "—" : spamCount.toLocaleString()} variant="spam" />
              <KPIBlock label={t("threats.badge_legitimate")} value={kpisLoading ? "—" : legitimateCount.toLocaleString()} variant="legitimate" />
            </div>
          </div>

          {/* Verdict Distribution & Trend Analysis chart */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Verdict Distribution */}
            <div className="lg:col-span-5 bg-white rounded-xl border border-border-subtle p-6 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 pb-4 border-b border-border-subtle mb-4">
                  <Cpu className="w-5 h-5 text-primary" />
                  <div>
                    <h3 className="font-display font-semibold text-[17px] text-on-surface">
                      {t("dashboard.verdict_distribution")}
                    </h3>
                    <p className="text-[11px] text-on-surface-variant font-medium">
                      {i18n.language === "fr" ? "Répartition des emails par classification IA" : "Distribution of emails by AI safety classification"}
                    </p>
                  </div>
                </div>

                {/* Vertical gaps spacing expanded to distribute elements more evenly in space */}
                <div className="space-y-7 pt-4 pb-2">
                  <DistributionRow label={t("threats.badge_legitimate")} count={legitimateCount} total={Math.max(totalScans, 1)} colorClass="bg-safe" />
                  <DistributionRow label={t("threats.badge_spam")} count={spamCount} total={Math.max(totalScans, 1)} colorClass="bg-secondary" />
                  <DistributionRow label={t("threats.badge_phishing")} count={phishingCount} total={Math.max(totalScans, 1)} colorClass="bg-error" />
                </div>
              </div>
            </div>

            {/* Trend Analysis chart trend (Height Increased, Title renamed, light-adapted tooltip breakdown only) */}
            <div className="lg:col-span-7 bg-white rounded-xl border border-border-subtle p-6 shadow-sm flex flex-col justify-between relative min-h-[350px]">
              <div>
                <div className="flex items-center justify-between pb-4 border-b border-border-subtle mb-4">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-primary" />
                    <div>
                      <h3 className="font-display font-semibold text-[17px] text-on-surface">
                        {i18n.language === "fr" ? "Analyse des Tendances" : "Trend Analysis"}
                      </h3>
                      <p className="text-[11px] text-on-surface-variant font-medium">
                        {t("dashboard.scans_over_time")}
                      </p>
                    </div>
                  </div>

                  {/* Range Switcher */}
                  <div className="flex gap-1 bg-surface-low p-1 rounded-lg">
                    {(["7d", "30d", "12m"] as const).map((r) => (
                      <button
                        key={r}
                        onClick={() => {
                          setDateRange(r);
                          setHoveredBarIndex(null);
                        }}
                        className={`px-2.5 py-1 text-[10px] font-bold rounded transition-all cursor-pointer ${
                          dateRange === r
                            ? "bg-white text-primary shadow-sm"
                            : "text-on-surface-variant hover:text-on-surface"
                        }`}
                      >
                        {r === "7d"
                          ? (i18n.language === "fr" ? "7 Jours" : "7 Days")
                          : r === "30d"
                          ? (i18n.language === "fr" ? "30 Jours" : "30 Days")
                          : (i18n.language === "fr" ? "12 Mois" : "12 Months")}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Stacked interactive bars chart wrapped in overflow container (Height increased to h-56) */}
                <div className="w-full overflow-x-auto select-none scrollbar-none pb-1">
                  <div 
                    className={`h-56 pt-2 flex items-end justify-between gap-2.5 w-full font-sans text-[10px] font-bold text-on-surface-variant select-none ${
                      dateRange !== "7d" ? "min-w-[650px]" : ""
                    }`}
                  >
                    {trendData.labels.map((label, idx) => {
                      const safe = trendData.safeCounts[idx];
                      const phish = trendData.phishingCounts[idx];
                      const total = safe + phish;

                      // compute bar heights relative to max
                      const totalPct = maxTrendVal > 0 ? (total / maxTrendVal) * 100 : 0;
                      const safePct = total > 0 ? (safe / total) * 100 : 0;
                      const phishPct = total > 0 ? (phish / total) * 100 : 0;

                      return (
                        <div
                          key={idx}
                          className="flex-1 flex flex-col items-center gap-1 h-full justify-end group cursor-pointer relative"
                          onMouseEnter={() => setHoveredBarIndex(idx)}
                          onMouseLeave={() => setHoveredBarIndex(null)}
                        >
                          {/* Daily total value displayed above the bar */}
                          <span className="font-extrabold text-[12px] text-primary/80 mb-0.5 group-hover:text-primary transition-colors">
                            {total}
                          </span>

                          {/* Removed standard HTML browser titles */}
                          <div
                            className="w-full flex flex-col justify-end rounded-t-md overflow-hidden bg-surface-low border border-border-subtle/50 transition-all duration-300 group-hover:scale-y-105"
                            style={{ height: `${Math.max(6, totalPct * 0.78)}%` }}
                          >
                            {/* Phishing stack (Top) */}
                            {phish > 0 && (
                              <div
                                className="bg-error w-full transition-all"
                                style={{ height: `${phishPct}%` }}
                              />
                            )}
                            {/* Legitimate stack (Bottom) */}
                            {safe > 0 && (
                              <div
                                className="bg-safe w-full transition-all"
                                style={{ height: `${safePct}%` }}
                              />
                            )}
                          </div>
                          <span className="text-[10px] uppercase tracking-wider text-on-surface-variant truncate w-full text-center font-bold">
                            {label}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Absolute Floating Tooltip Card (Only displays breakdown counts, no date/totals) */}
                {hoveredBarIndex !== null && (
                  <div className="absolute top-16 right-6 z-35 p-3 bg-white border border-border-subtle text-on-surface rounded-xl text-[11px] shadow-xl flex flex-col gap-1.5 w-44 font-sans select-none pointer-events-none animate-in fade-in duration-100">
                    <div className="flex items-center justify-between gap-2 font-bold text-safe border-b border-border-subtle/40 pb-1.5 mb-0.5">
                      <span className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-safe" />
                        {t("threats.badge_legitimate")}
                      </span>
                      <span>{trendData.safeCounts[hoveredBarIndex]}</span>
                    </div>
                    <div className="flex items-center justify-between gap-2 font-bold text-error">
                      <span className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-error" />
                        {t("threats.badge_phishing")}
                      </span>
                      <span>{trendData.phishingCounts[hoveredBarIndex]}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Expanded full-width Recent Emails Scanned live feed */}
          <div className="grid grid-cols-1 gap-6">
            <div className="bg-white rounded-xl border border-border-subtle p-6 shadow-sm">
              <div className="flex items-center justify-between mb-5 pb-4 border-b border-border-subtle">
                <div className="flex items-center gap-2.5">
                  {/* Live pulsing green node blinker when active, static amber when suspended */}
                  {hasActiveDomain ? (
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-safe" />
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-safe" />
                    </span>
                  ) : (
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500" />
                    </span>
                  )}
                  {/* Text size increased to match Live Feed titles */}
                  <h3 className="font-display font-bold text-[19px] text-on-surface">
                    {i18n.language === "fr" ? "Emails Récemment Scannés" : "Recent Emails Scanned"}
                  </h3>
                </div>
                <div className={`inline-flex items-center gap-2 text-[12px] font-bold ${hasActiveDomain ? "text-primary" : "text-amber-600"}`}>
                  <Mail className="w-4 h-4" />
                  <span>
                    {hasActiveDomain
                      ? (i18n.language === "fr" ? "Flux Live" : "Recent Scans")
                      : (i18n.language === "fr" ? "Interception Suspendue" : "Interception Suspended")}
                  </span>
                </div>
              </div>
              {threatsLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-16 bg-surface-low rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : recentAlerts.length === 0 ? (
                <div className="py-8 text-center text-on-surface-variant text-sm font-medium">
                  {t("dashboard.no_threats")}
                </div>
              ) : (
                <div className="space-y-3">
                  {recentAlerts.map((alert) => (
                    <div
                      key={alert.id}
                      className="p-4 rounded-xl border border-border-subtle bg-surface-low/30 hover:bg-surface-low/60 transition-colors flex items-center justify-between gap-4"
                    >
                      {/* Left/Middle Content */}
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[11px] text-on-surface-variant font-medium">{alert.time}</span>
                          <span className="text-xs font-bold text-on-surface truncate max-w-[200px]" title={alert.sender}>
                            {alert.verdict !== "phishing" && alert.verdict !== "quarantine" ? "[Masqué par Sicurre]" : alert.sender}
                          </span>
                        </div>
                        <h4 className="font-bold text-sm text-on-surface truncate">
                          {alert.verdict !== "phishing" && alert.verdict !== "quarantine" ? "[Masqué par Sicurre]" : alert.subject}
                        </h4>
                        <p className="text-[12px] text-on-surface-variant font-medium truncate max-w-3xl">
                          {alert.verdict !== "phishing" && alert.verdict !== "quarantine" ? "[Masqué par Sicurre]" : alert.content}
                        </p>
                      </div>

                      {/* Right Classification Badge */}
                      <div className="shrink-0 pl-2">
                        <VerdictBadge verdict={alert.verdict} confidence={alert.confidence} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
    </MotionDiv>
  );
}

function DistributionRow({ label, count, total, colorClass }: { label: string; count: number; total: number; colorClass: string }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="space-y-1.5 animate-in fade-in duration-300">
      <div className="flex justify-between text-sm">
        <span className="font-semibold text-on-surface">{label}</span>
        <span className="text-on-surface font-mono text-[12px] font-bold">
          {count.toLocaleString()} · {pct} %
        </span>
      </div>
      <div className="w-full h-1.5 bg-surface-container rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${colorClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
