import { useTranslation } from "react-i18next";
import { useAdminOverview } from "../lib/api";
import { AdminPage, AdminQueryNotice, useAdminFormatting } from "../components/admin/admin-page";

export default function AdminReviewsRoute() {
  const { t } = useTranslation();
  const query = useAdminOverview();
  const { data } = query;
  const format = useAdminFormatting();
  const itemClass = "min-w-0 rounded-lg border border-border-subtle bg-surface-lowest p-4 text-sm dark:bg-surface-low";
  return (
    <AdminPage view="reviews" onRefresh={() => query.refetch()} refreshing={query.isFetching}>
      <AdminQueryNotice loading={query.isLoading} error={query.isError} hasData={!!data} />
      {data && <>
        <div className="grid gap-8 xl:grid-cols-2">
          <section className="min-w-0 space-y-5" aria-labelledby="feedback-title">
            <h2 id="feedback-title" className="app-h2">{t("admin.recent_feedback")}</h2>
            {!data.recent_feedback.length && <p className="text-sm text-on-surface-variant">{t("admin.empty_feedback")}</p>}
            {data.recent_feedback.map((item) => <article key={item.id} className={itemClass}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold capitalize text-on-surface">{format.value(item.feedback_type)}</h3>
                <time dateTime={item.created_at} className="text-xs text-on-surface-variant">{format.date(item.created_at)}</time>
              </div>
              <p className="mt-2 text-on-surface-variant">{format.value(item.original_verdict)} → {format.value(item.corrected_verdict)}</p>
              <p className="mt-1 break-all text-xs text-on-surface-variant">{item.reporter_email || item.workspace_id}</p>
            </article>)}
          </section>
          <section className="min-w-0 space-y-5" aria-labelledby="quarantine-title">
            <h2 id="quarantine-title" className="app-h2">{t("admin.recent_quarantine")}</h2>
            {!data.recent_quarantine.length && <p className="text-sm text-on-surface-variant">{t("admin.empty_quarantine")}</p>}
            {data.recent_quarantine.map((item) => <article key={item.id} className={itemClass}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold capitalize text-on-surface">{format.value(item.safety_verdict)}</h3>
                <span className="font-mono text-xs text-on-surface-variant">{Math.round(item.composite_score * 100)} %</span>
              </div>
              <p className="mt-2 text-on-surface-variant">{t("admin.status")}: {format.value(item.status)}</p>
              <p className="mt-1 text-xs text-on-surface-variant">{t("admin.expires", { date: format.date(item.expires_at) })}</p>
            </article>)}
          </section>
        </div>
        <section className="space-y-5" aria-labelledby="support-title">
          <h2 id="support-title" className="app-h2">{t("admin.recent_support")}</h2>
          {!data.recent_support.length && <p className="text-sm text-on-surface-variant">{t("admin.empty_support")}</p>}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.recent_support.map((item) => <article key={item.id} className={itemClass}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold capitalize text-on-surface">{format.value(item.category)}</h3>
                <span className="rounded-full border border-border-subtle px-2.5 py-1 text-xs text-on-surface">{format.value(item.status)}</span>
              </div>
              <p className="mt-2 break-all text-on-surface-variant">{item.requester_email}</p>
              <time dateTime={item.created_at} className="mt-1 block text-xs text-on-surface-variant">{format.date(item.created_at)}</time>
            </article>)}
          </div>
        </section>
      </>}
    </AdminPage>
  );
}
