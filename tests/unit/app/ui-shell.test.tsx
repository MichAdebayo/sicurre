// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "../../../src/app/components/common/app-shell";
import { AppToast } from "../../../src/app/components/common/app-toast";
import { Sidebar } from "../../../src/app/components/common/sidebar";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useAdminRuntimeHealth: () => ({ data: undefined }),
  useAlertHistory: () => ({ data: [] }),
  useCloudflareList: () => ({ data: [] }),
  useDomainShieldStatus: () => ({ data: undefined }),
  useQuarantineItems: () => ({ data: [] }),
  useThreatLogs: () => ({ data: [] }),
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("application navigation", () => {
  it("locks customer destinations until Cloudflare onboarding is complete", () => {
    const onPageChange = vi.fn();
    render(
      <Sidebar
        currentPage="settings"
        onPageChange={onPageChange}
        onLogout={vi.fn()}
        onboardingRequired
        userRole="owner"
      />,
    );

    const dashboard = screen.getByRole("button", { name: /sidebar.nav_dashboard/i });
    const settings = screen.getByRole("button", { name: /sidebar.nav_settings/i });
    expect(dashboard).toBeDisabled();
    expect(dashboard).toHaveClass("cursor-not-allowed");
    expect(settings).toBeEnabled();

    fireEvent.click(dashboard);
    fireEvent.click(settings);
    expect(onPageChange).toHaveBeenCalledTimes(1);
    expect(onPageChange).toHaveBeenCalledWith("settings");
  });

  it("shows platform operations without customer mailbox navigation for admins", () => {
    render(
      <Sidebar
        currentPage="logs"
        onPageChange={vi.fn()}
        onLogout={vi.fn()}
        userRole="admin"
      />,
    );

    expect(screen.getByRole("button", { name: /sidebar.nav_admin_console/i })).toBeVisible();
    expect(screen.queryByRole("button", { name: /sidebar.nav_quarantine/i })).not.toBeInTheDocument();
  });

  it("opens mobile navigation and closes it after choosing a page", () => {
    const onPageChange = vi.fn();
    render(
      <AppShell
        currentPage="dashboard"
        onPageChange={onPageChange}
        onLogout={vi.fn()}
      >
        <p>Dashboard content</p>
      </AppShell>,
    );

    fireEvent.click(screen.getByRole("button", { name: "common.open_navigation" }));
    expect(screen.getAllByRole("button", { name: /sidebar.nav_settings/i })).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("button", { name: /sidebar.nav_settings/i })[1]);
    expect(onPageChange).toHaveBeenCalledWith("settings");
    expect(screen.queryByRole("button", { name: "common.close_navigation" })).not.toBeInTheDocument();
  });

  it("closes mobile navigation from both the backdrop and close control", () => {
    render(
      <AppShell currentPage="dashboard" onPageChange={vi.fn()} onLogout={vi.fn()}>
        <p>Dashboard content</p>
      </AppShell>,
    );

    fireEvent.click(screen.getByRole("button", { name: "common.open_navigation" }));
    const closeButtons = screen.getAllByRole("button", { name: "common.close_navigation" });
    fireEvent.click(closeButtons[0]);
    expect(screen.queryByRole("button", { name: "common.close_navigation" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "common.open_navigation" }));
    fireEvent.click(screen.getAllByRole("button", { name: "common.close_navigation" })[1]);
    expect(screen.queryByRole("button", { name: "common.close_navigation" })).not.toBeInTheDocument();
  });

  it("routes the sidebar support command", () => {
    const onPageChange = vi.fn();
    render(
      <Sidebar currentPage="dashboard" onPageChange={onPageChange} onLogout={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /sidebar.nav_support/i }));
    expect(onPageChange).toHaveBeenCalledWith("support");
  });

  it("exposes logout as a direct navigation action", () => {
    const onLogout = vi.fn();
    render(
      <Sidebar currentPage="dashboard" onPageChange={vi.fn()} onLogout={onLogout} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "common.logout" }));
    expect(onLogout).toHaveBeenCalledOnce();
  });
});

describe("application toast", () => {
  it("announces errors and supports explicit dismissal", () => {
    const onClose = vi.fn();
    render(<AppToast tone="error" message="Configuration impossible" onClose={onClose} />);

    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
    fireEvent.click(screen.getByRole("button", { name: "Fermer la notification" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("dismisses transient messages after their configured duration", () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    render(<AppToast tone="success" message="Domaine configuré" onClose={onClose} durationMs={1000} />);

    vi.advanceTimersByTime(999);
    expect(onClose).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onClose).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it("pauses dismissal while the user is reading the message", () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    render(<AppToast tone="error" message="Permission Cloudflare manquante" onClose={onClose} durationMs={1000} />);
    const toast = screen.getByRole("alert");

    fireEvent.mouseEnter(toast);
    vi.advanceTimersByTime(1500);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseLeave(toast);
    vi.advanceTimersByTime(1000);
    expect(onClose).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it("also pauses dismissal for keyboard focus", () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    render(<AppToast tone="info" message="Configuration en cours" onClose={onClose} durationMs={500} />);
    const closeButton = screen.getByRole("button", { name: "Fermer la notification" });

    fireEvent.focus(closeButton);
    vi.advanceTimersByTime(1000);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.blur(closeButton);
    vi.advanceTimersByTime(500);
    expect(onClose).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });
});
