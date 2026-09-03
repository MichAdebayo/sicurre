import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink, FlaskConical, Play, RefreshCw, Square } from "lucide-react";
import { Button } from "../ui/button";
import { useOperationalExercises, useRecoverOperationalExercise, useStartOperationalExercise, type OperationalExerciseType } from "../../lib/api";

const EXERCISE_SECONDS = 240;
const GRAFANA_URL = "https://sicurre.grafana.net";
const ALERT_RULES: Record<OperationalExerciseType, string> = {
  api_unavailable: "sicurre-controlled-exercise",
  high_latency: "sicurre-controlled-latency",
  elevated_5xx: "sicurre-controlled-server-errors",
};

export function OperationalExercisePanel() {
  const { t, i18n } = useTranslation();
  const query = useOperationalExercises();
  const start = useStartOperationalExercise();
  const recover = useRecoverOperationalExercise();
  const [confirming, setConfirming] = useState(false);
  const [selectedScenario, setSelectedScenario] = useState<OperationalExerciseType>("api_unavailable");
  const [now, setNow] = useState(Date.now);
  const active = query.data?.active;
  const scenario = active?.exercise_type || selectedScenario;
  const supportedTypes = query.data?.supported_types || [];
  const canStart = query.data?.enabled && supportedTypes.includes(scenario);
  const history = query.data?.recent.filter((item) => item.exercise_type === scenario) || [];
  const latest = active || history[0];
  const busy = start.isPending || recover.isPending;
  const stale = query.isError;
  const remaining = active ? Math.max(0, Math.ceil((Date.parse(active.expires_at) - now) / 1000)) : 0;

  useEffect(() => {
    if (active) setSelectedScenario(active.exercise_type);
  }, [active?.exercise_type]);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active?.id]);

  const date = (value: string) => new Date(value).toLocaleString(i18n.language, {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const evidence = new URL(`${GRAFANA_URL}/d/sicurre-controlled-exercise`);
  if (latest) {
    evidence.searchParams.set("from", String(Date.parse(latest.started_at) - 60000));
    evidence.searchParams.set("to", active ? "now" : String(Date.parse(latest.recovered_at || latest.expires_at) + 300000));
  }

  return (
    <section aria-labelledby="exercise-title" className="min-w-0 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="exercise-title" className="app-h2 flex items-center gap-2">
            <FlaskConical className="h-5 w-5 shrink-0 text-navy-dark" aria-hidden="true" />
            {t("operational_test.title", { scenario: t(`operational_test.scenarios.${scenario}`) })}
          </h2>
          <p className="mt-2 text-sm text-on-surface-variant">{t("operational_test.subtitle")}</p>
        </div>
        {query.data && !stale && (
          <span className={`rounded-full border px-3 py-1 text-sm font-semibold ${active
            ? "border-warning/40 bg-warning-bg text-warning"
            : "border-border-subtle bg-surface-low text-on-surface"}`}>
            {t(active ? "operational_test.active" : query.data.enabled ? "operational_test.ready" : "operational_test.disabled")}
          </span>
        )}
      </div>

      <label className="block max-w-md space-y-2 text-sm font-semibold text-on-surface">
        <span>{t("operational_test.scenario")}</span>
        <select value={scenario} disabled={!!active || busy || stale || !query.data?.enabled}
          onChange={(event) => { setSelectedScenario(event.target.value as OperationalExerciseType); setConfirming(false); }}
          className="min-h-11 w-full rounded-lg border border-border-subtle bg-surface-lowest px-3 py-2 text-sm text-on-surface focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-60 dark:bg-surface-low">
          {(Object.keys(ALERT_RULES) as OperationalExerciseType[]).map((type) => (
            <option key={type} value={type} disabled={!!query.data && !supportedTypes.includes(type)}>{t(`operational_test.scenarios.${type}`)}</option>
          ))}
        </select>
      </label>

      {!query.data && !stale && <p role="status" className="text-sm text-on-surface-variant">{t("common.loading")}</p>}
      {stale && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg bg-error-container p-3 text-sm text-on-error-container">
          <p>{t("operational_test.load_error")}</p>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />{t("common.retry")}
          </Button>
        </div>
      )}

      {active ? (
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-warning/40 bg-warning-bg p-4 text-warning">
          <div className="min-w-0">
            <p className="font-semibold">{t("operational_test.signal_active")}</p>
            <p className="mt-1 text-sm">{t("operational_test.expires", { time: `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` })}</p>
            <p className="mt-1 break-all font-mono text-xs">{active.id}</p>
          </div>
          <Button variant="outline" disabled={busy || stale} onClick={() => recover.mutate(active.id)}>
            <Square className="h-4 w-4" aria-hidden="true" />
            {t(recover.isPending ? "operational_test.stopping" : "operational_test.stop")}
          </Button>
        </div>
      ) : query.data && confirming ? (
        <div className="space-y-4 rounded-lg border border-primary/40 bg-primary-container p-4 text-on-primary-container">
          <p>{t("operational_test.confirm", { scenario: t(`operational_test.scenarios.${scenario}`) })}</p>
          <div className="flex flex-wrap gap-3">
            <Button disabled={busy || stale || !canStart} onClick={() => start.mutate(
              { exercise_type: scenario, duration_seconds: EXERCISE_SECONDS },
              { onSuccess: () => { setConfirming(false); setNow(Date.now()); } },
            )}>
              <Play className="h-4 w-4" aria-hidden="true" />{t(start.isPending ? "operational_test.starting" : "operational_test.launch")}
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => setConfirming(false)}>{t("common.cancel")}</Button>
          </div>
        </div>
      ) : query.data ? (
        <Button disabled={!canStart || stale || busy} onClick={() => setConfirming(true)}>
          <Play className="h-4 w-4" aria-hidden="true" />{t("operational_test.start")}
        </Button>
      ) : null}

      {(start.isError || recover.isError) && <p role="alert" className="rounded-lg bg-error-container p-3 text-sm text-on-error-container">{t("operational_test.action_error")}</p>}

      <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
        <a className="inline-flex min-h-10 items-center gap-2 font-semibold text-navy-dark underline underline-offset-4" href={evidence.toString()} target="_blank" rel="noreferrer">
          {t("operational_test.evidence")}<ExternalLink className="h-4 w-4" aria-hidden="true" />
        </a>
        <a className="inline-flex min-h-10 items-center gap-2 font-semibold text-navy-dark underline underline-offset-4" href={`${GRAFANA_URL}/alerting/grafana/${ALERT_RULES[scenario]}/view`} target="_blank" rel="noreferrer">
          {t("operational_test.alert_state")}<ExternalLink className="h-4 w-4" aria-hidden="true" />
        </a>
      </div>

      {!!history.length && (
        <table className="w-full table-fixed border-collapse text-left text-sm">
          <caption className="pb-3 text-left font-semibold text-on-surface">{t("operational_test.history")}</caption>
          <thead className="border-y border-border-subtle bg-surface-low text-on-surface-variant">
            <tr>
              <th scope="col" className="w-2/5 p-2 font-semibold">{t("operational_test.test")}</th>
              <th scope="col" className="p-2 font-semibold">{t("operational_test.started")}</th>
              <th scope="col" className="p-2 font-semibold">{t("operational_test.signal")}</th>
            </tr>
          </thead>
          <tbody>
            {history.map((item) => (
              <tr key={item.id} className="border-b border-border-subtle align-top text-on-surface">
                <td className="break-words p-2">
                  <span className="block font-semibold">{t(`operational_test.scenarios.${item.exercise_type}`)}</span>
                  <span className="mt-1 block font-mono text-xs text-on-surface-variant" title={item.id}>{item.id.slice(0, 8)}</span>
                  <span className="mt-1 block break-all text-xs text-on-surface-variant">{item.initiated_by}</span>
                </td>
                <td className="p-2"><time dateTime={item.started_at}>{date(item.started_at)}</time></td>
                <td className="p-2">
                  <span>{t(item.status === "active" ? "operational_test.active" : "operational_test.ended")}</span>
                  {item.recovered_at && <time className="mt-1 block text-xs text-on-surface-variant" dateTime={item.recovered_at}>{date(item.recovered_at)}</time>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
