// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AlertsRoute from "../../../src/app/routes/alerts";
import type { AlertHistoryItem, AlertPreferences, SecurityRule } from "../../../src/app/lib/api";

const mocks = vi.hoisted(() => ({
  updatePreferences: vi.fn(),
  createRule: vi.fn(),
  deleteRule: vi.fn(),
  dismissAlert: vi.fn(),
  markRead: vi.fn(),
  retryPreferences: vi.fn(),
  retryRules: vi.fn(),
  retryHistory: vi.fn(),
  queryState: {
    preferencesFailed: false,
    rulesFailed: false,
    historyFailed: false,
    preferencesLoading: false,
    rulesLoading: false,
    historyLoading: false,
    preferences: undefined as unknown,
    rules: [] as unknown,
    history: [] as unknown,
    markReadPending: false,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({ activeDomain: "vinse.app" }),
}));

const defaultPreferences: AlertPreferences = {
  domain: "vinse.app",
  email_enabled: true,
  notify_phishing: true,
  notify_domain_shield: true,
  quiet_hours_enabled: false,
  quiet_hours_start: "22:00",
  quiet_hours_end: "07:00",
  timezone: "Europe/Paris",
};

vi.mock("../../../src/app/lib/api", () => ({
  useAlertPreferences: () => ({
    data: mocks.queryState.preferencesFailed || mocks.queryState.preferencesLoading
      ? undefined
      : (mocks.queryState.preferences ?? defaultPreferences),
    isLoading: mocks.queryState.preferencesLoading,
    isError: mocks.queryState.preferencesFailed,
    refetch: mocks.retryPreferences,
  }),
  useUpdateAlertPreferences: () => ({ mutateAsync: mocks.updatePreferences, isPending: false, reset: vi.fn() }),
  useSecurityRules: () => ({
    data: mocks.queryState.rulesFailed || mocks.queryState.rulesLoading ? undefined : mocks.queryState.rules,
    isLoading: mocks.queryState.rulesLoading,
    isError: mocks.queryState.rulesFailed,
    refetch: mocks.retryRules,
  }),
  useCreateSecurityRule: () => ({ mutateAsync: mocks.createRule, isPending: false, reset: vi.fn() }),
  useDeleteSecurityRule: () => ({ mutateAsync: mocks.deleteRule, isPending: false, reset: vi.fn() }),
  useAlertHistory: () => ({
    data: mocks.queryState.historyFailed || mocks.queryState.historyLoading ? undefined : mocks.queryState.history,
    isLoading: mocks.queryState.historyLoading,
    isError: mocks.queryState.historyFailed,
    refetch: mocks.retryHistory,
  }),
  useDismissAlert: () => ({ mutateAsync: mocks.dismissAlert, isPending: false, reset: vi.fn() }),
  useMarkDomainAlertsRead: () => ({ mutate: mocks.markRead, isPending: mocks.queryState.markReadPending, reset: vi.fn() }),
}));

const historyItem = (overrides: Partial<AlertHistoryItem> = {}): AlertHistoryItem => ({
  id: "h-1",
  domain: "vinse.app",
  event_type: "phishing",
  action_page: null,
  title: "Menace bloquée",
  message: "Un message a été mis en quarantaine.",
  created_at: "2026-09-01T08:30:00.000Z",
  is_read: true,
  ...overrides,
});

const rule = (overrides: Partial<SecurityRule> = {}): SecurityRule => ({
  id: "r-1",
  domain: "vinse.app",
  rule_type: "whitelist",
  pattern: "partenaire.test",
  created_at: "2026-09-01T08:30:00.000Z",
  ...overrides,
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.queryState.preferencesFailed = false;
  mocks.queryState.rulesFailed = false;
  mocks.queryState.historyFailed = false;
  mocks.queryState.preferencesLoading = false;
  mocks.queryState.rulesLoading = false;
  mocks.queryState.historyLoading = false;
  mocks.queryState.preferences = undefined;
  mocks.queryState.rules = [];
  mocks.queryState.history = [];
  mocks.queryState.markReadPending = false;
});

describe("alerts route", () => {
  it("preserves the loaded per-domain preferences when saving", async () => {
    mocks.updatePreferences.mockResolvedValue({ status: "saved" });
    render(<AlertsRoute mode="settings" />);

    expect(screen.getByRole("switch", { name: /alerts.email_enabled/i })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "alerts.save_preferences" }));

    await waitFor(() => expect(mocks.updatePreferences).toHaveBeenCalledOnce());
    expect(mocks.updatePreferences).toHaveBeenCalledWith(expect.objectContaining({
      notify_phishing: true,
      notify_domain_shield: true,
      email_enabled: true,
    }));
  });

  it("renders retryable failures instead of empty security states", () => {
    mocks.queryState.preferencesFailed = true;
    mocks.queryState.rulesFailed = true;
    mocks.queryState.historyFailed = true;
    const { rerender } = render(<AlertsRoute />);

    expect(screen.getAllByRole("alert")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    expect(mocks.retryHistory).toHaveBeenCalledOnce();

    rerender(<AlertsRoute mode="settings" />);
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    screen.getAllByRole("button", { name: "common.retry" }).forEach((button) => fireEvent.click(button));
    expect(mocks.retryPreferences).toHaveBeenCalledOnce();
    expect(mocks.retryRules).toHaveBeenCalledOnce();
    expect(screen.queryByText("alerts.no_rules")).not.toBeInTheDocument();
    expect(screen.queryByText("alerts.no_history")).not.toBeInTheDocument();
  });
});

describe("alert history", () => {
  it("shows the page header and the loading skeleton while the history loads", () => {
    mocks.queryState.historyLoading = true;
    render(<AlertsRoute />);

    expect(screen.getByRole("heading", { name: "alerts.title" })).toBeInTheDocument();
    expect(screen.getByText("alerts.subtitle")).toBeInTheDocument();
    expect(screen.queryByText("alerts.no_history")).not.toBeInTheDocument();
    expect(mocks.markRead).not.toHaveBeenCalled();
  });

  it("shows the empty state when there is no history and never marks anything read", () => {
    render(<AlertsRoute />);

    expect(screen.getByText("alerts.no_history")).toBeInTheDocument();
    expect(mocks.markRead).not.toHaveBeenCalled();
  });

  it("lists every alert with its tone and marks unread alerts as read on open", () => {
    mocks.queryState.history = [
      historyItem({ id: "h-1", title: "Échec de synchronisation", message: "Le DNS a refusé", is_read: false }),
      historyItem({ id: "h-2", title: "Rapport DMARC", message: "Nouveau rapport" }),
      historyItem({ id: "h-3", title: "Règle appliquée", message: "La liste blanche est active" }),
      historyItem({ id: "h-4", title: "Information", message: "Rien à signaler" }),
    ];
    render(<AlertsRoute />);

    expect(screen.getByText("Échec de synchronisation")).toBeInTheDocument();
    expect(screen.getByText("Rapport DMARC")).toBeInTheDocument();
    expect(screen.getByText("Règle appliquée")).toBeInTheDocument();
    expect(screen.getByText("Information")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "alerts.dismiss_alert" })).toHaveLength(4);
    expect(mocks.markRead).toHaveBeenCalled();
  });

  it("does not mark alerts read while a mark-read call is already pending", () => {
    mocks.queryState.history = [historyItem({ is_read: false })];
    mocks.queryState.markReadPending = true;
    render(<AlertsRoute />);

    expect(mocks.markRead).not.toHaveBeenCalled();
  });

  it("does not mark alerts read in settings mode", () => {
    mocks.queryState.history = [historyItem({ is_read: false })];
    render(<AlertsRoute mode="settings" />);

    expect(screen.queryByRole("heading", { name: "alerts.title" })).not.toBeInTheDocument();
    expect(mocks.markRead).not.toHaveBeenCalled();
  });

  it("dismisses an alert from its row", async () => {
    mocks.dismissAlert.mockResolvedValue({ status: "dismissed" });
    mocks.queryState.history = [historyItem({ id: "h-7" })];
    render(<AlertsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "alerts.dismiss_alert" }));

    await waitFor(() => expect(mocks.dismissAlert).toHaveBeenCalledWith("h-7"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("surfaces the server message when dismissing fails", async () => {
    mocks.dismissAlert.mockRejectedValue(new Error("Notification introuvable"));
    mocks.queryState.history = [historyItem()];
    render(<AlertsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "alerts.dismiss_alert" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Notification introuvable");
  });

  it("falls back to the French dismissal message when the rejection is not an Error", async () => {
    mocks.dismissAlert.mockRejectedValue("nope");
    mocks.queryState.history = [historyItem()];
    render(<AlertsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "alerts.dismiss_alert" }));

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Impossible de masquer la notification.");
    fireEvent.click(within(toast).getByRole("button", { name: "Fermer la notification" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
});

describe("alert preferences form", () => {
  it("shows the preferences skeleton while they load", () => {
    mocks.queryState.preferencesLoading = true;
    render(<AlertsRoute mode="settings" />);

    expect(screen.getByText("alerts.preferences_for_domain")).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: /alerts.email_enabled/i })).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /alerts.quiet_hours_enabled/i })).toBeInTheDocument();
  });

  it("disables the per-event toggles and quiet hours when email is switched off", () => {
    render(<AlertsRoute mode="settings" />);

    const email = screen.getByRole("switch", { name: /alerts.email_enabled/i });
    const phishing = screen.getByRole("switch", { name: /alerts.notify_phishing/i });
    const shield = screen.getByRole("switch", { name: /alerts.notify_domain_shield/i });
    const quiet = screen.getByRole("switch", { name: /alerts.quiet_hours_enabled/i });
    expect(phishing).toBeEnabled();

    fireEvent.click(email);
    expect(email).not.toBeChecked();
    expect(phishing).toBeDisabled();
    expect(shield).toBeDisabled();
    expect(quiet).toBeDisabled();

    fireEvent.click(email);
    fireEvent.click(phishing);
    fireEvent.click(shield);
    expect(phishing).not.toBeChecked();
    expect(shield).not.toBeChecked();
  });

  it("reveals the quiet hours inputs and saves the edited window", async () => {
    mocks.updatePreferences.mockResolvedValue({ status: "saved" });
    render(<AlertsRoute mode="settings" />);

    expect(screen.queryByText("alerts.quiet_hours_start")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: /alerts.quiet_hours_enabled/i }));

    const start = screen.getByText("alerts.quiet_hours_start").parentElement!.querySelector("input")!;
    const end = screen.getByText("alerts.quiet_hours_end").parentElement!.querySelector("input")!;
    expect(start).toHaveValue("22:00");
    expect(end).toHaveValue("07:00");
    fireEvent.change(start, { target: { value: "21:30" } });
    fireEvent.change(end, { target: { value: "06:45" } });

    fireEvent.click(screen.getByRole("button", { name: "alerts.save_preferences" }));

    await waitFor(() => expect(mocks.updatePreferences).toHaveBeenCalledWith(expect.objectContaining({
      quiet_hours_enabled: true,
      quiet_hours_start: "21:30",
      quiet_hours_end: "06:45",
      timezone: expect.any(String),
    })));
    expect(await screen.findByRole("status")).toHaveTextContent("alerts.preferences_saved");
  });

  it("loads a quiet-hours window that is already enabled", () => {
    mocks.queryState.preferences = { ...defaultPreferences, quiet_hours_enabled: true, quiet_hours_start: "20:00", quiet_hours_end: "08:00" };
    render(<AlertsRoute mode="settings" />);

    expect(screen.getByRole("switch", { name: /alerts.quiet_hours_enabled/i })).toBeChecked();
    expect(screen.getByText("alerts.quiet_hours_start").parentElement!.querySelector("input")).toHaveValue("20:00");
  });

  it("surfaces the server message when saving fails", async () => {
    mocks.updatePreferences.mockRejectedValue(new Error("Fuseau horaire invalide"));
    render(<AlertsRoute mode="settings" />);

    fireEvent.click(screen.getByRole("button", { name: "alerts.save_preferences" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Fuseau horaire invalide");
  });

  it("falls back to a generic message when the save rejection is not an Error", async () => {
    mocks.updatePreferences.mockRejectedValue("nope");
    render(<AlertsRoute mode="settings" />);

    fireEvent.click(screen.getByRole("button", { name: "alerts.save_preferences" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to save preferences.");
  });
});

describe("security rules", () => {
  const patternInput = () => screen.getByPlaceholderText("alerts.pattern_placeholder");
  const submitRule = () => fireEvent.submit(patternInput().closest("form")!);

  it("shows the rules skeleton while they load", () => {
    mocks.queryState.rulesLoading = true;
    render(<AlertsRoute mode="settings" />);

    expect(screen.getByText("alerts.section_rules")).toBeInTheDocument();
    expect(screen.queryByText("alerts.no_rules")).not.toBeInTheDocument();
  });

  it("shows the empty rules state", () => {
    render(<AlertsRoute mode="settings" />);

    expect(screen.getByText("alerts.no_rules")).toBeInTheDocument();
  });

  it("refuses an empty pattern before calling the API", async () => {
    render(<AlertsRoute mode="settings" />);

    fireEvent.change(patternInput(), { target: { value: "   " } });
    submitRule();

    expect(await screen.findByRole("alert")).toHaveTextContent("Please enter a valid email or domain pattern.");
    expect(mocks.createRule).not.toHaveBeenCalled();
  });

  it("creates a blocklist rule with the trimmed pattern and clears the input", async () => {
    mocks.createRule.mockResolvedValue(rule());
    render(<AlertsRoute mode="settings" />);

    fireEvent.change(screen.getByDisplayValue("alerts.whitelist"), { target: { value: "blocklist" } });
    fireEvent.change(patternInput(), { target: { value: "  spam.test  " } });
    submitRule();

    await waitFor(() => expect(mocks.createRule).toHaveBeenCalledWith({ rule_type: "blocklist", pattern: "spam.test" }));
    await waitFor(() => expect(patternInput()).toHaveValue(""));
  });

  it("surfaces the server message when creating a rule fails", async () => {
    mocks.createRule.mockRejectedValue(new Error("Règle en double"));
    render(<AlertsRoute mode="settings" />);

    fireEvent.change(patternInput(), { target: { value: "dup.test" } });
    submitRule();

    expect(await screen.findByRole("alert")).toHaveTextContent("Règle en double");
    expect(patternInput()).toHaveValue("dup.test");
  });

  it("falls back to a generic message when the create rejection is not an Error", async () => {
    mocks.createRule.mockRejectedValue("nope");
    render(<AlertsRoute mode="settings" />);

    fireEvent.change(patternInput(), { target: { value: "dup.test" } });
    submitRule();

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to create rule.");
  });

  it("lists whitelist and blocklist rules with their labels", () => {
    mocks.queryState.rules = [
      rule({ id: "r-1", rule_type: "whitelist", pattern: "partenaire.test" }),
      rule({ id: "r-2", rule_type: "blocklist", pattern: "spam.test" }),
    ];
    render(<AlertsRoute mode="settings" />);

    expect(screen.getByText("alerts.allow")).toBeInTheDocument();
    expect(screen.getByText("alerts.block")).toBeInTheDocument();
    expect(screen.getByText("alerts.whitelist_desc")).toBeInTheDocument();
    expect(screen.getByText("alerts.blocklist_desc")).toBeInTheDocument();
    expect(screen.getByText("partenaire.test")).toBeInTheDocument();
    expect(screen.getByText("spam.test")).toBeInTheDocument();
  });

  it("asks for confirmation before deleting a rule and cancels cleanly", () => {
    mocks.queryState.rules = [rule()];
    render(<AlertsRoute mode="settings" />);

    const row = screen.getByText("partenaire.test").closest("div")!.parentElement!.parentElement!;
    fireEvent.click(within(row).getByRole("button"));

    expect(screen.getByText("alerts.confirm_delete")).toBeInTheDocument();
    expect(screen.getByText("alerts.confirm_delete_desc")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));

    expect(screen.queryByText("alerts.confirm_delete")).not.toBeInTheDocument();
    expect(mocks.deleteRule).not.toHaveBeenCalled();
  });

  it("deletes the rule after confirmation and refetches the list", async () => {
    mocks.deleteRule.mockResolvedValue({ status: "deleted" });
    mocks.queryState.rules = [rule({ id: "r-9" })];
    render(<AlertsRoute mode="settings" />);

    const row = screen.getByText("partenaire.test").closest("div")!.parentElement!.parentElement!;
    fireEvent.click(within(row).getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "alerts.delete" }));

    await waitFor(() => expect(mocks.deleteRule).toHaveBeenCalledWith("r-9"));
    await waitFor(() => expect(mocks.retryRules).toHaveBeenCalledOnce());
    expect(screen.queryByText("alerts.confirm_delete")).not.toBeInTheDocument();
  });

  it("surfaces the server message when the deletion fails", async () => {
    mocks.deleteRule.mockRejectedValue(new Error("Règle protégée"));
    mocks.queryState.rules = [rule()];
    render(<AlertsRoute mode="settings" />);

    const row = screen.getByText("partenaire.test").closest("div")!.parentElement!.parentElement!;
    fireEvent.click(within(row).getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "alerts.delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Règle protégée");
    expect(mocks.retryRules).not.toHaveBeenCalled();
  });

  it("falls back to the French deletion message when the rejection is not an Error", async () => {
    mocks.deleteRule.mockRejectedValue("nope");
    mocks.queryState.rules = [rule()];
    render(<AlertsRoute mode="settings" />);

    const row = screen.getByText("partenaire.test").closest("div")!.parentElement!.parentElement!;
    fireEvent.click(within(row).getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "alerts.delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de supprimer la règle.");
  });
});
