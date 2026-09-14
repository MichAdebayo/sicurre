// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import App from "../../../src/app/App";

const state = vi.hoisted(() => {
  // The tab opens on the redirect the activation link ends with.
  window.history.replaceState({}, "", "/login?verified=1");
  return {
    session: {
      data: undefined as undefined | Record<string, unknown>,
      isLoading: false,
      isError: false,
    },
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));
vi.mock("../../../src/app/lib/api", () => ({
  useCurrentSession: () => state.session,
  useCloudflareList: () => ({
    data: [{ id: "1", zone_name: "sicurre.com", status: "active" }],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useLogout: () => ({ mutateAsync: vi.fn().mockResolvedValue(undefined) }),
  useDiscardSessionCache: () => vi.fn(),
  clearStoredSession: vi.fn(),
  seedStoredSession: vi.fn(),
}));
vi.mock("../../../src/app/components/common/app-shell", () => ({
  AppShell: ({ children, onLogout }: { children: ReactNode; onLogout: () => void }) => (
    <main>
      <button onClick={onLogout}>Sign out</button>
      {children}
    </main>
  ),
}));
vi.mock("../../../src/app/routes/dashboard", () => ({ default: () => <h1>Dashboard</h1> }));
vi.mock("../../../src/app/routes/login", () => ({
  default: ({ onLoginSuccess, emailJustVerified }: { onLoginSuccess: () => void; emailJustVerified?: boolean }) => (
    <>
      <p>{emailJustVerified ? "notice: e-mail confirmé" : "notice: none"}</p>
      <button onClick={onLoginSuccess}>Sign in</button>
    </>
  ),
}));
vi.mock("../../../src/app/routes/landing", () => ({
  default: ({ onNavigateToLogin }: { onNavigateToLogin: () => void }) => (
    <button onClick={onNavigateToLogin}>Open login</button>
  ),
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
});

it("shows the activation notice once, not again after signing in and out in the same tab", async () => {
  const { rerender } = render(<App />);
  expect(await screen.findByText("notice: e-mail confirmé")).toBeInTheDocument();

  state.session.data = {
    workspace_id: "workspace-1",
    display_name: "Michael",
    role: "owner",
    is_platform_admin: false,
    onboarding_required: false,
  };
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  rerender(<App />);
  expect(await screen.findByText("Dashboard")).toBeInTheDocument();

  state.session.data = undefined;
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  rerender(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Open login" }));

  expect(await screen.findByText("notice: none")).toBeInTheDocument();
  expect(screen.queryByText("notice: e-mail confirmé")).not.toBeInTheDocument();
});
