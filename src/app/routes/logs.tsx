import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Cloud,
  Flag,
  FlaskConical,
  Inbox,
  LifeBuoy,
  RefreshCw,
  Server,
  ShieldCheck,
  Square,
  Users,
} from "lucide-react";
import {
  useAdminOverview,
  useAdminRuntimeHealth,
  useOperationalExercises,
  useRecoverOperationalExercise,
  useStartOperationalExercise,
  type AdminRuntimeHealth,
  type OperationalExerciseType,
} from "../lib/api";

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
                  <p className="font-bold text-on-surface">{component.component.replaceAll("_", " ")}</p>
                  <span className="rounded-full bg-white/70 px-2.5 py-0.5 text-xs font-bold text-current dark:bg-black/15">
                    {statusLabel(component.status)}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-current">{component.message}</p>
                {component.detail && (
                  <p className="mt-2 break-all text-xs font-semibold text-current/80">{component.detail}</p>
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

const exerciseLabels: Record<OperationalExerciseType, string> = {
  api_unavailable: "Indisponibilité API",
  high_latency: "Latence élevée",
  elevated_5xx: "Taux 5xx élevé",
};

function OperationalExercisePanel() {
  const exercises = useOperationalExercises();
  const startExercise = useStartOperationalExercise();
  const recoverExercise = useRecoverOperationalExercise();
  const [pendingType, setPendingType] = useState<OperationalExerciseType | null>(null);
  const active = exercises.data?.active;

  return (
    <section className="border-y border-border-subtle py-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="flex items-center gap-3">
            <FlaskConical className="h-5 w-5 text-primary" />
            <h2 className="app-h2">Tests opérationnels contrôlés</h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-on-surface-variant">
            Émet un signal synthétique borné pour vérifier Grafana, l’alerte e-mail et le retour à l’état normal. Aucun trafic client, conteneur ou contenu d’e-mail n’est modifié.
          </p>
        </div>
        <span className={`w-fit rounded-full border px-3 py-1 text-sm font-bold ${
          exercises.data?.enabled
            ? "border-safe/25 bg-safe-bg text-safe"
            : "border-border-subtle bg-surface-low text-on-surface-variant"
        }`}>
          {exercises.data?.enabled ? "Autorisé" : "Désactivé par configuration"}
        </span>
      </div>

      {active ? (
        <div role="status" className="mt-5 flex flex-col gap-4 border-l-4 border-warning bg-warning-bg p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-bold text-on-surface">{exerciseLabels[active.exercise_type]}</p>
            <p className="mt-1 text-sm text-on-surface-variant">
              Exercice {active.id.slice(0, 8)} · récupération automatique {formatDate(active.expires_at)}
            </p>
          </div>
          <button
            type="button"
            onClick={() => recoverExercise.mutate(active.id)}
            disabled={recoverExercise.isPending}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-warning px-4 text-sm font-bold text-on-surface transition-colors hover:bg-warning/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Square className="h-4 w-4" />
            Rétablir maintenant
          </button>
        </div>
      ) : (
        <div className="mt-5">
          <div className="grid gap-3 md:grid-cols-3">
            {(Object.keys(exerciseLabels) as OperationalExerciseType[]).map((exerciseType) => (
              <button
                key={exerciseType}
                type="button"
                onClick={() => setPendingType(exerciseType)}
                disabled={!exercises.data?.enabled || startExercise.isPending}
                className={`min-h-12 rounded-lg border px-4 py-3 text-left text-sm font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  pendingType === exerciseType
                    ? "border-primary bg-primary-fixed text-on-primary-container"
                    : "border-border-subtle bg-surface-lowest text-on-surface hover:border-primary/50 dark:bg-surface-low"
                }`}
              >
                {exerciseLabels[exerciseType]}
              </button>
            ))}
          </div>
          {pendingType && (
            <div className="mt-4 flex flex-col gap-3 border-l-4 border-primary bg-primary-fixed p-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm leading-6 text-on-primary-container">
                Confirmer l’exercice « {exerciseLabels[pendingType]} ». Le signal durera quatre minutes puis se rétablira automatiquement.
              </p>
              <div className="flex gap-2">
                <button type="button" onClick={() => setPendingType(null)} className="h-10 px-3 text-sm font-bold text-on-primary-container">
                  Annuler
                </button>
                <button
                  type="button"
                  onClick={() => startExercise.mutate(
                    { exercise_type: pendingType, duration_seconds: 240 },
                    { onSuccess: () => setPendingType(null) },
                  )}
                  className="h-10 rounded-lg bg-primary px-4 text-sm font-bold text-on-primary transition-colors hover:bg-primary-dark"
                >
                  Lancer le test
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {(startExercise.isError || recoverExercise.isError) && (
        <p role="alert" className="mt-4 text-sm font-semibold text-error">
          {(startExercise.error || recoverExercise.error)?.message}
        </p>
      )}

      {exercises.data?.recent.length ? (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-border-subtle text-on-surface-variant">
              <tr>
                <th className="px-3 py-2 font-bold">Exercice</th>
                <th className="px-3 py-2 font-bold">Début</th>
                <th className="px-3 py-2 font-bold">Opérateur</th>
                <th className="px-3 py-2 font-bold">État</th>
              </tr>
            </thead>
            <tbody>
              {exercises.data.recent.map((exercise) => (
                <tr key={exercise.id} className="border-b border-border-subtle last:border-b-0">
                  <td className="px-3 py-3 font-semibold text-on-surface">{exerciseLabels[exercise.exercise_type]}</td>
                  <td className="px-3 py-3 text-on-surface-variant">{formatDate(exercise.started_at)}</td>
                  <td className="px-3 py-3 text-on-surface-variant">{exercise.initiated_by}</td>
                  <td className="px-3 py-3 font-semibold text-on-surface">{exercise.status === "active" ? "Actif" : "Rétabli"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

export default function LogsRoute() {
  const reduceMotion = useReducedMotion();
  const { data, isLoading, isError, refetch, isFetching } = useAdminOverview();
  const runtimeHealth = useAdminRuntimeHealth();

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
          <h1 className="app-h1">Console admin</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant">
            Vue plateforme des workspaces, domaines Cloudflare, quarantaines et feedbacks utilisateur.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-border-subtle bg-surface-lowest px-4 text-sm font-bold text-on-surface transition-[background-color,border-color,transform] duration-200 hover:border-primary/45 hover:bg-primary-fixed active:scale-[0.98] dark:bg-surface-low"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          Actualiser
        </button>
      </div>

      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-40 animate-pulse rounded-lg bg-surface-low dark:bg-surface-low" />
          ))}
        </div>
      )}

      {isError && (
        <div role="alert" className="rounded-lg border border-danger/25 bg-danger-bg p-5 text-sm leading-6 text-danger">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="font-bold">Impossible de charger la console admin.</p>
              <p>Vérifiez que votre session est bien marquée platform admin.</p>
            </div>
          </div>
        </div>
      )}

      {data && (
        <>
          <RuntimeHealthPanel health={runtimeHealth.data} isLoading={runtimeHealth.isLoading} />
          <OperationalExercisePanel />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <AdminMetric icon={<Users className="h-5 w-5" />} label="Workspaces" value={data.summary.workspaces_count} help="Espaces client connus par le runtime." />
            <AdminMetric icon={<Activity className="h-5 w-5" />} label="Événements" value={data.summary.threat_events_count} help="Verdicts enregistrés sans messages supprimés." />
            <AdminMetric icon={<Flag className="h-5 w-5" />} label="Feedbacks" value={data.summary.feedback_count} help={`${data.summary.false_negative_count} faux négatifs, dont ${data.summary.reported_email_count} transférés.`} />
            <AdminMetric icon={<Cloud className="h-5 w-5" />} label="Domaines actifs" value={data.summary.cloudflare_active_count} help={`${data.summary.cloudflare_integrations_count} intégrations Cloudflare au total.`} />
            <AdminMetric icon={<LifeBuoy className="h-5 w-5" />} label="Support ouvert" value={data.summary.support_open_count} help="Demandes client à prendre en charge." />
          </div>

          <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
            <section className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
              <div className="mb-5 flex items-center gap-3">
                <BarChart3 className="h-5 w-5 text-primary" />
                <h2 className="app-h2">Répartition des verdicts</h2>
              </div>
              {data.verdicts.length === 0 ? (
                <EmptyPanel title="Aucun verdict enregistré" body="Les premiers emails routés par Cloudflare alimenteront cette section." />
              ) : (
                <div className="space-y-3">
                  {data.verdicts.map((row) => (
                    <div key={row.verdict} className="flex items-center justify-between rounded-lg bg-surface-low px-4 py-3 dark:bg-surface">
                      <span className="text-sm font-bold text-on-surface">{row.verdict}</span>
                      <span className="font-mono text-sm font-semibold text-on-surface-variant">{row.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
              <div className="mb-5 flex items-center gap-3">
                <Cloud className="h-5 w-5 text-primary" />
                <h2 className="app-h2">Domaines Cloudflare</h2>
              </div>
              {data.cloudflare_domains.length === 0 ? (
                <EmptyPanel title="Aucun domaine connecté" body="Les domaines ajoutés depuis Domain Shield apparaîtront ici avec leur statut." />
              ) : (
                <div className="overflow-hidden rounded-lg border border-border-subtle">
                  {data.cloudflare_domains.map((domain) => (
                    <div key={`${domain.zone_name}-${domain.user_email}`} className="grid gap-2 border-b border-border-subtle bg-surface-lowest p-4 last:border-b-0 dark:bg-surface md:grid-cols-[1fr_auto_auto] md:items-center">
                      <div>
                        <p className="text-sm font-bold text-on-surface">{domain.zone_name || "Domaine sans nom"}</p>
                        <p className="text-xs text-on-surface-variant">{domain.user_email || "Utilisateur inconnu"}</p>
                      </div>
                      <span className="w-fit rounded-md bg-primary-fixed px-2.5 py-1 text-xs font-bold text-on-primary-container dark:bg-primary-container">
                        {domain.status || "unknown"}
                      </span>
                      <span className="text-xs font-semibold text-on-surface-variant">{formatDate(domain.updated_at)}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
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
                        <p className="text-sm font-bold text-on-surface">{item.feedback_type}</p>
                        <span className="text-xs font-semibold text-on-surface-variant">{formatDate(item.created_at)}</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                        {item.original_verdict || "inconnu"} vers {item.corrected_verdict}
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
                        <p className="text-sm font-bold text-on-surface">{item.safety_verdict}</p>
                        <span className="font-mono text-xs font-semibold text-on-surface-variant">{Math.round(item.composite_score * 100)} %</span>
                      </div>
                      <p className="mt-2 text-sm text-on-surface-variant">Statut: {item.status}</p>
                      <p className="mt-1 text-xs text-on-surface-variant">Expire le {formatDate(item.expires_at)}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
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
                      <p className="text-sm font-bold text-on-surface">{item.category}</p>
                      <span className="rounded-md bg-primary-fixed px-2 py-1 text-xs font-bold text-on-primary-container">{item.status}</span>
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
