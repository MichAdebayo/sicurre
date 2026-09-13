import { Component, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { isChunkLoadError, reloadOnceForStaleBuild, reloadPage } from "../../lib/stale-build";

interface AppErrorBoundaryState {
  error: unknown;
}

/**
 * Last line of defence for the whole application. Without it any render
 * error, a page file missing after a deploy included, unmounted everything
 * and left a white screen. A missing page file reloads once to pick up the
 * current build; anything else shows a short message and a reload button.
 */
export class AppErrorBoundary extends Component<{ children: ReactNode }, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): AppErrorBoundaryState {
    return { error: error ?? new Error("Unknown render error") };
  }

  componentDidCatch(error: unknown): void {
    if (isChunkLoadError(error)) reloadOnceForStaleBuild();
  }

  render() {
    if (!this.state.error) return this.props.children;
    return <PageLoadError />;
  }
}

function PageLoadError() {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="min-h-screen w-full flex flex-col items-center justify-center gap-4 bg-surface-low px-6 text-center text-on-surface"
    >
      <p className="text-sm font-semibold">{t("common.page_load_error")}</p>
      <button
        type="button"
        onClick={reloadPage}
        className="rounded-lg border border-outline-variant px-4 py-2 text-sm font-semibold hover:bg-surface-container focus-visible:outline-2 focus-visible:outline-primary"
      >
        {t("common.reload")}
      </button>
    </div>
  );
}
