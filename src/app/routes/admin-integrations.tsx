import { useDeferredValue, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Loader2, Search, Trash2 } from "lucide-react";
import { useAdminDomains, useEraseAdminAccount, type AdminDomainPage } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Dialog } from "../components/ui/dialog";
import { DataTable, type Column } from "../components/ui/data-table";
import { AppToast } from "../components/common/app-toast";
import { AdminPage, AdminQueryNotice, useAdminFormatting } from "../components/admin/admin-page";

type AdminDomainRow = AdminDomainPage["items"][number];

const normalizeEmail = (value: string) => value.trim().toLowerCase();

// The API refuses in English; the two refusals an admin can expect read in the interface language.
const REFUSAL_KEYS: Record<string, string> = {
  "Erase your own account from your settings, not from here": "admin.erase_own_refused",
  "No account with this email": "admin.erase_not_found",
};

interface AdminIntegrationsRouteProps {
  /** The signed-in admin. Their own account is deleted from their settings, never from this page. */
  currentEmail?: string;
}

export default function AdminIntegrationsRoute({ currentEmail = "" }: AdminIntegrationsRouteProps) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const query = useAdminDomains(page, deferredSearch);
  const format = useAdminFormatting();
  const { data } = query;
  const ownEmail = normalizeEmail(currentEmail);

  // Accounts are selected by owner address: one owner can hold several domains,
  // and deleting the account removes every domain it holds.
  const [selected, setSelected] = useState<string[]>([]);
  const [eraseEmailInput, setEraseEmailInput] = useState("");
  const [pendingEmails, setPendingEmails] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [eraseDone, setEraseDone] = useState<string[]>([]);
  const [eraseFailures, setEraseFailures] = useState<{ email: string; reason: string }[]>([]);
  const eraseMutation = useEraseAdminAccount();
  const busy = running || eraseMutation.isPending;

  const isOwn = (email: string) => ownEmail !== "" && normalizeEmail(email) === ownEmail;
  const pageOwners = useMemo(() => {
    const owners = (data?.items ?? [])
      .map((row) => row.user_email)
      .filter((email): email is string => Boolean(email))
      .map(normalizeEmail)
      .filter((email) => email !== ownEmail);
    return Array.from(new Set(owners));
  }, [data, ownEmail]);
  const allSelected = pageOwners.length > 0 && pageOwners.every((email) => selected.includes(email));

  const toggleOwner = (email: string) =>
    setSelected((current) => (current.includes(email) ? current.filter((item) => item !== email) : [...current, email]));
  const toggleAll = () =>
    setSelected((current) => (allSelected ? current.filter((email) => !pageOwners.includes(email)) : Array.from(new Set([...current, ...pageOwners]))));

  const askErase = (emails: string[]) => {
    const unique = Array.from(new Set(emails.map(normalizeEmail).filter(Boolean)));
    setEraseDone([]);
    setEraseFailures([]);
    if (unique.some(isOwn)) {
      setEraseFailures([{ email: ownEmail, reason: t("admin.erase_own_refused") }]);
      return;
    }
    if (unique.length > 0) setPendingEmails(unique);
  };
  const closeDialog = () => {
    if (!busy) setPendingEmails([]);
  };
  const runErase = async () => {
    if (busy || pendingEmails.length === 0) return;
    setRunning(true);
    const done: string[] = [];
    const failures: { email: string; reason: string }[] = [];
    // One account at a time: each deletion talks to Cloudflare, and a refusal
    // on one account must not stop the others nor hide which one it was.
    for (const email of pendingEmails) {
      try {
        await eraseMutation.mutateAsync(email);
        done.push(email);
      } catch (error) {
        const key = error instanceof Error ? REFUSAL_KEYS[error.message] : undefined;
        failures.push({ email, reason: t(key ?? "admin.erase_failed") });
      }
    }
    setRunning(false);
    setEraseDone(done);
    setEraseFailures(failures);
    setSelected((current) => current.filter((email) => !done.includes(email)));
    setEraseEmailInput("");
    setPendingEmails([]);
  };

  const columns: Column<AdminDomainRow>[] = [
    {
      header: (
        <input type="checkbox" aria-label={t("admin.select_all")} checked={allSelected} disabled={pageOwners.length === 0}
          onChange={toggleAll} className="h-4 w-4 cursor-pointer accent-primary" />
      ),
      className: "w-12",
      render: (row) => row.user_email && !isOwn(row.user_email) ? (
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
      render: (row) => {
        if (!row.user_email) return null;
        if (isOwn(row.user_email)) {
          return <span className="text-xs font-semibold text-on-surface-variant">{t("admin.own_account")}</span>;
        }
        const email = row.user_email;
        return (
          <Button variant="ghost" size="sm" className="gap-1.5 text-error cursor-pointer" onClick={() => askErase([email])}
            aria-label={t("admin.erase_row_label", { email })}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />{t("admin.erase_account")}
          </Button>
        );
      },
    },
  ];

  return (
    <AdminPage view="integrations" onRefresh={() => query.refetch()}>
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

      {eraseFailures.length > 0 && (
        <ul role="alert" className="space-y-1 text-xs font-semibold text-error">
          {eraseFailures.map((failure) => <li key={failure.email}>{failure.email} : {failure.reason}</li>)}
        </ul>
      )}

      <section className="rounded-xl border border-border-subtle p-5">
        <h3 className="text-sm font-bold text-on-surface">{t("admin.erase_by_email_title")}</h3>
        <form onSubmit={(event) => { event.preventDefault(); askErase([eraseEmailInput]); }} className="mt-3 flex flex-col sm:flex-row sm:items-end gap-3">
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
        size="sm"
        title={t("admin.erase_dialog_title", { count: pendingEmails.length })}
        description={t("admin.erase_dialog_desc")}
        footer={
          <div className="flex justify-end gap-2.5">
            <Button type="button" variant="outline" size="sm" className="font-bold text-xs cursor-pointer" onClick={closeDialog} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="button" variant="danger" size="sm" className="gap-2 font-bold text-xs cursor-pointer" onClick={runErase} disabled={busy}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
              {busy ? t("admin.erase_pending") : t("admin.erase_confirm")}
            </Button>
          </div>
        }
      >
        <ul className="space-y-1 text-sm font-semibold text-on-surface">
          {pendingEmails.map((email) => <li key={email} className="break-all">{email}</li>)}
        </ul>
      </Dialog>

      <AppToast
        tone="success"
        message={t("admin.erase_done", { count: eraseDone.length, emails: eraseDone.join(", ") })}
        visible={eraseDone.length > 0}
        onClose={() => setEraseDone([])}
      />
    </AdminPage>
  );
}
