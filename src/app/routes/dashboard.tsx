import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  ShieldCheck,
  Zap,
  Mail,
  Users,
  ArrowUpRight,
  ArrowDownRight,
  AlertTriangle,
  TrendingUp,
  Clock,
} from "lucide-react";
import { useKPIStats, useThreatLogs } from "../lib/api";

const MotionDiv = motion.div as any;

export default function DashboardRoute() {
  const { t } = useTranslation();
  const { data: kpis, isLoading: kpisLoading } = useKPIStats();
  const { data: threats, isLoading: threatsLoading } = useThreatLogs();
  const [activeTab, setActiveTab] = useState<"realtime" | "historical">("realtime");

  const totalThreats = (kpis?.threats_phishing_count || 0) + (kpis?.threats_spam_count || 0);

  const kpiCards = [
    {
      label: "Scans Quotidiens",
      value: kpisLoading ? "—" : (kpis?.raw_records_count?.toLocaleString("fr-FR") || "0"),
      icon: Mail,
      iconColor: "text-primary",
      iconBg: "bg-primary/[0.06]",
      trend: { value: 12.5, positive: true, label: "depuis hier" },
    },
    {
      label: "Menaces Bloquées",
      value: kpisLoading ? "—" : totalThreats.toLocaleString("fr-FR"),
      icon: ShieldAlert,
      iconColor: "text-error",
      iconBg: "bg-error/[0.06]",
      trend: { value: 4.8, positive: false, label: "pic détecté il y a 14m" },
    },
    {
      label: "Utilisateurs Actifs",
      value: "248",
      icon: Users,
      iconColor: "text-primary",
      iconBg: "bg-primary/[0.06]",
      trend: { value: 8.2, positive: true, label: "sessions vérifiées" },
    },
    {
      label: "Temps de Réponse",
      value: "1,2",
      unit: "ms",
      icon: Zap,
      iconColor: "text-safe",
      iconBg: "bg-safe/[0.06]",
      trend: { value: 15.3, positive: true, label: "sous le seuil SLA" },
    },
  ];

  const recentAlerts = threats
    ? threats.slice(0, 4).map((t) => ({
        id: t.id,
        time: new Date(t.received_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " UTC",
        level: t.verdict === "phishing" ? 5 : t.verdict === "spam" ? 3 : 1,
        title: t.verdict === "phishing"
          ? "Tentative de Phishing Interceptée"
          : t.verdict === "spam"
          ? "Spam Publicitaire Filtré"
          : "Email Validé",
        desc: t.subject || "Aucun objet",
      }))
    : [];

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
            Console de Commandes
          </h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Vue d'ensemble en temps réel de votre sécurité e-mail
          </p>
        </div>
        <div className="flex p-0.5 bg-surface-low rounded-lg border border-border-subtle self-start sm:self-center">
          {(["realtime", "historical"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 text-[13px] font-semibold rounded-md transition-all cursor-pointer ${
                activeTab === tab
                  ? "bg-white text-primary shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
            >
              {tab === "realtime" ? "Temps Réel" : "Historique"}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {kpiCards.map((kpi, i) => {
          const Icon = kpi.icon;
          return (
            <MotionDiv
              key={i}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: i * 0.05 }}
              className="bg-white rounded-xl border border-border-subtle p-5 hover:shadow-md hover:shadow-on-surface/[0.03] transition-shadow"
            >
              <div className="flex items-start justify-between mb-4">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">
                  {kpi.label}
                </span>
                <div className={`p-2 rounded-lg ${kpi.iconBg}`}>
                  <Icon className={`w-4.5 h-4.5 ${kpi.iconColor} stroke-[1.5]`} />
                </div>
              </div>
              <div className="flex items-baseline gap-1">
                <span className="font-display font-bold text-[32px] text-on-surface tracking-tight leading-none">
                  {kpi.value}
                </span>
                {kpi.unit && (
                  <span className="text-sm text-on-surface-variant font-medium">{kpi.unit}</span>
                )}
              </div>
              <div className="flex items-center gap-1.5 mt-2.5">
                <span className={`inline-flex items-center text-[12px] font-semibold ${kpi.trend.positive ? "text-safe" : "text-error"}`}>
                  {kpi.trend.positive ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                  {kpi.trend.value} %
                </span>
                <span className="text-[11px] text-on-surface-variant/60">{kpi.trend.label}</span>
              </div>
            </MotionDiv>
          );
        })}
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column */}
        <div className="lg:col-span-4 space-y-6">
          {/* System Integrity Gauge */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em] mb-1">
              Intégrité Système
            </p>
            <div className="flex flex-col items-center py-6">
              <div className="relative w-36 h-36 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90">
                  <circle cx="72" cy="72" r="62" className="stroke-surface-container" strokeWidth="8" fill="transparent" />
                  <circle
                    cx="72" cy="72" r="62"
                    className="stroke-safe transition-all duration-1000 ease-out"
                    strokeWidth="8" fill="transparent"
                    strokeDasharray={389.6}
                    strokeDashoffset={389.6 - (389.6 * 99.8) / 100}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute flex flex-col items-center">
                  <span className="font-display font-bold text-[28px] text-on-surface leading-none">
                    99.8%
                  </span>
                  <span className="text-[9px] font-bold text-safe uppercase tracking-[0.15em] mt-1">
                    Optimal
                  </span>
                </div>
              </div>
              <p className="text-[12px] text-on-surface-variant/60 text-center mt-5 leading-relaxed max-w-[200px]">
                Toutes les sondes d'analyse (CamemBERTav2, DMARC, DNS RBL) sont opérationnelles.
              </p>
            </div>
          </div>

          {/* Verdict Distribution */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em] mb-5">
              Répartition des Verdicts
            </p>
            <div className="space-y-4">
              <DistributionRow
                label="Légitime"
                count={kpis?.threats_legitimate_count || 0}
                total={kpis?.raw_records_count || 1}
                colorClass="bg-safe"
              />
              <DistributionRow
                label="Spam"
                count={kpis?.threats_spam_count || 0}
                total={kpis?.raw_records_count || 1}
                colorClass="bg-secondary"
              />
              <DistributionRow
                label="Phishing"
                count={kpis?.threats_phishing_count || 0}
                total={kpis?.raw_records_count || 1}
                colorClass="bg-error"
              />
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="lg:col-span-8 space-y-6">
          {/* Recent Critical Alerts */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <div className="flex items-center justify-between mb-5 pb-4 border-b border-border-subtle">
              <h3 className="font-display font-semibold text-[17px] text-on-surface">
                Alertes Critiques Récentes
              </h3>
            </div>
            {threatsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-16 bg-surface-low rounded-xl animate-pulse" />
                ))}
              </div>
            ) : recentAlerts.length === 0 ? (
              <div className="py-8 text-center text-on-surface-variant/50 text-sm">
                Aucune alerte récente 🎉
              </div>
            ) : (
              <div className="space-y-3">
                {recentAlerts.map((alert) => (
                  <div
                    key={alert.id}
                    className={`p-4 rounded-xl border transition-colors ${
                      alert.level >= 5
                        ? "bg-error/[0.03] border-error/10"
                        : alert.level >= 3
                        ? "bg-secondary/[0.03] border-secondary/10"
                        : "bg-surface-low border-border-subtle"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[11px] text-on-surface-variant/60">{alert.time}</span>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ${
                            alert.level >= 5
                              ? "bg-error/10 text-error"
                              : alert.level >= 3
                              ? "bg-secondary/10 text-secondary"
                              : "bg-safe/10 text-safe"
                          }`}>
                            Niveau {alert.level}
                          </span>
                        </div>
                        <p className="font-bold text-sm text-on-surface">{alert.title}</p>
                        <p className="text-[12px] text-on-surface-variant/70 truncate">{alert.desc}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active Breach Analysis */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <div className="flex items-center justify-between mb-5 pb-4 border-b border-border-subtle">
              <h3 className="font-display font-semibold text-[17px] text-on-surface">
                Analyse Vectorielle des Risques
              </h3>
              <button className="text-[11px] font-bold text-primary uppercase tracking-wider hover:text-navy-dark transition-colors cursor-pointer">
                Exporter
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border-subtle">
                    <th className="pb-3 pr-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Type de Menace</th>
                    <th className="pb-3 px-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Vecteur</th>
                    <th className="pb-3 px-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Mitigation</th>
                    <th className="pb-3 px-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Cible</th>
                    <th className="pb-3 pl-4 text-right text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Probabilité</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle text-sm text-on-surface">
                  {[
                    { type: "Spear Phishing", vector: "Direct / Link-injection", status: "Bloqué", statusColor: "error", target: "/inbox/primary", prob: "99 %" },
                    { type: "Usurpation d'identité", vector: "Lookalike-domain", status: "Quarantaine", statusColor: "secondary", target: "/api/v2/users", prob: "97 %" },
                    { type: "Spam Publicitaire", vector: "Bulk-sender", status: "Filtré", statusColor: "safe", target: "/inbox/promotions", prob: "85 %" },
                  ].map((row, i) => (
                    <tr key={i} className="hover:bg-surface-low/30 transition-colors">
                      <td className="py-3.5 pr-4 font-bold">{row.type}</td>
                      <td className="py-3.5 px-4 text-on-surface-variant font-mono text-[12px]">{row.vector}</td>
                      <td className="py-3.5 px-4">
                        <span className={`inline-flex text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider bg-${row.statusColor}/10 text-${row.statusColor}`}>
                          {row.status}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-[12px] text-on-surface-variant">{row.target}</td>
                      <td className="py-3.5 pl-4 text-right font-mono font-bold">{row.prob}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </MotionDiv>
  );
}

function DistributionRow({ label, count, total, colorClass }: { label: string; count: number; total: number; colorClass: string }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="font-semibold text-on-surface">{label}</span>
        <span className="text-on-surface-variant font-mono text-[12px] font-bold">
          {count.toLocaleString("fr-FR")} · {pct} %
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
