import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { Button } from "../ui/button";

export function AdminPage({ view, children, onRefresh, refreshing = false }: {
  view: "overview" | "operations" | "incidents" | "integrations" | "reviews";
  children: ReactNode;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0 space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="app-h1">{t(`admin.views.${view}`)}</h1>
        {onRefresh && <Button variant="outline" disabled={refreshing} onClick={onRefresh}>
          <RefreshCw className={`h-4 w-4 ${refreshing ? "motion-safe:animate-spin" : ""}`} aria-hidden="true" />
          {t("admin.refresh")}
        </Button>}
      </header>
      {children}
    </div>
  );
}

export function AdminQueryNotice({ loading, error, hasData }: { loading: boolean; error: boolean; hasData: boolean }) {
  const { t } = useTranslation();
  if (error) return <p role="alert" className="rounded-lg bg-error-container p-4 text-sm text-on-error-container">
    {t(hasData ? "admin.refresh_error" : "admin.load_error")}
  </p>;
  if (loading && !hasData) return <p role="status" className="text-sm text-on-surface-variant">{t("common.loading")}</p>;
  return null;
}

export function useAdminFormatting() {
  const { t, i18n } = useTranslation();
  return {
    value: (value: string | null | undefined) => value
      ? t(`admin.values.${value}`, { defaultValue: value.replaceAll("_", " ") }) : t("admin.unknown"),
    date: (value: string | null | undefined) => value ? new Date(value).toLocaleString(i18n.language, {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    }) : t("admin.unknown"),
  };
}
