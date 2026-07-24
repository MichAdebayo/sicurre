// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AlertsRoute from "../../../src/app/routes/alerts";

const mocks = vi.hoisted(() => ({
  updatePreferences: vi.fn(),
  retryPreferences: vi.fn(),
  retryRules: vi.fn(),
  retryHistory: vi.fn(),
  queryState: {
    preferencesFailed: false,
    rulesFailed: false,
    historyFailed: false,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useAlertPreferences: () => ({
    data: mocks.queryState.preferencesFailed ? undefined : {
      notify_phishing: true,
      notify_spam: true,
      quiet_hours_enabled: false,
      quiet_hours_start: "22:00",
      quiet_hours_end: "07:00",
      timezone: "Europe/Paris",
    },
    isLoading: false,
    isError: mocks.queryState.preferencesFailed,
    refetch: mocks.retryPreferences,
  }),
  useUpdateAlertPreferences: () => ({ mutateAsync: mocks.updatePreferences }),
  useSecurityRules: () => ({
    data: mocks.queryState.rulesFailed ? undefined : [],
    isLoading: false,
    isError: mocks.queryState.rulesFailed,
    refetch: mocks.retryRules,
  }),
  useCreateSecurityRule: () => ({ mutateAsync: vi.fn() }),
  useDeleteSecurityRule: () => ({ mutateAsync: vi.fn() }),
  useAlertHistory: () => ({
    data: mocks.queryState.historyFailed ? undefined : [],
    isLoading: false,
    isError: mocks.queryState.historyFailed,
    refetch: mocks.retryHistory,
  }),
  useDismissAlert: () => ({ mutateAsync: vi.fn() }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.queryState.preferencesFailed = false;
  mocks.queryState.rulesFailed = false;
  mocks.queryState.historyFailed = false;
});

describe("alerts route", () => {
  it("preserves the loaded spam preference when another preference is saved", async () => {
    mocks.updatePreferences.mockResolvedValue({ status: "saved" });
    render(<AlertsRoute />);

    expect(screen.queryByRole("checkbox", { name: /alerts.notify_spam/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "alerts.save_preferences" }));

    await waitFor(() => expect(mocks.updatePreferences).toHaveBeenCalledOnce());
    expect(mocks.updatePreferences).toHaveBeenCalledWith(expect.objectContaining({
      notify_phishing: true,
      notify_spam: true,
    }));
  });

  it("renders retryable failures instead of empty security states", () => {
    mocks.queryState.preferencesFailed = true;
    mocks.queryState.rulesFailed = true;
    mocks.queryState.historyFailed = true;
    render(<AlertsRoute />);

    expect(screen.getAllByRole("alert")).toHaveLength(3);
    const retryButtons = screen.getAllByRole("button", { name: "common.retry" });
    expect(retryButtons).toHaveLength(3);
    retryButtons.forEach((button) => fireEvent.click(button));
    expect(mocks.retryPreferences).toHaveBeenCalledOnce();
    expect(mocks.retryRules).toHaveBeenCalledOnce();
    expect(mocks.retryHistory).toHaveBeenCalledOnce();
    expect(screen.queryByText("alerts.no_rules")).not.toBeInTheDocument();
    expect(screen.queryByText("alerts.no_history")).not.toBeInTheDocument();
  });
});
