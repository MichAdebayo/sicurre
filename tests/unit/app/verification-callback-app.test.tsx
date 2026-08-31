// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import App from "../../../src/app/App";

vi.hoisted(() => {
  window.history.replaceState({}, "", "/login?verified=1&error=INVALID_TOKEN");
});
const translate = (key: string) => key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { language: "fr" } }),
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

it.each([false, true])("keeps verification errors on login instead of opening a cached workspace (%s)", async (signedIn) => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (signedIn) client.setQueryData(["auth-session"], {
    workspace_id: "existing-workspace", display_name: "Existing user", role: "owner",
    is_platform_admin: false, onboarding_required: false,
  });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  expect(await screen.findByText("login.verification_invalid")).toBeInTheDocument();
  expect(screen.getByText("Connexion à Sicurre")).toBeInTheDocument();
  expect(window.location.pathname).toBe("/login");
  expect(fetch).not.toHaveBeenCalled();
  client.clear();
});
