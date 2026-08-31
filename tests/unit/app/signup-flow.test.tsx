// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../../src/app/App";
import { verifyEmailFromLink } from "../../../src/app/lib/email-verification";

vi.mock("../../../src/app/lib/email-verification", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../../src/app/lib/email-verification")>(),
  verifyEmailFromLink: vi.fn(),
}));

const auth = vi.hoisted(() => ({ signup: vi.fn(), resend: vi.fn() }));
let translate = (key: string) => key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { language: "fr" } }),
}));
vi.mock("../../../src/app/lib/auth-client", () => ({
  authBaseURL: "/api/auth",
  authClient: { signUp: { email: auth.signup }, sendVerificationEmail: auth.resend },
}));

let client: QueryClient;
let sessionRequests: number;
let finishSessionCheck: (() => void) | undefined;
let holdSessionCheck: boolean;

beforeEach(() => {
  translate = (key: string) => key;
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  sessionRequests = 0;
  holdSessionCheck = false;
  finishSessionCheck = undefined;
  auth.signup.mockResolvedValue({ data: { user: { email: "new@example.test", emailVerified: false }, token: null } });
  auth.resend.mockResolvedValue({ data: { status: true } });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url === "/api/auth/config") return new Response(JSON.stringify({ turnstile: { enabled: false } }));
    if (url === "/v1/auth/session") {
      sessionRequests++;
      if (holdSessionCheck) await new Promise<void>((resolve) => { finishSessionCheck = resolve; });
      return new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 });
    }
    throw new Error(`Unexpected request: ${url}`);
  }));
});

afterEach(() => {
  finishSessionCheck?.();
  cleanup();
  client.clear();
  localStorage.clear();
  sessionStorage.clear();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("signup through the real application session boundary", () => {
  it.each([false, true])("opens verification without a session lookup, even with a cached login (%s)", async (signedIn) => {
    if (signedIn) client.setQueryData(["auth-session"], {
      workspace_id: "existing-workspace", display_name: "Existing user", role: "owner",
      is_platform_admin: false, onboarding_required: false,
    });
    window.history.replaceState({}, "", "/verify-email#token=test-verification-token");
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
    await waitFor(() => expect(verifyEmailFromLink).toHaveBeenCalledExactlyOnceWith(
      "test-verification-token", window.location.origin, "/api/auth",
    ));
    expect(screen.getByRole("status")).toHaveTextContent("verify_email.verifying");
    expect(sessionRequests).toBe(0);
    expect(window.location.pathname).toBe("/verify-email");
    expect(auth.signup).not.toHaveBeenCalled();
  });

  it.each(["/signup", "/login"])("keeps confirmation after signup from %s and a background 401", async (path) => {
    window.history.replaceState({}, "", path);
    const { rerender } = render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
    if (path === "/login") fireEvent.click(await screen.findByRole("button", { name: "S'inscrire", exact: true }));
    fireEvent.change(await screen.findByLabelText("Nom complet"), { target: { value: "Jean Dupont" } });
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "new@example.test" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "secret123" } });
    const submit = screen.getByRole("button", { name: /Créer mon compte/ });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    expect(await screen.findByText("Vérifiez votre adresse e-mail")).toBeInTheDocument();
    expect(sessionRequests).toBe(1);
    expect(client.getQueryData(["auth-session"])).toBeUndefined();
    expect(localStorage.getItem("sicurre_auth_provider")).toBeNull();

    // i18n can replace its translator without changing the signup step.
    translate = (key: string) => key;
    rerender(<QueryClientProvider client={client}><App /></QueryClientProvider>);
    expect(screen.getByText("Vérifiez votre adresse e-mail")).toBeInTheDocument();

    holdSessionCheck = true;
    let recheck: Promise<void>;
    act(() => { recheck = client.invalidateQueries({ queryKey: ["auth-session"] }); });
    await waitFor(() => expect(finishSessionCheck).toBeDefined());
    expect(screen.getByText("Vérifiez votre adresse e-mail")).toBeInTheDocument();
    await act(async () => { finishSessionCheck!(); await recheck!; });
    expect(screen.getByText("new@example.test")).toBeInTheDocument();
    expect(screen.getByText("Vérifiez votre adresse e-mail")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Renvoyer le lien" }));
    await waitFor(() => expect(auth.resend).toHaveBeenCalledWith(expect.objectContaining({ email: "new@example.test" })));
    fireEvent.click(screen.getByRole("button", { name: "Revenir à la connexion" }));
    expect(await screen.findByText("Connexion à Sicurre")).toBeInTheDocument();
  });
});
