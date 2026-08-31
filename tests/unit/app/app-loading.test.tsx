// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../../src/app/App";
import { useActiveDomain } from "../../../src/app/contexts/active-domain";

const state = vi.hoisted(() => ({
  session: {
    data: undefined as undefined | Record<string, unknown>,
    isLoading: true,
    isError: false,
  },
  domains: {
    data: undefined as undefined | { id: string; zone_name: string; status: string }[],
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  },
  publicRender: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../src/app/lib/api", () => ({
  useCurrentSession: () => state.session,
  useCloudflareList: () => state.domains,
  useLogout: () => ({ mutateAsync: vi.fn() }),
  clearStoredSession: vi.fn(),
  seedStoredSession: vi.fn(),
}));
vi.mock("../../../src/app/components/common/app-shell", () => ({
  AppShell: ({ children, onPageChange, administration }: { children: ReactNode; onPageChange: (page: string) => void; administration: boolean }) => (
    <main data-administration={String(administration)}>
      <button onClick={() => onPageChange("dashboard")}>Workspace</button>
      <button onClick={() => onPageChange("logs")}>Admin</button>
      <button onClick={() => onPageChange("settings")}>Settings</button>
      <button onClick={() => onPageChange("support")}>Support</button>
      {children}
    </main>
  ),
}));

function DomainContent() {
  const { activeDomain } = useActiveDomain();
  return <h1>{activeDomain ? `Protected: ${activeDomain}` : "No active domain"}</h1>;
}

vi.mock("../../../src/app/routes/domain-shield", () => ({ default: DomainContent }));
vi.mock("../../../src/app/routes/dashboard", () => ({ default: DomainContent }));
vi.mock("../../../src/app/routes/threats", () => ({ default: DomainContent }));
vi.mock("../../../src/app/routes/quarantine", () => ({ default: DomainContent }));
vi.mock("../../../src/app/routes/alerts", () => ({ default: DomainContent }));
vi.mock("../../../src/app/routes/settings", () => ({ default: () => <h1>Settings page</h1> }));
vi.mock("../../../src/app/routes/support", () => ({ default: () => <h1>Support page</h1> }));
vi.mock("../../../src/app/routes/logs", () => ({ default: () => <h1>Admin console</h1> }));
vi.mock("../../../src/app/routes/login", () => ({ default: ({ onLoginSuccess }: { onLoginSuccess: () => void }) => <button onClick={onLoginSuccess}>Sign in</button> }));
vi.mock("../../../src/app/routes/landing", () => ({ default: ({ onNavigateToLogin }: { onNavigateToLogin: () => void }) => {
  state.publicRender();
  return <><h1>Public page</h1><button onClick={onNavigateToLogin}>Open login</button></>;
} }));

function finishSession() {
  state.session.isLoading = false;
  state.session.isError = false;
  state.session.data = {
    workspace_id: "workspace-1", display_name: "Michael", role: "owner",
    is_platform_admin: false, onboarding_required: false,
  };
}

beforeEach(() => {
  state.session = { data: undefined, isLoading: true, isError: false };
  state.domains = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
  state.publicRender.mockClear();
  window.history.replaceState({}, "", "/app/domain-shield");
});

describe("explicit platform admin access", () => {
  function adminSession(onboarding = false) {
    finishSession();
    state.session.data = { ...state.session.data, is_platform_admin: true, onboarding_required: onboarding };
    state.domains = { ...state.domains, isLoading: false, data: onboarding ? [] : [
      { id: "1", zone_name: "vinse.app", status: "active" },
    ] };
  }

  it.each(["/", "/login", "/app/dashboard", "/app/domain-shield"])("keeps an admin in their workspace at %s", async (path) => {
    window.history.replaceState({}, "", path);
    adminSession();
    render(<App />);
    expect(await screen.findByText("Protected: vinse.app")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("data-administration", "false");
    expect(window.location.pathname).not.toBe("/admin");
  });

  it("onboards administrators who have not connected their workspace", async () => {
    adminSession(true);
    render(<App />);
    expect(await screen.findByText("Settings page")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/app/settings");
  });

  it.each([false, true])("preserves a direct /admin request, including before onboarding (%s)", async (onboarding) => {
    window.history.replaceState({}, "", "/admin");
    adminSession(onboarding);
    render(<App />);
    expect(await screen.findByText("Admin console")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("data-administration", "true");
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));
    expect(await screen.findByText(onboarding ? "Settings page" : "Protected: vinse.app")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("data-administration", "false");
  });

  it.each(["/login", "/admin"])("preserves login intent from %s", async (path) => {
    window.history.replaceState({}, "", path);
    state.session = { data: undefined, isLoading: false, isError: true };
    render(<App />);
    if (path === "/admin") fireEvent.click(await screen.findByRole("button", { name: "Open login" }));
    const signIn = await screen.findByRole("button", { name: "Sign in" });
    adminSession();
    fireEvent.click(signIn);
    expect(await screen.findByText(path === "/admin" ? "Admin console" : "Protected: vinse.app")).toBeInTheDocument();
    expect(window.location.pathname).toBe(path === "/admin" ? "/admin" : "/app/dashboard");
  });

  it("rejects a customer requesting /admin even with a workspace admin role", async () => {
    window.history.replaceState({}, "", "/admin");
    adminSession();
    state.session.data = { ...state.session.data, role: "admin", is_platform_admin: false };
    render(<App />);
    expect(await screen.findByText("Protected: vinse.app")).toBeInTheDocument();
    expect(screen.queryByText("Admin console")).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/app/dashboard");
  });
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
});

describe("authenticated refresh loading", () => {
  it("does not render protected content if session validation fails", async () => {
    state.session = { data: undefined, isLoading: false, isError: true };
    state.domains = { ...state.domains, isLoading: false, data: [
      { id: "1", zone_name: "vinse.app", status: "active" },
    ] };
    render(<App />);
    expect(await screen.findByText("Public page")).toBeInTheDocument();
    expect(screen.queryByText(/Protected:/)).not.toBeInTheDocument();
  });

  it.each(["domain-shield", "dashboard", "threats", "quarantine", "alerts"])(
    "keeps %s pending until owned domains load, without a false empty or public page",
    async (page) => {
      window.history.replaceState({}, "", `/app/${page}`);
      localStorage.setItem("sicurre:active-domain:workspace-1", "foreign.test");
      const { rerender } = render(<App />);
      expect(screen.getByRole("status")).toHaveTextContent("common.loading");
      expect(screen.queryByRole("main")).not.toBeInTheDocument();

      finishSession();
      rerender(<App />);
      expect(await screen.findByRole("status", { name: "common.loading" })).toBeInTheDocument();
      expect(screen.queryByText("No active domain")).not.toBeInTheDocument();
      expect(screen.queryByText(/Protected:/)).not.toBeInTheDocument();
      expect(state.publicRender).not.toHaveBeenCalled();

      state.domains = { ...state.domains, isLoading: false, data: [
        { id: "1", zone_name: "vinse.app", status: "active" },
      ] };
      rerender(<App />);
      expect(await screen.findByText("Protected: vinse.app")).toBeInTheDocument();
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    },
  );

  it("shows the empty state only after a successful empty response", async () => {
    finishSession();
    const { rerender } = render(<App />);
    expect(screen.queryByText("No active domain")).not.toBeInTheDocument();
    state.domains = { ...state.domains, data: [], isLoading: false };
    rerender(<App />);
    expect(await screen.findByText("No active domain")).toBeInTheDocument();
  });

  it("offers retry on domain failure and recovers without an empty-state flash", async () => {
    finishSession();
    state.domains = { ...state.domains, isLoading: false, isError: true };
    const { rerender } = render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("common.domains_load_error");
    expect(screen.queryByText("No active domain")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    expect(state.domains.refetch).toHaveBeenCalledOnce();
    state.domains = { ...state.domains, isError: false, isLoading: true };
    rerender(<App />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    state.domains = { ...state.domains, isLoading: false, data: [
      { id: "1", zone_name: "vinse.app", status: "active" },
    ] };
    rerender(<App />);
    expect(await screen.findByText("Protected: vinse.app")).toBeInTheDocument();
  });

  it.each(["Settings", "Support"])("keeps %s accessible when domains fail", async (label) => {
    finishSession();
    state.domains = { ...state.domains, isLoading: false, isError: true };
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: label }));
    expect(await screen.findByText(`${label} page`)).toBeInTheDocument();
  });

  it("retains existing content while a background refresh fails", async () => {
    finishSession();
    state.domains = { ...state.domains, isLoading: false, isError: true, data: [
      { id: "1", zone_name: "vinse.app", status: "active" },
    ] };
    render(<App />);
    expect(await screen.findByText("Protected: vinse.app")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
