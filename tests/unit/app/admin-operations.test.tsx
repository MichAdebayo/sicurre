// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import fr from "../../../src/app/locales/fr.json";
import en from "../../../src/app/locales/en.json";

import LogsRoute from "../../../src/app/routes/logs";

const mocks = vi.hoisted(() => ({
  start: vi.fn(),
  recover: vi.fn(),
  refetch: vi.fn(),
  loading: false,
  error: false,
  state: {
    enabled: true,
    active: null as null | {
      id: string;
      exercise_type: "api_unavailable";
      initiated_by: string;
      started_at: string;
      expires_at: string;
    },
  },
}));

vi.mock("../../../src/app/lib/api", () => ({
  useAdminOverview: () => ({
    data: {
      summary: {
        workspaces_count: 0, members_count: 0, threat_events_count: 0,
        feedback_count: 0, false_negative_count: 0, reported_email_count: 0,
        quarantine_held_count: 0, cloudflare_integrations_count: 0,
        cloudflare_active_count: 0, support_open_count: 0,
      },
      verdicts: [], feedback_by_type: [], cloudflare_domains: [],
      recent_feedback: [], recent_quarantine: [], recent_support: [],
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    isFetching: false,
  }),
  useAdminRuntimeHealth: () => ({ data: undefined, isLoading: false }),
  useAdminDomains: () => ({ data: { items: [], page: 1, page_size: 20, total: 0, pages: 1 } }),
  useOperationalExercises: () => ({
    data: mocks.loading || mocks.error ? undefined : { ...mocks.state, recent: [], supported_types: ["api_unavailable", "high_latency", "elevated_5xx"] },
    isLoading: mocks.loading,
    isError: mocks.error,
    refetch: mocks.refetch,
  }),
  useStartOperationalExercise: () => ({ mutate: mocks.start, isPending: false, isError: false, error: null }),
  useRecoverOperationalExercise: () => ({ mutate: mocks.recover, isPending: false, isError: false, error: null }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.state.enabled = true;
  mocks.state.active = null;
  mocks.loading = false;
  mocks.error = false;
});

function renderOperations(language = "fr") {
  const i18n = createInstance();
  i18n.init({ lng: language, fallbackLng: "fr", resources: { fr: { translation: fr }, en: { translation: en } }, initImmediate: false });
  render(<I18nextProvider i18n={i18n}><LogsRoute /></I18nextProvider>);
  fireEvent.click(screen.getByRole("button", { name: language === "fr" ? "Opérations" : "Operations" }));
}

describe("admin operational exercises", () => {
  it("requires an explicit confirmation before starting a bounded exercise", () => {
    renderOperations();
    fireEvent.click(screen.getByRole("button", { name: "Tester l’alerte" }));
    expect(mocks.start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Lancer le test" }));

    expect(mocks.start).toHaveBeenCalledWith(
      { exercise_type: "api_unavailable", duration_seconds: 240 },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("disables triggers when production configuration forbids exercises", () => {
    mocks.state.enabled = false;
    renderOperations();

    expect(screen.getByText("Désactivé par configuration")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tester l’alerte" })).toBeDisabled();
  });

  it("offers early recovery for the active exercise", () => {
    mocks.state.active = {
      id: "exercise-1234",
      exercise_type: "api_unavailable",
      initiated_by: "michael@sicurre.com",
      started_at: "2026-08-06T10:00:00Z",
      expires_at: "2026-08-06T10:04:00Z",
    };
    renderOperations();
    fireEvent.click(screen.getByRole("button", { name: "Arrêter le signal" }));
    expect(mocks.recover).toHaveBeenCalledWith("exercise-1234");
  });

  it("does not report a disabled feature while state is loading", () => {
    mocks.loading = true;
    renderOperations();
    expect(screen.getByRole("status")).toHaveTextContent("Chargement");
    expect(screen.queryByText("Désactivé par configuration")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tester l’alerte" })).not.toBeInTheDocument();
  });

  it("reports query failure separately and offers a retry", () => {
    mocks.error = true;
    renderOperations();
    expect(screen.getByRole("alert")).toHaveTextContent("État du test indisponible");
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(mocks.refetch).toHaveBeenCalledOnce();
    expect(screen.queryByText("Désactivé par configuration")).not.toBeInTheDocument();
  });

  it("cancels confirmation without sending a signal and retains monitoring links", () => {
    renderOperations();
    fireEvent.click(screen.getByRole("button", { name: "Tester l’alerte" }));
    fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
    expect(mocks.start).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Lancer le test" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mesures Grafana" })).toHaveAttribute("href", expect.stringContaining("/d/sicurre-controlled-exercise"));
  });

  it("translates the test controls into English", () => {
    renderOperations("en");
    fireEvent.click(screen.getByRole("button", { name: "Test alert" }));
    expect(screen.getByRole("button", { name: "Start test" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });
});
