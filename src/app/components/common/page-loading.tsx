import { useTranslation } from "react-i18next";

export function PageLoading() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-label={t("common.loading")} className="space-y-8 py-2">
      <div aria-hidden="true" className="space-y-3">
        <div className="h-9 w-64 max-w-full rounded bg-surface-container" />
        <div className="h-5 w-96 max-w-full rounded bg-surface-container" />
      </div>
      <div aria-hidden="true" className="h-64 rounded-lg bg-surface-container" />
    </div>
  );
}
