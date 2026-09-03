import { motion, useReducedMotion } from "framer-motion";
import { useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Cloud,
  Flag,
  Inbox,
  LifeBuoy,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Users,
} from "lucide-react";
import {
  useAdminOverview,
  useAdminDomains,
  useAdminRuntimeHealth,
  type AdminRuntimeHealth,
} from "../lib/api";
import { OperationalExercisePanel } from "../components/admin/operational-exercise-panel";

const MotionDiv = motion.div as any;

function formatDate(value: string | null | undefined) {
  if (!value) return "Jamais";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function AdminMetric({
  icon,
  label,
  value,
  help,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  help: string;
}) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-primary-fixed text-primary dark:bg-primary-container dark:text-on-primary-container">
        {icon}
      </div>
      <div className="font-mono text-3xl font-semibold text-on-surface">{value.toLocaleString("fr-FR")}</div>
      <div className="mt-2 text-sm font-bold text-on-surface">{label}</div>
      <p className="mt-1 text-sm leading-6 text-on-surface-variant">{help}</p>
    </div>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border-subtle bg-surface-low p-6 text-sm leading-6 text-on-surface-variant dark:bg-surface">
      <p className="font-bold text-on-surface">{title}</p>
      <p className="mt-1">{body}</p>
    </div>
  );
}

function statusLabel(status: AdminRuntimeHealth["status"]) {
  if (status === "ok") return "Opérationnel";
  if (status === "degraded") return "Dégradé";
  if (status === "down") return "Incident";
  return "Inconnu";
}

function statusClass(status: AdminRuntimeHealth["status"]) {
  if (status === "ok") return "border-safe/25 bg-safe-bg text-safe dark:bg-safe-bg";
  if (status === "degraded") return "border-warning/25 bg-warning-bg text-warning dark:bg-warning-bg";
  if (status === "down") return "border-error/25 bg-error/10 text-error";
  return "border-border-subtle bg-surface-low text-on-surface-variant";
}

function RuntimeHealthPanel({
  health,
  isLoading,
}: {
  health?: AdminRuntimeHealth;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const componentLabel = (component: string) =>
    t(`admin.health.components.${component}`, { defaultValue: component.replaceAll("_", " ") });
  return (
    <section className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-fixed text-primary dark:bg-primary-container dark:text-on-primary-container">
            <Server className="h-5 w-5" />
          </div>
          <div>
            <h2 className="app-h2">Santé runtime</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-variant">
              Préflight admin des dépendances critiques: API publique de scan, classifier déployé, Worker Cloudflare et règle de routage.
            </p>
          </div>
        </div>
        <span className={`w-fit rounded-full border px-3 py-1 text-sm font-bold ${statusClass(health?.status || "unknown")}`}>
          {isLoading ? "Vérification" : statusLabel(health?.status || "unknown")}
        </span>
      </div>

      {isLoading && !health ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-28 animate-pulse rounded-lg bg-surface-low dark:bg-surface" />
          ))}
        </div>
      ) : health ? (
        <>
          <div className="mb-4 grid gap-3 text-sm md:grid-cols-2">
            <div className="rounded-lg bg-surface-low p-3 dark:bg-surface">
              <p className="font-bold text-on-surface">Gateway Worker attendu</p>
              <p className="mt-1 break-all text-on-surface-variant">{health.expected_worker_scan_url || "Non configuré"}</p>
            </div>
            <div className="rounded-lg bg-surface-low p-3 dark:bg-surface">
              <p className="font-bold text-on-surface">Classifier app runtime</p>
              <p className="mt-1 break-all text-on-surface-variant">{health.inference_api_url || "Non configuré"}</p>
            </div>
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            {health.components.map((component) => (
              <div key={component.component} className={`rounded-lg border p-4 ${statusClass(component.status)}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-bold text-on-surface">{componentLabel(component.component)}</p>
                  <span className="rounded-full bg-white/70 px-2.5 py-0.5 text-xs font-bold text-current dark:bg-black/15">
                    {statusLabel(component.status)}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-current">
                  {t(`admin.health.messages.${component.status}`)}
                </p>
                {component.detail && (
                  <details className="mt-2 text-xs text-current/80">
                    <summary className="cursor-pointer font-semibold">{t("admin.health.technical_detail")}</summary>
                    <p className="mt-2 break-all">{component.detail}</p>
                  </details>
                )}
                {component.latency_ms !== null && (
                  <p className="mt-2 text-xs font-bold text-current/75">{component.latency_ms} ms</p>
                )}
              </div>
            ))}
          </div>
        </>
      ) : (
        <EmptyPanel title="Préflight indisponible" body="La santé runtime sera affichée ici dès que l’endpoint admin répond." />
      )}
    </section>
  );
}


export default function LogsRoute() {
  const reduceMotion = useReducedMotion();
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch, isFetching } = useAdminOverview();
  const runtimeHealth = useAdminRuntimeHealth();
  const [activeView, setActiveView] = useState<"overview" | "operations" | "integrations" | "reviews">("overview");
  const [domainPageNumber, setDomainPageNumber] = useState(1);
  const [domainSearch, setDomainSearch] = useState("");
  const deferredDomainSearch = useDeferredValue(domainSearch);
  const domainPage = useAdminDomains(domainPageNumber, deferredDomainSearch, activeView === "integrations");
  const translatedValue = (value: string | null | undefined) =>
    value ? t(`admin.values.${value}`, { defaultValue: value.replaceAll("_", " ") }) : t("admin.unknown");

  return (
    <MotionDiv
      initial={reduceMotion ? false : { opacity: 0, transform: "translateY(12px)" }}
      animate={{ opacity: 1, transform: "translateY(0)" }}
      exit={reduceMotion ? undefined : { opacity: 0, transform: "translateY(-8px)" }}
      transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
      className="space-y-6"
    >
      <div className="flex flex-col gap-4 border-b border-border-subtle pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="app-h1">{t("admin.title", { defaultValue: "Console d’administration" })}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant">
            {t("admin.subtitle", { defaultValue: "Vue synthétique des espaces clients, opérations, intégrations et signalements." })}
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-border-subtle bg-surface-lowest px-4 text-sm font-bold text-on-surface transition-[background-color,border-color,transform] duration-200 hover:border-primary/45 hover:bg-primary-fixed active:scale-[0.98] dark:bg-surface-low"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          {t("admin.refresh", { defaultValue: "Actualiser" })}
        </button>
      </div>

      <nav className="flex gap-1 overflow-x-auto border-b border-border-subtle" aria-label={t("admin.views_label", { defaultValue: "Vues de la console" })}>
        {(["overview", "operations", "integrations", "reviews"] as const).map((view) => (
          <button
            key={view}
            type="button"
            onClick={() => setActiveView(view)}
            className={`shrink-0 border-b-2 px-4 py-3 text-sm font-bold transition-colors ${activeView === view ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}
          >
            {t(`admin.views.${view}`, {
              defaultValue: { overview: "Vue d’ensemble", operations: "Opérations", integrations: "Intégrations", reviews: "À examiner" }[view],
            })}
          </button>
        ))}
      </nav>

      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-40 animate-pulse rounded-lg bg-surface-low dark:bg-surface-low" />
          ))}
        </div>
      )}

      {isError && !data && (
        <div role="alert" className="rounded-lg border border-danger/25 bg-danger-bg p-5 text-sm leading-6 text-danger">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="font-bold">{t("admin.load_error")}</p>
              <p>{t("admin.load_error_help")}</p>
            </div>
          </div>
        </div>
      )}

      {data && (
        <>
          {isError && (
            <p role="status" className="border-l-4 border-warning bg-warning-bg px-4 py-3 text-sm text-on-surface">
              {t("admin.refresh_error")}
            </p>
          )}
          {activeView === "operations" && (
            <>
              <OperationalExercisePanel />
              <details className="min-w-0 border-b border-border-subtle pb-5">
                <summary className="cursor-pointer py-3 font-semibold text-on-surface">{t("operational_test.dependencies")}</summary>
                <RuntimeHealthPanel health={runtimeHealth.data} isLoading={runtimeHealth.isLoading} />
              </details>
            </>
          )}

          <div className={`${activeView === "overview" ? "grid" : "hidden"} gap-4 md:grid-cols-2 xl:grid-cols-5`}>
            <AdminMetric icon={<Users className="h-5 w-5" />} label="Espaces clients" value={data.summary.workspaces_count} help="Espaces client connus par le runtime." />
            <AdminMetric icon={<Activity className="h-5 w-5" />} label="Événements" value={data.summary.threat_events_count} help="Verdicts enregistrés sans messages supprimés." />
            <AdminMetric icon={<Flag className="h-5 w-5" />} label="Feedbacks" value={data.summary.feedback_count} help={`${data.summary.false_negative_count} faux négatifs, dont ${data.summary.reported_email_count} transférés.`} />
            <AdminMetric icon={<Cloud className="h-5 w-5" />} label="Domaines actifs" value={data.summary.cloudflare_active_count} help={`${data.summary.cloudflare_integrations_count} intégrations Cloudflare au total.`} />
            <AdminMetric icon={<LifeBuoy className="h-5 w-5" />} label="Support ouvert" value={data.summary.support_open_count} help="Demandes client à prendre en charge." />
          </div>

          <div className={`${activeView === "overview" || activeView === "integrations" ? "grid" : "hidden"} gap-5`}>
            <section className={`${activeView === "overview" ? "block" : "hidden"} rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low`}>
              <div className="mb-5 flex items-center gap-3">
                <BarChart3 className="h-5 w-5 text-primary" />
                <h2 className="app-h2">Répartition des verdicts</h2>
              </div>
              {data.verdicts.length === 0 ? (
                <EmptyPanel title="Aucun verdict enregistré" body="Les premiers emails routés par Cloudflare alimenteront cette section." />
              ) : (
                <div className="space-y-3">
                  {data.verdicts.map((row) => (
                    <div key={row.verdict} className="space-y-2 rounded-lg bg-surface-low px-4 py-3 dark:bg-surface">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold capitalize text-on-surface">{translatedValue(row.verdict)}</span>
                        <span className="font-mono text-sm font-semibold text-on-surface-variant">{row.count}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-surface-high" aria-hidden="true">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(3, (row.count / Math.max(...data.verdicts.map((item) => item.count), 1)) * 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className={`${activeView === "integrations" ? "block" : "hidden"} rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low`}>
              <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <Cloud className="h-5 w-5 text-primary" />
                  <div>
                    <h2 className="app-h2">Domaines Cloudflare</h2>
                    <p className="mt-1 text-sm text-on-surface-variant">{domainPage.data?.total ?? data.summary.cloudflare_integrations_count} intégration(s)</p>
                  </div>
                </div>
                <label className="relative block sm:w-72">
                  <span className="sr-only">Rechercher un domaine</span>
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
                  <input
                    value={domainSearch}
                    onChange={(event) => { setDomainSearch(event.target.value); setDomainPageNumber(1); }}
                    placeholder="Domaine ou propriétaire"
                    className="h-10 w-full rounded-lg border border-border-subtle bg-surface-lowest pl-9 pr-3 text-sm text-on-surface outline-none focus:border-primary dark:bg-surface"
                  />
                </label>
              </div>
              {(domainPage.data?.items ?? []).length === 0 ? (
                <EmptyPanel title="Aucun domaine connecté" body="Les domaines ajoutés depuis Domain Shield apparaîtront ici avec leur statut." />
              ) : (
                <div className="overflow-hidden rounded-lg border border-border-subtle">
                  {domainPage.data?.items.map((domain) => (
                    <div key={`${domain.zone_name}-${domain.user_email}`} className="grid gap-2 border-b border-border-subtle bg-surface-lowest p-4 last:border-b-0 dark:bg-surface md:grid-cols-[1fr_auto_auto] md:items-center">
                      <div>
                        <p className="text-sm font-bold text-on-surface">{domain.zone_name || "Domaine sans nom"}</p>
                        <p className="text-xs text-on-surface-variant">{domain.user_email || "Utilisateur inconnu"}</p>
                      </div>
                      <span className="w-fit rounded-md bg-primary-fixed px-2.5 py-1 text-xs font-bold text-on-primary-container dark:bg-primary-container">
                        {translatedValue(domain.status)}
                      </span>
                      <span className="text-xs font-semibold text-on-surface-variant">{formatDate(domain.updated_at)}</span>
                    </div>
                  ))}
                </div>
              )}
              {(domainPage.data?.pages ?? 1) > 1 && (
                <div className="mt-4 flex items-center justify-between gap-3 text-sm">
                  <span className="font-semibold text-on-surface-variant">Page {domainPage.data?.page} / {domainPage.data?.pages}</span>
                  <div className="flex gap-2">
                    <button type="button" disabled={domainPageNumber === 1} onClick={() => setDomainPageNumber((page) => Math.max(1, page - 1))} className="h-9 rounded-lg border border-border-subtle px-3 font-bold disabled:opacity-40">Précédent</button>
                    <button type="button" disabled={domainPageNumber === domainPage.data?.pages} onClick={() => setDomainPageNumber((page) => page + 1)} className="h-9 rounded-lg border border-border-subtle px-3 font-bold disabled:opacity-40">Suivant</button>
                  </div>
                </div>
              )}
            </section>
          </div>

          <div className={`${activeView === "reviews" ? "grid" : "hidden"} gap-5 xl:grid-cols-2`}>
            <section className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
              <div className="mb-5 flex items-center gap-3">
                <Flag className="h-5 w-5 text-warning" />
                <h2 className="app-h2">Feedbacks récents</h2>
              </div>
              {data.recent_feedback.length === 0 ? (
                <EmptyPanel title="Aucun feedback" body="Les false positives et false negatives reportés par les utilisateurs s’afficheront ici." />
              ) : (
                <div className="space-y-3">
                  {data.recent_feedback.map((item) => (
                    <div key={item.id} className="rounded-lg border border-border-subtle bg-surface-low p-4 dark:bg-surface">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-bold capitalize text-on-surface">{translatedValue(item.feedback_type)}</p>
                        <span className="text-xs font-semibold text-on-surface-variant">{formatDate(item.created_at)}</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                        {translatedValue(item.original_verdict)} → {translatedValue(item.corrected_verdict)}
                      </p>
                      <p className="mt-1 text-xs text-on-surface-variant">{item.reporter_email || item.workspace_id}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
              <div className="mb-5 flex items-center gap-3">
                <Inbox className="h-5 w-5 text-primary" />
                <h2 className="app-h2">Quarantaine récente</h2>
              </div>
              {data.recent_quarantine.length === 0 ? (
                <EmptyPanel title="Aucune quarantaine" body="Les emails retenus par le runtime apparaîtront ici sans exposer leur contenu brut." />
              ) : (
                <div className="space-y-3">
                  {data.recent_quarantine.map((item) => (
                    <div key={item.id} className="rounded-lg border border-border-subtle bg-surface-low p-4 dark:bg-surface">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-bold capitalize text-on-surface">{translatedValue(item.safety_verdict)}</p>
                        <span className="font-mono text-xs font-semibold text-on-surface-variant">{Math.round(item.composite_score * 100)} %</span>
                      </div>
                      <p className="mt-2 text-sm text-on-surface-variant">{t("admin.status")}: {translatedValue(item.status)}</p>
                      <p className="mt-1 text-xs text-on-surface-variant">Expire le {formatDate(item.expires_at)}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className={`${activeView === "reviews" ? "block" : "hidden"} rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low`}>
            <div className="mb-5 flex items-center gap-3">
              <LifeBuoy className="h-5 w-5 text-primary" />
              <h2 className="app-h2">Demandes de support récentes</h2>
            </div>
            {data.recent_support.length === 0 ? (
              <EmptyPanel title="Aucune demande" body="Les tickets envoyés depuis l’application apparaîtront ici." />
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {data.recent_support.map((item) => (
                  <div key={item.id} className="rounded-lg border border-border-subtle bg-surface-low p-4 dark:bg-surface">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-bold capitalize text-on-surface">{translatedValue(item.category)}</p>
                      <span className="rounded-md bg-primary-fixed px-2 py-1 text-xs font-bold capitalize text-on-primary-container">{translatedValue(item.status)}</span>
                    </div>
                    <p className="mt-2 break-all text-sm text-on-surface-variant">{item.requester_email}</p>
                    <p className="mt-1 text-xs text-on-surface-variant">{formatDate(item.created_at)}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </MotionDiv>
  );
}
