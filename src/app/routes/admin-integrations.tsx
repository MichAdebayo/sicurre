import { useDeferredValue, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useAdminDomains } from "../lib/api";
import { Button } from "../components/ui/button";
import { AdminPage, AdminQueryNotice, useAdminFormatting } from "../components/admin/admin-page";

export default function AdminIntegrationsRoute() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const query = useAdminDomains(page, deferredSearch);
  const format = useAdminFormatting();
  const { data } = query;
  return (
    <AdminPage view="integrations" onRefresh={() => query.refetch()} refreshing={query.isFetching}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="app-h2">{t("admin.domains_title")}{data && <span className="ml-2 text-sm font-normal text-on-surface-variant">({data.total})</span>}</h2>
        <label className="relative block w-full sm:w-72">
          <span className="sr-only">{t("admin.domain_search")}</span>
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" aria-hidden="true" />
          <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder={t("admin.domain_search")}
            className="h-10 w-full rounded-lg border border-border-subtle bg-surface-lowest pl-9 pr-3 text-sm text-on-surface focus-visible:outline-2 focus-visible:outline-primary dark:bg-surface-low" />
        </label>
      </div>
      <AdminQueryNotice loading={query.isLoading} error={query.isError} hasData={!!data} />
      {data && (data.items.length ? <ul className="divide-y divide-border-subtle">
        {data.items.map((domain) => (
          <li key={`${domain.zone_name}-${domain.user_email}`} className="grid min-w-0 gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
            <div className="min-w-0">
              <p className="break-all text-sm font-semibold text-on-surface">{domain.zone_name || t("admin.unknown")}</p>
              <p className="mt-1 break-all text-xs text-on-surface-variant">{domain.user_email || t("admin.unknown")}</p>
            </div>
            <span className="w-fit rounded-full border border-border-subtle bg-surface-low px-2.5 py-1 text-xs font-semibold text-on-surface">{format.value(domain.status)}</span>
            <span className="text-xs text-on-surface-variant">{format.date(domain.updated_at)}</span>
          </li>
        ))}
      </ul> : <p className="text-sm text-on-surface-variant">{t(search ? "admin.no_matching_domains" : "admin.empty_domains")}</p>)}
      {data && data.pages > 1 && <nav aria-label={t("admin.pagination")} className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="text-on-surface-variant">{t("admin.page_number", { page: data.page, pages: data.pages })}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page === 1 || query.isFetching} onClick={() => setPage(page - 1)}>
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />{t("common.previous")}
          </Button>
          <Button variant="outline" size="sm" disabled={page >= data.pages || query.isFetching} onClick={() => setPage(page + 1)}>
            {t("common.next")}<ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </nav>}
    </AdminPage>
  );
}
