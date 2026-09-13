// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TopBar } from "../../../src/app/components/common/top-bar";
import type { AlertHistoryItem } from "../../../src/app/lib/api";

const state = vi.hoisted(() => ({
  language: "fr",
  activeDomain: "vinse.app",
  alerts: [] as unknown[],
  alertHistoryDomain: "",
  markAlertRead: vi.fn(),
  markAllRead: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "count" in options ? `${key}:${options.count}` : key,
    i18n: { language: state.language },
  }),
}));

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({ activeDomain: state.activeDomain }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useAlertHistory: (domain: string) => {
    state.alertHistoryDomain = domain;
    return { data: state.alerts };
  },
  useMarkAlertRead: () => ({ mutate: state.markAlertRead, isPending: false, reset: vi.fn() }),
  useMarkDomainAlertsRead: () => ({ mutate: state.markAllRead, isPending: false, reset: vi.fn() }),
}));

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

const alert = (overrides: Partial<AlertHistoryItem> = {}): AlertHistoryItem => ({
  id: "a-1",
  title: "Enregistrement SPF absent",
  message: "Le domaine n'a pas de SPF.",
  event_type: "domain_shield",
  action_page: "domain-shield",
  created_at: minutesAgo(5),
  is_read: false,
  ...overrides,
} as AlertHistoryItem);

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "topbar.open_notifications" }));
  return screen.getByRole("region", { name: "topbar.notifications" });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  state.language = "fr";
  state.activeDomain = "vinse.app";
  state.alerts = [];
});

describe("TopBar notifications menu", () => {
  it("opens the menu, lists the recent alerts and marks unread items", () => {
    state.alerts = [
      alert(),
      alert({ id: "a-2", title: "Rapport hebdomadaire", event_type: "system", action_page: undefined, is_read: true }),
    ];
    render(<TopBar />);

    const bell = screen.getByRole("button", { name: "topbar.open_notifications" });
    expect(bell).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    const region = openMenu();
    expect(bell).toHaveAttribute("aria-expanded", "true");
    expect(within(region).getByText("topbar.unread:1")).toBeInTheDocument();
    expect(within(region).getByText("Enregistrement SPF absent")).toBeInTheDocument();
    expect(within(region).getByText("Rapport hebdomadaire")).toBeInTheDocument();
    expect(within(region).getAllByText("topbar.unread_item")).toHaveLength(1);
    expect(within(region).getAllByText("topbar.minutes_ago:5")).toHaveLength(2);
    expect(state.alertHistoryDomain).toBe("vinse.app");
  });

  it("closes the menu with the bell, with Escape and with a click outside", () => {
    render(<TopBar />);

    openMenu();
    fireEvent.click(screen.getByRole("button", { name: "topbar.open_notifications" }));
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    openMenu();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    const region = openMenu();
    fireEvent.keyDown(window, { key: "Enter" });
    expect(screen.getByRole("region")).toBeInTheDocument();
    fireEvent.click(region);
    expect(screen.getByRole("region")).toBeInTheDocument();
    fireEvent.click(document.body);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("marks one alert read and navigates to its page when clicked", () => {
    state.alerts = [alert()];
    const onPageChange = vi.fn();
    render(<TopBar onPageChange={onPageChange} />);

    const region = openMenu();
    fireEvent.click(within(region).getByRole("button", { name: /Enregistrement SPF absent/ }));

    expect(state.markAlertRead).toHaveBeenCalledWith("a-1");
    expect(onPageChange).toHaveBeenCalledWith("domain-shield");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("marks every alert read from the header action and keeps the menu open", () => {
    state.alerts = [alert()];
    render(<TopBar />);

    const region = openMenu();
    fireEvent.click(within(region).getByRole("button", { name: "topbar.mark_all_read" }));

    expect(state.markAllRead).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("region")).toBeInTheDocument();
  });

  it("shows the empty state and the link to all alerts when nothing is pending", () => {
    const onPageChange = vi.fn();
    render(<TopBar onPageChange={onPageChange} />);

    const bell = screen.getByRole("button", { name: "topbar.open_notifications" });
    expect(bell.querySelector(".bg-error")).toBeNull();

    const region = openMenu();
    expect(within(region).getByText("topbar.no_active_alerts")).toBeInTheDocument();
    expect(within(region).queryByText(/topbar.unread:/)).not.toBeInTheDocument();
    fireEvent.click(within(region).getByRole("button", { name: "topbar.view_all_alerts" }));
    expect(onPageChange).toHaveBeenCalledWith("alerts");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("caps the list at four entries", () => {
    state.alerts = [1, 2, 3, 4, 5, 6].map((n) => alert({ id: `a-${n}`, title: `Alerte ${n}` }));
    render(<TopBar />);

    const region = openMenu();
    expect(within(region).getAllByText(/^Alerte \d$/)).toHaveLength(4);
    expect(within(region).queryByText("Alerte 5")).not.toBeInTheDocument();
    expect(within(region).getByText("topbar.unread:4")).toBeInTheDocument();
  });

  it("replaces the alerts with the Cloudflare onboarding prompt while setup is required", () => {
    state.alerts = [alert()];
    const onPageChange = vi.fn();
    render(<TopBar onboardingRequired onPageChange={onPageChange} />);

    const region = openMenu();
    expect(within(region).getByText("topbar.connect_cloudflare")).toBeInTheDocument();
    expect(within(region).queryByText("Enregistrement SPF absent")).not.toBeInTheDocument();
    expect(within(region).getByText("topbar.now")).toBeInTheDocument();

    fireEvent.click(within(region).getByRole("button", { name: /topbar.connect_cloudflare/ }));
    expect(state.markAlertRead).not.toHaveBeenCalled();
    expect(onPageChange).toHaveBeenCalledWith("settings");

    openMenu();
    fireEvent.click(screen.getByRole("button", { name: "topbar.open_setup" }));
    expect(onPageChange).toHaveBeenLastCalledWith("settings");
  });

  it("keeps an item without a target page inert for navigation", () => {
    state.alerts = [alert({ action_page: undefined })];
    const onPageChange = vi.fn();
    render(<TopBar onPageChange={onPageChange} />);

    const region = openMenu();
    fireEvent.click(within(region).getByRole("button", { name: /Enregistrement SPF absent/ }));
    expect(state.markAlertRead).toHaveBeenCalledWith("a-1");
    expect(onPageChange).not.toHaveBeenCalled();
  });

  it("hides the bell and names the console in administration mode", () => {
    state.alerts = [alert()];
    render(<TopBar administration onboardingRequired />);

    expect(screen.getByText("topbar.console_name")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "topbar.open_notifications" })).not.toBeInTheDocument();
    expect(state.alertHistoryDomain).toBe("");
  });

  it("falls back to the no-domain label when the workspace has none", () => {
    state.activeDomain = "";
    render(<TopBar />);
    expect(screen.getByText("sidebar.no_domain")).toBeInTheDocument();
  });
});

describe("TopBar relative time", () => {
  const renderWithTime = (created_at: string, id = "t-1") => {
    state.alerts = [alert({ id, created_at })];
    render(<TopBar />);
    return openMenu();
  };

  it("labels a missing, invalid or future date as now", () => {
    const region = renderWithTime("");
    expect(within(region).getByText("topbar.now")).toBeInTheDocument();
    cleanup();

    const future = renderWithTime(new Date(Date.now() + 120_000).toISOString());
    expect(within(future).getByText("topbar.now")).toBeInTheDocument();
    cleanup();

    const invalid = renderWithTime("not-a-date");
    expect(within(invalid).getByText("topbar.now")).toBeInTheDocument();
  });

  it("scales from seconds to minutes to hours", () => {
    const seconds = renderWithTime(new Date(Date.now() - 20_000).toISOString());
    expect(within(seconds).getByText("topbar.less_than_minute")).toBeInTheDocument();
    cleanup();

    const minutes = renderWithTime(minutesAgo(42));
    expect(within(minutes).getByText("topbar.minutes_ago:42")).toBeInTheDocument();
    cleanup();

    const hours = renderWithTime(minutesAgo(3 * 60 + 10));
    expect(within(hours).getByText("topbar.hours_ago:3")).toBeInTheDocument();
  });

  it("prints a locale date past one day, following the interface language", () => {
    const stamp = new Date(Date.now() - 2 * 24 * 60 * 60_000);

    const french = renderWithTime(stamp.toISOString());
    expect(within(french).getByText(stamp.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }))).toBeInTheDocument();
    cleanup();

    state.language = "en";
    const english = renderWithTime(stamp.toISOString());
    expect(within(english).getByText(stamp.toLocaleDateString("en-US", { day: "numeric", month: "short" }))).toBeInTheDocument();
  });
});
