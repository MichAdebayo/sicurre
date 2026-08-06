// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LogsRoute from "../../../src/app/routes/logs";

const mocks = vi.hoisted(() => ({
  start: vi.fn(),
  recover: vi.fn(),
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
  useOperationalExercises: () => ({
    data: { ...mocks.state, recent: [], supported_types: ["api_unavailable", "high_latency", "elevated_5xx"] },
  }),
  useStartOperationalExercise: () => ({ mutate: mocks.start, isPending: false, isError: false, error: null }),
  useRecoverOperationalExercise: () => ({ mutate: mocks.recover, isPending: false, isError: false, error: null }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.state.enabled = true;
  mocks.state.active = null;
});

describe("admin operational exercises", () => {
  it("requires an explicit confirmation before starting a bounded exercise", () => {
    render(<LogsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "Latence élevée" }));
    expect(mocks.start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Lancer le test" }));

    expect(mocks.start).toHaveBeenCalledWith(
      { exercise_type: "high_latency", duration_seconds: 240 },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("disables triggers when production configuration forbids exercises", () => {
    mocks.state.enabled = false;
    render(<LogsRoute />);

    expect(screen.getByText("Désactivé par configuration")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Indisponibilité API" })).toBeDisabled();
  });

  it("offers early recovery for the active exercise", () => {
    mocks.state.active = {
      id: "exercise-1234",
      exercise_type: "api_unavailable",
      initiated_by: "michael@sicurre.com",
      started_at: "2026-08-06T10:00:00Z",
      expires_at: "2026-08-06T10:04:00Z",
    };
    render(<LogsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "Rétablir maintenant" }));
    expect(mocks.recover).toHaveBeenCalledWith("exercise-1234");
  });
});
