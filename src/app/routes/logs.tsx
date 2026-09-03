import { useTranslation } from "react-i18next";
import { useAdminOverview } from "../lib/api";
import { AdminPage, AdminQueryNotice, useAdminFormatting } from "../components/admin/admin-page";

export default function LogsRoute() {
  const { t, i18n } = useTranslation();
  const query = useAdminOverview();
  const { data } = query;
  const format = useAdminFormatting();
  const metrics = data ? [
    ["workspaces", data.summary.workspaces_count],
    ["events", data.summary.threat_events_count],
    ["feedback", data.summary.feedback_count],
    ["domains", data.summary.cloudflare_active_count],
    ["support", data.summary.support_open_count],
  ] as const : [];

  return (
    <AdminPage view="overview" onRefresh={() => query.refetch()} refreshing={query.isFetching}>
      <AdminQueryNotice loading={query.isLoading} error={query.isError} hasData={!!data} />
      {data && <>
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {metrics.map(([name, value]) => (
            <div key={name} className="rounded-lg border border-border-subtle bg-surface-lowest p-5 dark:bg-surface-low">
              <dt className="text-sm font-semibold text-on-surface-variant">{t(`admin.metrics.${name}`)}</dt>
              <dd className="mt-3 font-mono text-3xl font-semibold text-on-surface">{value.toLocaleString(i18n.language)}</dd>
              {name === "feedback" && <dd className="mt-2 text-xs text-on-surface-variant">{t("admin.feedback_detail", { count: data.summary.false_negative_count, reported: data.summary.reported_email_count })}</dd>}
              {name === "domains" && <dd className="mt-2 text-xs text-on-surface-variant">{t("admin.domains_detail", { count: data.summary.cloudflare_integrations_count })}</dd>}
            </div>
          ))}
        </dl>
        <section aria-labelledby="verdicts-title" className="space-y-5">
          <h2 id="verdicts-title" className="app-h2">{t("admin.verdicts")}</h2>
          {data.verdicts.length === 0 ? <p className="text-sm text-on-surface-variant">{t("admin.empty_verdicts")}</p> : (
            <div className="space-y-5">
              {data.verdicts.map((row) => (
                <div key={row.verdict} className="space-y-2">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-semibold capitalize text-on-surface">{format.value(row.verdict)}</span>
                    <span className="font-mono text-on-surface-variant">{row.count.toLocaleString(i18n.language)}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-surface-high" aria-hidden="true">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${row.count / Math.max(...data.verdicts.map((item) => item.count), 1) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </>}
    </AdminPage>
  );
}
