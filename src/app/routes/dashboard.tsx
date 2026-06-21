import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  ShieldCheck,
  Mail,
  Settings,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { AuthSession, useKPIStats, useThreatLogs } from "../lib/api";

const MotionDiv = motion.div as any;

interface DashboardRouteProps {
  session: AuthSession;
  onGoToSettings: () => void;
}

function KPIBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-border-subtle p-5">
      <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em] mb-2">
        {label}
      </p>
      <p className="font-display font-bold text-[32px] text-on-surface tracking-tight leading-none">
        {value}
      </p>
    </div>
  );
}

export default function DashboardRoute({ session, onGoToSettings }: DashboardRouteProps) {
  const { t } = useTranslation();
  const { data: kpis, isLoading: kpisLoading } = useKPIStats();
  const { data: threats, isLoading: threatsLoading } = useThreatLogs();
  const totalScans = kpis?.raw_records_count ?? 0;
  const phishingCount = kpis?.threats_phishing_count ?? 0;
  const spamCount = kpis?.threats_spam_count ?? 0;
  const legitimateCount = kpis?.threats_legitimate_count ?? 0;

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
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
            Console de Commandes
          </h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Vue d'ensemble en temps réel de votre sécurité e-mail
          </p>
        </div>
        {session.is_platform_admin && (
          <div className="rounded-lg border border-border-subtle bg-white px-4 py-3 text-right">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant">
              Dataset Items
            </div>
            <div className="text-lg font-bold text-on-surface">
              {(kpis?.dataset_items_count ?? 0).toLocaleString("fr-FR")}
            </div>
          </div>
        )}
      </div>

      {session.onboarding_required ? (
        <div className="bg-white rounded-xl border border-border-subtle p-8 space-y-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="w-6 h-6 text-primary shrink-0 mt-0.5" />
            <div>
              <h2 className="font-display font-semibold text-xl text-on-surface">
                Connectez d'abord votre domaine
              </h2>
              <p className="text-sm text-on-surface-variant mt-1 max-w-2xl">
                Votre compte existe, mais aucun domaine n'est encore protégé. Commencez par configurer Cloudflare dans les paramètres pour activer l'interception et les premiers scans.
              </p>
            </div>
          </div>
          <Button onClick={onGoToSettings} className="gap-2">
            <Settings className="w-4 h-4" />
            Ouvrir l'intégration Cloudflare
          </Button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <KPIBlock label="Emails scannés" value={kpisLoading ? "—" : totalScans.toLocaleString("fr-FR")} />
            <KPIBlock label="Phishing bloqué" value={kpisLoading ? "—" : phishingCount.toLocaleString("fr-FR")} />
            <KPIBlock label="Spam signalé" value={kpisLoading ? "—" : spamCount.toLocaleString("fr-FR")} />
            <KPIBlock label="Emails légitimes" value={kpisLoading ? "—" : legitimateCount.toLocaleString("fr-FR")} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-4 bg-white rounded-xl border border-border-subtle p-6">
              <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em] mb-5">
                Répartition des verdicts
              </p>
              <div className="space-y-4">
                <DistributionRow label="Légitime" count={legitimateCount} total={Math.max(totalScans, 1)} colorClass="bg-safe" />
                <DistributionRow label="Spam" count={spamCount} total={Math.max(totalScans, 1)} colorClass="bg-secondary" />
                <DistributionRow label="Phishing" count={phishingCount} total={Math.max(totalScans, 1)} colorClass="bg-error" />
              </div>
            </div>

            <div className="lg:col-span-8 bg-white rounded-xl border border-border-subtle p-6">
              <div className="flex items-center justify-between mb-5 pb-4 border-b border-border-subtle">
                <h3 className="font-display font-semibold text-[17px] text-on-surface">
                  Alertes récentes
                </h3>
                <div className="inline-flex items-center gap-2 text-[11px] text-on-surface-variant">
                  <Mail className="w-3.5 h-3.5" />
                  Flux temps réel
                </div>
              </div>
              {threatsLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-16 bg-surface-low rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : recentAlerts.length === 0 ? (
                <div className="py-8 text-center text-on-surface-variant/70 text-sm">
                  Aucun événement pour le moment. Les alertes apparaîtront ici dès que Sicurre commencera à scanner vos e-mails.
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
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
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
