import React from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { ShieldAlert, MailCheck, Database, ShieldCheck, Clock } from "lucide-react";
import { useKPIStats, useThreatLogs } from "../lib/api";
import { VerdictBadge } from "../components/threats/verdict-badge";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/card";

const MotionDiv = motion.div as any;

export default function DashboardRoute() {
  const { t } = useTranslation();
  const { data: kpis, isLoading: kpisLoading } = useKPIStats();
  const { data: threats, isLoading: threatsLoading } = useThreatLogs();

  const totalThreats = (kpis?.threats_phishing_count || 0) + (kpis?.threats_spam_count || 0) + (kpis?.threats_legitimate_count || 0);

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-8"
    >
      {/* Welcome header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-3xl font-display font-bold text-slate-900">
            {t("dashboard.welcome")}, {localStorage.getItem("sicurre_user_name") || "Utilisateur"} 👋
          </h2>
          <p className="text-sm text-slate-500 mt-1">{t("dashboard.subtitle")}</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">
          <Clock className="w-3.5 h-3.5" />
          <span>{new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}</span>
        </div>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <KPICard
          icon={<Database className="w-5 h-5 text-primary" />}
          iconBg="bg-primary/10 border-primary/20"
          title={t("dashboard.kpi_raw")}
          value={kpisLoading ? "—" : (kpis?.raw_records_count?.toLocaleString() || "0")}
          description="Données brutes ingérées"
          accent
        />
        <KPICard
          icon={<ShieldAlert className="w-5 h-5 text-red-600" />}
          iconBg="bg-red-50 border-red-200"
          title="Menaces détectées"
          value={kpisLoading ? "—" : ((kpis?.threats_phishing_count || 0) + (kpis?.threats_spam_count || 0)).toLocaleString()}
          description="Phishing + spam neutralisés"
          danger
        />
        <KPICard
          icon={<MailCheck className="w-5 h-5 text-green-600" />}
          iconBg="bg-green-50 border-green-200"
          title="Emails légitimes"
          value={kpisLoading ? "—" : (kpis?.threats_legitimate_count?.toLocaleString() || "0")}
          description="Correctement délivrés"
          safe
        />
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Recent Activity */}
        <Card className="col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{t("dashboard.recent_activity")}</CardTitle>
              {threats && threats.length > 0 && (
                <span className="text-xs text-slate-400 font-mono">{threats.length} entrées</span>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {threatsLoading ? (
              <div className="space-y-3 py-2">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-12 bg-slate-100 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : !threats || threats.length === 0 ? (
              <div className="py-10 text-center">
                <ShieldCheck className="w-10 h-10 text-slate-200 mx-auto mb-3" />
                <p className="text-sm text-slate-400">{t("dashboard.no_threats")}</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {threats.slice(0, 6).map((threat) => (
                  <div key={threat.id} className="py-3.5 flex items-center justify-between gap-4 group">
                    <div className="truncate flex-1">
                      <p className="text-sm font-medium text-slate-900 truncate group-hover:text-primary transition-colors">
                        {threat.subject}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5 font-mono">
                        {new Date(threat.received_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                    <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Verdict Distribution Panel */}
        <Card>
          <CardHeader>
            <CardTitle>{t("dashboard.verdict_distribution")}</CardTitle>
          </CardHeader>
          <CardContent>
            {kpisLoading ? (
              <div className="space-y-4 py-2">
                {[1, 2, 3].map(i => <div key={i} className="h-8 bg-slate-100 rounded animate-pulse" />)}
              </div>
            ) : (
              <div className="space-y-4 pt-2">
                <DistributionBar
                  label={t("threats.badge_phishing")}
                  count={kpis?.threats_phishing_count || 0}
                  total={totalThreats || 1}
                  colorClass="bg-red-500"
                />
                <DistributionBar
                  label={t("threats.badge_spam")}
                  count={kpis?.threats_spam_count || 0}
                  total={totalThreats || 1}
                  colorClass="bg-amber-400"
                />
                <DistributionBar
                  label={t("threats.badge_legitimate")}
                  count={kpis?.threats_legitimate_count || 0}
                  total={totalThreats || 1}
                  colorClass="bg-green-500"
                />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </MotionDiv>
  );
}

interface KPICardProps {
  icon: React.ReactNode;
  iconBg: string;
  title: string;
  value: string;
  description: string;
  accent?: boolean;
  danger?: boolean;
  safe?: boolean;
}

function KPICard({ icon, iconBg, title, value, description, accent, danger, safe }: KPICardProps) {
  const borderClass = accent
    ? "border-primary/20 bg-gradient-to-br from-primary-light to-white"
    : danger
    ? "border-red-100 bg-gradient-to-br from-red-50 to-white"
    : safe
    ? "border-green-100 bg-gradient-to-br from-green-50 to-white"
    : "border-slate-200 bg-white";

  const valueClass = accent
    ? "text-primary"
    : danger
    ? "text-red-700"
    : safe
    ? "text-green-700"
    : "text-slate-900";

  return (
    <div className={`p-5 rounded-xl border shadow-sm ${borderClass}`}>
      <div className="flex items-start justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center border ${iconBg}`}>
          {icon}
        </div>
      </div>
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{title}</p>
      <p className={`text-3xl font-display font-bold mt-1 tabular-nums ${valueClass}`}>{value}</p>
      <p className="text-xs text-slate-400 mt-1">{description}</p>
    </div>
  );
}

function DistributionBar({ label, count, total, colorClass }: { label: string; count: number; total: number; colorClass: string }) {
  const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs font-medium">
        <span className="text-slate-600">{label}</span>
        <span className="text-slate-500 font-mono tabular-nums">{count.toLocaleString()} · {percentage}%</span>
      </div>
      <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${colorClass}`} style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

