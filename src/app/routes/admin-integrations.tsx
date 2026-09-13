import { useDeferredValue, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ChevronLeft, ChevronRight, Search, Trash2 } from "lucide-react";
import { useAdminDomains, useEraseAdminAccount, type AdminDomainPage } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Dialog } from "../components/ui/dialog";
import { DataTable, type Column } from "../components/ui/data-table";
import { AdminPage, AdminQueryNotice, useAdminFormatting } from "../components/admin/admin-page";

type AdminDomainRow = AdminDomainPage["items"][number];

const normalizeEmail = (value: string) => value.trim().toLowerCase();

export default function AdminIntegrationsRoute() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const query = useAdminDomains(page, deferredSearch);
  const format = useAdminFormatting();
  const { data } = query;

  // Accounts are selected by owner address: one owner can hold several domains,
  // and erasing an account removes every domain it holds in one cascade.
  const [selected, setSelected] = useState<string[]>([]);
  const [eraseEmailInput, setEraseEmailInput] = useState("");
  const [pendingEmails, setPendingEmails] = useState<string[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [eraseDone, setEraseDone] = useState<string[]>([]);
  const [eraseFailures, setEraseFailures] = useState<{ email: string; reason: string }[]>([]);
  const eraseMutation = useEraseAdminAccount();

  const pageOwners = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((row) => row.user_email).filter(Boolean).map((email) => normalizeEmail(email as string)))),
    [data],
  );
  const allSelected = pageOwners.length > 0 && pageOwners.every((email) => selected.includes(email));

  const toggleOwner = (email: string) =>
    setSelected((current) => (current.includes(email) ? current.filter((item) => item !== email) : [...current, email]));
  const toggleAll = () =>
    setSelected((current) => (allSelected ? current.filter((email) => !pageOwners.includes(email)) : Array.from(new Set([...current, ...pageOwners]))));

  const askErase = (emails: string[]) => {
    const unique = Array.from(new Set(emails.map(normalizeEmail).filter(Boolean)));
    if (unique.length === 0) return;
    setPendingEmails(unique);
    setAcknowledged(false);
    setEraseDone([]);
    setEraseFailures([]);
  };
  const closeDialog = () => {
    if (eraseMutation.isPending) return;
    setPendingEmails([]);
    setAcknowledged(false);
  };
  const runErase = async () => {
    if (!acknowledged || pendingEmails.length === 0) return;
    const done: string[] = [];
    const failures: { email: string; reason: string }[] = [];
    // One account at a time: each cascade talks to Cloudflare, and a refusal
    // on one account must not stop the others nor hide which one it was.
    for (const email of pendingEmails) {
      try {
        await eraseMutation.mutateAsync(email);
        done.push(email);
      } catch (error) {
        failures.push({ email, reason: error instanceof Error ? error.message : t("admin.erase_failed") });
      }
    }
    setEraseDone(done);
    setEraseFailures(failures);
    setSelected((current) => current.filter((email) => !done.includes(email)));
    setEraseEmailInput("");
    setPendingEmails([]);
    setAcknowledged(false);
  };

  const columns: Column<AdminDomainRow>[] = [
    {
      header: (
        <input type="checkbox" aria-label={t("admin.select_all")} checked={allSelected} disabled={pageOwners.length === 0}
          onChange={toggleAll} className="h-4 w-4 cursor-pointer accent-primary" />
      ),
      className: "w-12",
      render: (row) => row.user_email ? (
        <input type="checkbox" aria-label={t("admin.select_row", { email: row.user_email })} checked={selected.includes(normalizeEmail(row.user_email))}
          onChange={() => toggleOwner(normalizeEmail(row.user_email as string))} className="h-4 w-4 cursor-pointer accent-primary" />
      ) : null,
    },
    { header: t("admin.col_domain"), render: (row) => <span className="font-semibold">{row.zone_name || t("admin.unknown")}</span> },
    { header: t("admin.col_owner"), render: (row) => <span className="text-on-surface-variant">{row.user_email || t("admin.unknown")}</span> },
    {
      header: t("admin.status"),
      render: (row) => (
        <span className="rounded-full border border-border-subtle bg-surface-low px-2.5 py-1 text-xs font-semibold text-on-surface">{format.value(row.status)}</span>
      ),
    },
    { header: t("admin.col_updated"), render: (row) => <span className="text-xs text-on-surface-variant">{format.date(row.updated_at)}</span> },
    {
      header: t("admin.col_actions"),
      className: "text-right",
      render: (row) => row.user_email ? (
        <Button variant="ghost" size="sm" className="gap-1.5 text-error cursor-pointer" onClick={() => askErase([row.user_email as string])}
          aria-label={`${t("admin.erase_account")} ${row.user_email}`}>
          <Trash2 className="h-4 w-4" aria-hidden="true" />{t("admin.erase_account")}
        </Button>
      ) : null,
    },
  ];

  return (
    <AdminPage view="integrations" onRefresh={() => query.refetch()} refreshing={query.isFetching}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="app-h2">{t("admin.domains_title")}{data && <span className="ml-2 text-sm font-normal text-on-surface-variant">({data.total})</span>}</h2>
        <div className="flex flex-wrap items-center gap-3">
          {selected.length > 0 && (
            <Button variant="danger" size="sm" className="gap-2 cursor-pointer" onClick={() => askErase(selected)}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />{t("admin.erase_selected", { count: selected.length })}
            </Button>
          )}
          <label className="relative block w-full sm:w-72">
            <span className="sr-only">{t("admin.domain_search")}</span>
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" aria-hidden="true" />
            <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder={t("admin.domain_search")}
              className="h-10 w-full rounded-lg border border-border-subtle bg-surface-lowest pl-9 pr-3 text-sm text-on-surface focus-visible:outline-2 focus-visible:outline-primary dark:bg-surface-low" />
          </label>
        </div>
      </div>
      <AdminQueryNotice loading={query.isLoading} error={query.isError} hasData={!!data} />
      {data && (
        <DataTable columns={columns} data={data.items} keyExtractor={(row) => `${row.zone_name}-${row.user_email}`}
          emptyMessage={t(search ? "admin.no_matching_domains" : "admin.empty_domains")} />
      )}
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

      {eraseDone.length > 0 && (
        <p role="status" className="text-xs font-semibold text-safe">{t("admin.erase_done", { emails: eraseDone.join(", ") })}</p>
      )}
      {eraseFailures.length > 0 && (
        <ul role="alert" className="space-y-1 text-xs font-semibold text-error">
          {eraseFailures.map((failure) => <li key={failure.email}>{failure.email} : {failure.reason}</li>)}
        </ul>
      )}

      <section className="rounded-xl border border-border-subtle p-5">
        <h3 className="text-sm font-bold text-on-surface">{t("admin.erase_by_email_title")}</h3>
        <p className="app-body-sub mt-1">{t("admin.erase_by_email_desc")}</p>
        <form onSubmit={(event) => { event.preventDefault(); askErase([eraseEmailInput]); }} className="mt-4 flex flex-col sm:flex-row sm:items-end gap-3">
          <div className="flex-1">
            <Input label={t("admin.erase_by_email_label")} type="email" autoComplete="off" value={eraseEmailInput}
              onChange={(event) => setEraseEmailInput(event.target.value)} />
          </div>
          <Button type="submit" variant="outline" className="gap-2 shrink-0 cursor-pointer text-error" disabled={!eraseEmailInput.trim()}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />{t("admin.erase_account")}
          </Button>
        </form>
      </section>

      <Dialog
        isOpen={pendingEmails.length > 0}
        onClose={closeDialog}
        role="alertdialog"
        title={t("admin.erase_dialog_title")}
        description={t("admin.erase_dialog_desc")}
        footer={
          <div className="flex flex-wrap justify-end gap-3">
            <Button type="button" variant="outline" className="cursor-pointer" onClick={closeDialog} disabled={eraseMutation.isPending}>
              {t("common.cancel")}
            </Button>
            <Button type="button" variant="danger" className="gap-2 cursor-pointer" onClick={runErase} disabled={!acknowledged || eraseMutation.isPending}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />{t("admin.erase_confirm")}
            </Button>
          </div>
        }
      >
        <ul className="space-y-1 rounded-lg border border-border-subtle bg-surface-low/50 p-3 text-sm font-semibold text-on-surface">
          {pendingEmails.map((email) => <li key={email} className="break-all">{email}</li>)}
        </ul>
        <p className="mt-3 flex items-start gap-2 text-sm text-error">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t("admin.erase_dialog_warning")}</span>
        </p>
        <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm text-on-surface">
          <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} className="mt-0.5 h-4 w-4 cursor-pointer accent-primary" />
          <span>{t("admin.erase_acknowledge")}</span>
        </label>
      </Dialog>
    </AdminPage>
  );
}
