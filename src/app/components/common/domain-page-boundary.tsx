import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useActiveDomain } from "../../contexts/active-domain";
import { PageLoading } from "./page-loading";

export function DomainPageBoundary({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { isLoading, isError, retry } = useActiveDomain();

  if (isLoading) return <PageLoading />;
  if (isError) {
    return (
      <div role="alert" className="flex min-h-48 flex-col items-center justify-center gap-4 text-on-surface">
        <p>{t("common.domains_load_error")}</p>
        <button type="button" onClick={retry} className="rounded-lg border border-outline-variant px-4 py-2 font-semibold hover:bg-surface-container focus-visible:outline-2 focus-visible:outline-primary">
          {t("common.retry")}
        </button>
      </div>
    );
  }
  return children;
}
