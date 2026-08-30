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
  AppShell: ({ children, onPageChange }: { children: ReactNode; onPageChange: (page: string) => void }) => (
    <main>
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
vi.mock("../../../src/app/routes/landing", () => ({ default: () => {
  state.publicRender();
  return <h1>Public page</h1>;
} }));

function finishSession() {
  state.session.isLoading = false;
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
