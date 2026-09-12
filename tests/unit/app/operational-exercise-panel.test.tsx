// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OperationalExercisePanel } from "../../../src/app/components/admin/operational-exercise-panel";

const state = vi.hoisted(() => ({
  query: { data: undefined as unknown, isError: false, refetch: vi.fn() },
  start: { mutate: vi.fn(), reset: vi.fn(), isPending: false, error: null as Error | null },
  recover: { mutate: vi.fn(), reset: vi.fn(), isPending: false, error: null as Error | null },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options?.limit ? `${key}:${options.limit}` : key,
    i18n: { language: "fr" },
  }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useOperationalExercises: () => state.query,
  useStartOperationalExercise: () => state.start,
  useRecoverOperationalExercise: () => state.recover,
}));

const idle = {
  enabled: true,
  active: null,
  recent: [],
  supported_types: ["api_unavailable", "high_latency", "elevated_5xx"],
};

beforeEach(() => {
  state.query = { data: idle, isError: false, refetch: vi.fn() };
  state.start = { mutate: vi.fn(), reset: vi.fn(), isPending: false, error: null };
  state.recover = { mutate: vi.fn(), reset: vi.fn(), isPending: false, error: null };
});

afterEach(cleanup);

describe("OperationalExercisePanel", () => {
  it("names the hourly limit when a start was refused for rate limiting", () => {
    state.start.error = new Error("Rate limit exceeded: 10 per 1 hour");
    render(<OperationalExercisePanel />);
    expect(screen.getByRole("alert")).toHaveTextContent("operational_test.rate_limited:10");
  });

  it("keeps the generic sentence for any other failure", () => {
    state.recover.error = new Error("Active operational exercise not found");
    render(<OperationalExercisePanel />);
    expect(screen.getByRole("alert")).toHaveTextContent("operational_test.action_error");
  });

  it("clears a failed action when the confirmation is opened, and again when it is cancelled", () => {
    state.recover.error = new Error("Active operational exercise not found");
    render(<OperationalExercisePanel />);
    fireEvent.click(screen.getByRole("button", { name: /operational_test.start/ }));
    expect(state.start.reset).toHaveBeenCalledTimes(1);
    expect(state.recover.reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /operational_test.launch/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /common.cancel/ }));
    expect(state.start.reset).toHaveBeenCalledTimes(2);
    expect(state.recover.reset).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: /operational_test.start/ })).toBeInTheDocument();
  });

  it("starts the chosen scenario for four minutes from the confirmation", () => {
    render(<OperationalExercisePanel />);
    fireEvent.click(screen.getByRole("button", { name: /operational_test.start/ }));
    fireEvent.click(screen.getByRole("button", { name: /operational_test.launch/ }));
    expect(state.start.mutate).toHaveBeenCalledWith(
      { exercise_type: "api_unavailable", duration_seconds: 240 },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("shows no error when nothing failed", () => {
    render(<OperationalExercisePanel />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
