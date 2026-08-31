// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginRoute from "../../../src/app/routes/login";

const mocks = vi.hoisted(() => ({
  signup: vi.fn(),
  login: vi.fn(),
  resend: vi.fn(),
}));
const translate = (key: string) => key;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  AuthFlowError: class AuthFlowError extends Error {},
  useLogin: () => ({ mutateAsync: mocks.login, isPending: false }),
  useSignup: () => ({ mutateAsync: mocks.signup, isPending: false }),
}));

vi.mock("../../../src/app/lib/auth-client", () => ({
  authBaseURL: "/api/auth",
  authClient: { sendVerificationEmail: mocks.resend },
}));

beforeEach(() => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ turnstile: { enabled: false, siteKey: null } }),
  }));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("signup verification", () => {
  it("shows a verified notice only for a successful callback", () => {
    const { rerender } = render(
      <LoginRoute onLoginSuccess={vi.fn()} emailJustVerified />,
    );
    expect(screen.getByText("login.email_verified_sign_in")).toBeInTheDocument();

    rerender(
      <LoginRoute onLoginSuccess={vi.fn()} emailVerificationError="expired" />,
    );
    expect(screen.getByText("login.verification_expired")).toBeInTheDocument();
    expect(screen.queryByText("login.email_verified_sign_in")).not.toBeInTheDocument();
  });

  it("asks the user to verify email instead of entering the app", async () => {
    mocks.signup.mockResolvedValue({ user: { email: "new@example.test" }, token: null });
    const onLoginSuccess = vi.fn();
    render(<LoginRoute initialMode="signup" onLoginSuccess={onLoginSuccess} />);

    fireEvent.change(screen.getByLabelText("Nom complet"), { target: { value: "Jean Dupont" } });
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "new@example.test" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "secret123" } });

    const submit = screen.getByRole("button", { name: /Créer mon compte/ });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    await waitFor(() => expect(screen.getByText("Vérifiez votre adresse e-mail")).toBeInTheDocument());
    expect(screen.getByText("new@example.test")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Renvoyer le lien" })).toHaveClass(
      "hover:bg-primary!", "hover:text-on-primary", "hover:border-primary",
      "focus-visible:bg-primary", "focus-visible:text-on-primary",
    );
    const returnButton = screen.getByRole("button", { name: "Revenir à la connexion" });
    expect(returnButton.parentElement).toHaveClass("gap-6");
    expect(returnButton).toHaveClass("min-h-11", "focus-visible:outline-primary");
    expect(returnButton.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(onLoginSuccess).not.toHaveBeenCalled();
  });
});
