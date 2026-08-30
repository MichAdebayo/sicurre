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

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({
    domains: [{ id: "domain-1", zone_name: "vinse.app", status: "active" }],
    activeDomain: "vinse.app",
    activeIntegration: { id: "domain-1", zone_name: "vinse.app", status: "active" },
    setActiveDomain: vi.fn(),
    isLoading: false,
  }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useAdminRuntimeHealth: () => ({ data: undefined }),
  useAlertHistory: () => ({ data: [] }),
  useMarkDomainAlertsRead: () => ({ mutate: vi.fn(), isPending: false }),
  useMarkAlertRead: () => ({ mutate: vi.fn(), isPending: false }),
  useCloudflareList: () => ({ data: [] }),
  useDomainShieldStatus: () => ({ data: undefined }),
  useQuarantineItems: () => ({ data: [] }),
  useThreatLogs: () => ({ data: [] }),
  useKPIStats: () => ({ data: { raw_records_count: 33 } }),
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

  it("keeps page scrolling inside the shell without a horizontal axis", () => {
    const { container } = render(
      <AppShell currentPage="dashboard" onPageChange={vi.fn()} onLogout={vi.fn()}>
        <p>Dashboard content</p>
      </AppShell>,
    );

    expect(container.firstElementChild).toHaveClass("w-full", "overflow-hidden");
    expect(container.querySelector("main.app-readable")).toHaveClass(
      "overflow-x-hidden",
      "overflow-y-auto",
    );
  });

  it("exposes one clear mobile navigation close control", () => {
    render(
      <AppShell currentPage="dashboard" onPageChange={vi.fn()} onLogout={vi.fn()}>
        <p>Dashboard content</p>
      </AppShell>,
    );

    fireEvent.click(screen.getByRole("button", { name: "common.open_navigation" }));
    expect(screen.getAllByRole("button", { name: "common.close_navigation" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "common.close_navigation" }));
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

describe("workspace context in the rail", () => {
  it("reports a protected workspace with its analysed-email count", () => {
    render(
      <Sidebar
        currentPage="dashboard"
        onPageChange={vi.fn()}
        onLogout={vi.fn()}
        userRole="owner"
        workspaceName="vinse.app"
        threatCount={33}
        hasIntegration
      />,
    );

    expect(screen.getAllByText("vinse.app")).toHaveLength(2);
    expect(screen.getByText("sidebar.status_protected")).toBeInTheDocument();
    expect(screen.getByText(/sidebar\.emails_analysed/)).toBeInTheDocument();
  });

  it("reports setup as outstanding while onboarding is incomplete", () => {
    render(
      <Sidebar
        currentPage="settings"
        onPageChange={vi.fn()}
        onLogout={vi.fn()}
        userRole="owner"
        workspaceName="mike-sicurre.com"
        threatCount={0}
        onboardingRequired
      />,
    );

    expect(screen.getByText("sidebar.status_setup_required")).toBeInTheDocument();
    expect(screen.queryByText("sidebar.status_protected")).not.toBeInTheDocument();
  });

  it("omits the workspace card for platform admins, who hold no mailbox", () => {
    render(
      <Sidebar
        currentPage="logs"
        onPageChange={vi.fn()}
        onLogout={vi.fn()}
        userRole="admin"
        workspaceName="sicurre.com"
        threatCount={12}
        hasIntegration
      />,
    );

    expect(screen.queryByText("sicurre.com")).not.toBeInTheDocument();
    expect(screen.queryByText("sidebar.status_protected")).not.toBeInTheDocument();
  });
});

describe("rail collapsing", () => {
  it("keeps every control named once labels are hidden", () => {
    render(
      <Sidebar
        currentPage="settings"
        onPageChange={vi.fn()}
        onLogout={vi.fn()}
        userRole="owner"
        workspaceName="vinse.app"
        threatCount={4}
        hasIntegration
        collapsible
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /sidebar.collapse_rail/i }));

    // Collapsed, the visible text is gone but the accessible name must remain.
    for (const key of [
      "sidebar.nav_dashboard",
      "sidebar.nav_quarantine",
      "sidebar.nav_settings",
      "common.logout",
    ]) {
      expect(screen.getByRole("button", { name: new RegExp(key, "i") })).toBeInTheDocument();
    }
    // The theme control is a switch, and keeps its name collapsed too.
    expect(screen.getByRole("switch", { name: /sidebar.dark_mode/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sidebar.expand_rail/i })).toBeInTheDocument();
  });

  it("remembers the collapsed choice across mounts, and only when collapsible", () => {
    const { unmount } = render(
      <Sidebar
        currentPage="settings"
        onPageChange={vi.fn()}
        onLogout={vi.fn()}
        userRole="owner"
        collapsible
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /sidebar.collapse_rail/i }));
    expect(localStorage.getItem("sicurre_rail_collapsed")).toBe("1");
    unmount();

    render(
      <Sidebar currentPage="settings" onPageChange={vi.fn()} onLogout={vi.fn()} userRole="owner" collapsible />,
    );
    expect(screen.getByRole("button", { name: /sidebar.expand_rail/i })).toBeInTheDocument();
    cleanup();

    // The mobile drawer is a transient overlay, so it never offers the control.
    render(<Sidebar currentPage="settings" onPageChange={vi.fn()} onLogout={vi.fn()} userRole="owner" />);
    expect(screen.queryByRole("button", { name: /sidebar.(collapse|expand)_rail/i })).not.toBeInTheDocument();
  });
});

describe("theme switching from the rail", () => {
  it("toggles the document class and persists the choice", () => {
    render(<Sidebar currentPage="settings" onPageChange={vi.fn()} onLogout={vi.fn()} userRole="owner" />);

    const toggle = screen.getByRole("switch", { name: /sidebar.dark_mode/i });
    expect(toggle).toHaveAttribute("aria-checked", "false");

    fireEvent.click(toggle);
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("sicurre_theme")).toBe("dark");
    expect(toggle).toHaveAttribute("aria-checked", "true");

    fireEvent.click(toggle);
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("sicurre_theme")).toBe("light");
  });

  it("emergency lockdown is offered only when a handler is supplied", () => {
    const onLockdown = vi.fn();
    const { unmount } = render(
      <Sidebar currentPage="settings" onPageChange={vi.fn()} onLogout={vi.fn()} userRole="owner" onLockdown={onLockdown} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /sidebar.lockdown/i }));
    expect(onLockdown).toHaveBeenCalledTimes(1);
    unmount();

    render(<Sidebar currentPage="settings" onPageChange={vi.fn()} onLogout={vi.fn()} userRole="owner" />);
    expect(screen.queryByRole("button", { name: /sidebar.lockdown/i })).not.toBeInTheDocument();
  });
});
