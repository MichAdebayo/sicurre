// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import type { AdminRuntimeHealth } from "../../../src/app/lib/api";
import fr from "../../../src/app/locales/fr.json";
import en from "../../../src/app/locales/en.json";
import Operations from "../../../src/app/routes/admin-operations";
import Incidents from "../../../src/app/routes/admin-incidents";

const state = vi.hoisted(() => ({
  data: undefined as AdminRuntimeHealth | undefined,
  isError: false, isLoading: false, isFetching: false, health: vi.fn(), refetch: vi.fn(),
}));
vi.mock("../../../src/app/lib/api", () => ({ useAdminRuntimeHealth: () => { state.health(); return state; } }));
vi.mock("../../../src/app/components/admin/operational-exercise-panel", () => ({
  OperationalExercisePanel: () => <div>Exercise controls</div>,
}));

function renderPage(page: ReactNode = <Operations />, lang = "en") {
  const i18n = createInstance();
  i18n.init({ lng: lang, resources: { fr: { translation: fr }, en: { translation: en } }, initImmediate: false });
  return render(<I18nextProvider i18n={i18n}>{page}</I18nextProvider>);
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-03T12:00:00Z"));
  state.data = {
    status: "ok", checked_at: new Date().toISOString(), public_api_host: null,
    expected_worker_scan_url: null, inference_api_url: null,
    components: [{ component: "inference_api", status: "ok", message: "Available", detail: null, checked_url: null, latency_ms: 10 }],
  };
  state.isError = false; state.isLoading = false; state.isFetching = false;
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });

describe("health and incident separation", () => {
  it.each(["fr", "en"])("shows observed health, last check and refresh without exercises (%s)", (lang) => {
    renderPage(<Operations />, lang);
    const copy = lang === "fr" ? fr : en;
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(copy.admin.views.operations);
    expect(screen.getByRole("status")).toHaveTextContent(copy.admin.health.status.ok);
    expect(document.querySelector("time")).toHaveAttribute("dateTime", state.data!.checked_at);
    expect(screen.queryByText("Exercise controls")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: copy.admin.refresh }));
    expect(state.refetch).toHaveBeenCalledOnce();
  });

  it("does not fetch runtime health from Incidents", () => {
    renderPage(<Incidents />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Incidents");
    expect(screen.getByText("Exercise controls")).toBeVisible();
    expect(state.health).not.toHaveBeenCalled();
  });

  it.each(["missing", "error", "stale", "invalid"])("never shows green health for %s observations", (mode) => {
    if (mode === "missing") state.data = undefined;
    if (mode === "error") state.isError = true;
    if (mode === "stale") state.data!.checked_at = "2026-09-03T11:55:00Z";
    if (mode === "invalid") state.data!.checked_at = "invalid";
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Unknown");
    expect(screen.queryByText("Operational")).not.toBeInTheDocument();
    expect(document.querySelector(".text-safe")).toBeNull();
    if (mode === "error") expect(screen.getByRole("alert")).toBeVisible();
  });

  it("expires stale health without another network response", () => {
    renderPage();
    act(() => { vi.advanceTimersByTime(130_000); });
    expect(screen.getByRole("status")).toHaveTextContent("Unknown");
    expect(screen.getByText(en.admin.health.stale)).toBeVisible();
  });

  it("preserves down/degraded/unknown responses and disables a pending refresh", () => {
    state.data!.status = "down";
    state.data!.components[0].status = "degraded";
    state.isFetching = true;
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Incident");
    expect(screen.getByText("Degraded")).toBeVisible();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
  });
});
