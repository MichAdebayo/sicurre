import { useTranslation } from "react-i18next";
import { useAdminRuntimeHealth, type AdminRuntimeHealth } from "../../lib/api";
import { Button } from "../ui/button";
import { RefreshCw } from "lucide-react";
import { AdminQueryNotice } from "./admin-page";

const HEALTH_MAX_AGE_MS = 120_000;
const HEALTH_CLOCK_INTERVAL_MS = 10_000;

function statusClass(status: AdminRuntimeHealth["status"]): string {
  if (status === "ok") return "border-safe/25 bg-safe-bg text-safe";
  if (status === "degraded") return "border-warning/25 bg-warning-bg text-warning";
  if (status === "down") return "border-error/25 bg-error-container text-on-error-container";
  return "border-border-subtle bg-surface-low text-on-surface-variant";
}

export function RuntimeHealthPanel() {
  const { t, i18n } = useTranslation();
  const query = useAdminRuntimeHealth();
  const health = query.data;
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), HEALTH_CLOCK_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);
  const checkedAt = Date.parse(health?.checked_at || "");
  const stale = !Number.isFinite(checkedAt) || now - checkedAt > HEALTH_MAX_AGE_MS;
  const unavailable = query.isError || stale;
  const status = unavailable ? "unknown" : health?.status || "unknown";
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span role="status" className={`rounded-full border px-3 py-1 text-sm font-semibold ${statusClass(status)}`}>
            {t(`admin.health.status.${status}`)}
          </span>
          <p className="text-sm text-on-surface-variant">
            {t("admin.health.last_check")}: {Number.isFinite(checkedAt)
              ? <time dateTime={health?.checked_at}>{new Date(checkedAt).toLocaleString(i18n.language)}</time>
              : t("admin.unknown")}
          </p>
        </div>
        <Button variant="outline" size="sm" disabled={query.isFetching} onClick={() => query.refetch()}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />{t("admin.refresh")}
        </Button>
      </div>
      {query.isError && health
        ? <p role="alert" className="rounded-lg bg-error-container p-4 text-sm text-on-error-container">{t("admin.health.unavailable")}</p>
        : <AdminQueryNotice loading={query.isLoading} error={query.isError} hasData={!!health} />}
      {health && stale && !query.isError && <p className="text-sm text-on-surface-variant">{t("admin.health.stale")}</p>}
      {health && <>
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="font-semibold text-on-surface">{t("admin.health.gateway")}</dt>
            <dd className="mt-1 break-all text-on-surface-variant">{health.expected_worker_scan_url || t("admin.unknown")}</dd>
          </div>
          <div className="min-w-0">
            <dt className="font-semibold text-on-surface">{t("admin.health.classifier")}</dt>
            <dd className="mt-1 break-all text-on-surface-variant">{health.inference_api_url || t("admin.unknown")}</dd>
          </div>
        </dl>
        <div className="grid gap-4 xl:grid-cols-2">
          {health.components.map((component) => {
            const componentStatus = unavailable ? "unknown" : component.status;
            return (
            <div key={component.component} className="min-w-0 rounded-lg border border-border-subtle bg-surface-lowest p-4 dark:bg-surface-low">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-on-surface">{t(`admin.health.components.${component.component}`, { defaultValue: component.component.replaceAll("_", " ") })}</h3>
                <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClass(componentStatus)}`}>{t(`admin.health.status.${componentStatus}`)}</span>
              </div>
              <p className="mt-2 text-sm text-on-surface-variant">{t(`admin.health.messages.${componentStatus}`)}</p>
              {component.detail && <details className="mt-3 text-xs text-on-surface-variant">
                <summary className="cursor-pointer font-semibold">{t("admin.health.technical_detail")}</summary>
                <p className="mt-2 break-all">{component.detail}</p>
              </details>}
              {component.latency_ms !== null && <p className="mt-2 font-mono text-xs text-on-surface-variant">{component.latency_ms} ms</p>}
            </div>
            );
          })}
        </div>
      </>}
    </div>
  );
}
import { useEffect, useState } from "react";
