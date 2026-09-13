// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginRoute from "../../../src/app/routes/login";

const mocks = vi.hoisted(() => ({
  signup: vi.fn(),
  login: vi.fn(),
  resend: vi.fn(),
  loginPending: false,
}));
const translate = (key: string) => key;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  AuthFlowError: class AuthFlowError extends Error {
    reason: string;
    constructor(reason: string, message = reason) {
      super(message);
      this.reason = reason;
    }
  },
  useLogin: () => ({ mutateAsync: mocks.login, isPending: mocks.loginPending, reset: vi.fn() }),
  useSignup: () => ({ mutateAsync: mocks.signup, isPending: false, reset: vi.fn() }),
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

// Helpers shared by the sign-in, sign-up, reset and Turnstile suites below.
import { act, within } from "@testing-library/react";
import { AuthFlowError } from "../../../src/app/lib/api";

const fillLogin = (email = "jean@example.test", password = "secret123") => {
  fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: password } });
};

const fillSignup = (name = "Jean Dupont", email = "jean@example.test", password = "secret123") => {
  fireEvent.change(screen.getByLabelText("Nom complet"), { target: { value: name } });
  fillLogin(email, password);
};

const submitForm = () => screen.getByLabelText("Mot de passe").closest("form") as HTMLFormElement;

const jsonResponse = (body: unknown, ok = true) => ({ ok, json: async () => body });

const turnstileConfig = (enabled: boolean, siteKey: string | null = enabled ? "site-key" : null) =>
  jsonResponse({ turnstile: { enabled, siteKey } });

type RenderedTurnstileOptions = {
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
};

function stubTurnstileApi() {
  const api = {
    render: vi.fn<(container: string, options: Record<string, unknown>) => string>(() => "widget-1"),
    remove: vi.fn(),
    reset: vi.fn(),
  };
  vi.stubGlobal("turnstile", api);
  return api;
}

describe("sign-in form", () => {
  it("rejects an invalid address before calling the API", async () => {
    render(<LoginRoute onLoginSuccess={vi.fn()} />);
    fillLogin("not-an-email");
    // jsdom applies the native email constraint on a button click, so submit the
    // form itself to reach the schema check.
    fireEvent.submit(submitForm());

    expect(await screen.findByText("Adresse email invalide")).toBeInTheDocument();
    expect(mocks.login).not.toHaveBeenCalled();
  });

  it("signs the user in and reports success", async () => {
    mocks.login.mockResolvedValue({});
    const onLoginSuccess = vi.fn();
    render(<LoginRoute onLoginSuccess={onLoginSuccess} />);
    fillLogin();
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/ }));

    await waitFor(() => expect(onLoginSuccess).toHaveBeenCalledTimes(1));
    expect(mocks.login).toHaveBeenCalledWith({ email: "jean@example.test", password: "secret123" });
  });

  it("maps a flow error to its reason and any other failure to the generic key", async () => {
    mocks.login.mockRejectedValueOnce(new AuthFlowError("invalid_password", "bad"));
    const onLoginSuccess = vi.fn();
    render(<LoginRoute onLoginSuccess={onLoginSuccess} />);
    fillLogin();
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/ }));
    expect(await screen.findByText("login.errors.invalid_password")).toBeInTheDocument();

    mocks.login.mockRejectedValueOnce(new Error("network"));
    fireEvent.click(screen.getByRole("button", { name: /Se connecter/ }));
    expect(await screen.findByText("login.errors.login_failed")).toBeInTheDocument();
    expect(onLoginSuccess).not.toHaveBeenCalled();
  });

  it("shows the pending label while the mutation runs", () => {
    mocks.loginPending = true;
    try {
      render(<LoginRoute onLoginSuccess={vi.fn()} />);
      expect(screen.getByRole("button", { name: /Connexion en cours/ })).toBeDisabled();
    } finally {
      mocks.loginPending = false;
    }
  });

  it("toggles password visibility", () => {
    render(<LoginRoute onLoginSuccess={vi.fn()} />);
    const password = screen.getByLabelText("Mot de passe");
    expect(password).toHaveAttribute("type", "password");

    fireEvent.click(screen.getByRole("button", { name: "Afficher le mot de passe" }));
    expect(password).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByRole("button", { name: "Masquer le mot de passe" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("switches between sign-in and sign-up and clears the state", async () => {
    render(<LoginRoute onLoginSuccess={vi.fn()} />);
    fillLogin("not-an-email");
    fireEvent.submit(submitForm());
    expect(await screen.findByText("Adresse email invalide")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "S'inscrire" }));
    expect(screen.getByRole("heading", { name: "Créer un compte" })).toBeInTheDocument();
    expect(screen.queryByText("Adresse email invalide")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Mot de passe")).toHaveValue("");

    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(screen.getByRole("heading", { name: "Connexion à Sicurre" })).toBeInTheDocument();
  });

  it("offers the landing shortcut only when a handler is given", () => {
    const onNavigateToLanding = vi.fn();
    const { rerender } = render(<LoginRoute onLoginSuccess={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Retour à l'accueil" })).not.toBeInTheDocument();

    rerender(<LoginRoute onLoginSuccess={vi.fn()} onNavigateToLanding={onNavigateToLanding} />);
    fireEvent.click(screen.getByRole("button", { name: "Retour à l'accueil" }));
    expect(onNavigateToLanding).toHaveBeenCalledTimes(1);
  });

  it("opens and closes the legal modals in place", async () => {
    render(<LoginRoute onLoginSuccess={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Conditions d'utilisation" }));
    expect(screen.getByRole("heading", { name: "Conditions Générales d'Utilisation" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fermer" }));
    // The overlay leaves through an exit animation, so it lingers for a moment.
    await waitFor(
      () => expect(screen.queryByRole("heading", { name: "Conditions Générales d'Utilisation" })).not.toBeInTheDocument(),
      { timeout: 3000 },
    );

    fireEvent.click(screen.getByRole("button", { name: "Politique de confidentialité" }));
    expect(screen.getByRole("heading", { name: "Politique de Confidentialité" })).toBeInTheDocument();
  });
});

describe("password reset", () => {
  it("asks for a valid address before requesting a reset link", async () => {
    render(<LoginRoute onLoginSuccess={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Mot de passe oublié ?" }));

    expect(await screen.findByText("login.errors.invalid_email")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("request-password-reset"), expect.anything());
  });

  it("requests the link and confirms without revealing whether the account exists", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}) as Response);
    render(<LoginRoute onLoginSuccess={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "jean@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Mot de passe oublié ?" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Si un compte correspond à cette adresse, un lien vient d’être envoyé.",
    );
    expect(fetch).toHaveBeenCalledWith("/api/auth/request-password-reset", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ email: "jean@example.test", redirectTo: `${window.location.origin}/login` }),
    }));
  });

  it("reports an unavailable service when the reset request fails", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, false) as Response);
    render(<LoginRoute onLoginSuccess={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "jean@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Mot de passe oublié ?" }));

    expect(await screen.findByText("login.errors.service_unavailable")).toBeInTheDocument();
  });

  it("sets a new password from the token in the URL", async () => {
    window.history.replaceState({}, "", "/login?token=reset-123");
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}) as Response);
    render(<LoginRoute onLoginSuccess={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Nouveau mot de passe" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Adresse e-mail")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: /Mettre à jour le mot de passe/ }));
    expect(await screen.findByText("Le mot de passe doit comporter au moins 8 caractères.")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("reset-password"), expect.anything());

    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "longenough" } });
    fireEvent.click(screen.getByRole("button", { name: /Mettre à jour le mot de passe/ }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Mot de passe mis à jour. Vous pouvez maintenant vous connecter.",
    );
    expect(fetch).toHaveBeenCalledWith("/api/auth/reset-password", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ newPassword: "longenough", token: "reset-123" }),
    }));
    expect(screen.getByRole("heading", { name: "Connexion à Sicurre" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("");
  });

  it("names an expired reset link", async () => {
    window.history.replaceState({}, "", "/login?token=stale");
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, false) as Response);
    render(<LoginRoute onLoginSuccess={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "longenough" } });
    fireEvent.click(screen.getByRole("button", { name: /Mettre à jour le mot de passe/ }));
    expect(await screen.findByText("Ce lien de réinitialisation est invalide ou a expiré.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nouveau mot de passe" })).toBeInTheDocument();
  });
});

describe("sign-up form", () => {
  it("rejects a name that is too short before calling the API", async () => {
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);
    fillSignup("J");
    const submit = screen.getByRole("button", { name: /Créer mon compte/ });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    expect(await screen.findByText("Le nom doit comporter au moins 2 caractères")).toBeInTheDocument();
    expect(mocks.signup).not.toHaveBeenCalled();
  });

  it("maps a taken address and a generic failure", async () => {
    mocks.signup.mockRejectedValueOnce(new AuthFlowError("email_taken"));
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);
    fillSignup();
    const submit = screen.getByRole("button", { name: /Créer mon compte/ });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    expect(await screen.findByText("login.errors.email_taken")).toBeInTheDocument();

    mocks.signup.mockRejectedValueOnce(new Error("boom"));
    fireEvent.click(submit);
    expect(await screen.findByText("login.errors.signup_failed")).toBeInTheDocument();
    expect(mocks.signup).toHaveBeenCalledWith({
      name: "Jean Dupont", email: "jean@example.test", password: "secret123", turnstileToken: "",
    });
  });

  it("resends the verification link and reports a failure to send", async () => {
    mocks.signup.mockResolvedValue({ user: { email: "new@example.test" }, token: null });
    mocks.resend.mockResolvedValueOnce({ error: null }).mockResolvedValueOnce({ error: { message: "nope" } });
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);
    fillSignup("Jean Dupont", "new@example.test");
    const submit = screen.getByRole("button", { name: /Créer mon compte/ });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    await screen.findByText("Vérifiez votre adresse e-mail");

    fireEvent.click(screen.getByRole("button", { name: "Renvoyer le lien" }));
    expect(await screen.findByText("Un nouveau lien de vérification vient d’être envoyé.")).toBeInTheDocument();
    expect(mocks.resend).toHaveBeenCalledWith({
      email: "new@example.test",
      callbackURL: `${window.location.origin}/login?verified=1`,
    });

    fireEvent.click(screen.getByRole("button", { name: "Renvoyer le lien" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Impossible d’envoyer le lien pour le moment. Réessayez dans quelques instants.",
    );

    fireEvent.click(screen.getByRole("button", { name: "Revenir à la connexion" }));
    expect(screen.getByRole("heading", { name: "Connexion à Sicurre" })).toBeInTheDocument();
  });
});

describe("Turnstile gate", () => {
  it("keeps sign-up blocked until the widget hands over a token, then sends it", async () => {
    vi.mocked(fetch).mockResolvedValue(turnstileConfig(true) as Response);
    const api = stubTurnstileApi();
    mocks.signup.mockResolvedValue({ user: { email: "jean@example.test" }, token: null });
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);

    expect(screen.getByLabelText("Chargement de la vérification anti-robot")).toBeInTheDocument();
    const widget = await screen.findByRole("group", { name: "Vérification anti-robot" });
    expect(widget).toBeInTheDocument();
    await waitFor(() => expect(api.render).toHaveBeenCalledTimes(1));
    expect(api.render).toHaveBeenCalledWith(`#${widget.id}`, expect.objectContaining({ sitekey: "site-key" }));

    fillSignup();
    const submit = screen.getByRole("button", { name: /Créer mon compte/ });
    expect(submit).toBeDisabled();

    const options = api.render.mock.calls[0][1] as RenderedTurnstileOptions;
    act(() => options.callback("turnstile-token"));
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    await waitFor(() => expect(mocks.signup).toHaveBeenCalledWith(
      expect.objectContaining({ turnstileToken: "turnstile-token" }),
    ));
    await screen.findByText("Vérifiez votre adresse e-mail");
  });

  it("clears the token on expiry and names a failed verification", async () => {
    vi.mocked(fetch).mockResolvedValue(turnstileConfig(true) as Response);
    const api = stubTurnstileApi();
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);
    await screen.findByRole("group", { name: "Vérification anti-robot" });
    await waitFor(() => expect(api.render).toHaveBeenCalled());
    fillSignup();

    const options = api.render.mock.calls[0][1] as RenderedTurnstileOptions;
    const submit = screen.getByRole("button", { name: /Créer mon compte/ });
    act(() => options.callback("turnstile-token"));
    expect(submit).toBeEnabled();
    act(() => options["expired-callback"]());
    expect(submit).toBeDisabled();

    act(() => options["error-callback"]());
    expect(screen.getByText("login.errors.bot_verification_failed")).toBeInTheDocument();
  });

  it("resets the widget after a rejected sign-up so the token is not reused", async () => {
    vi.mocked(fetch).mockResolvedValue(turnstileConfig(true) as Response);
    const api = stubTurnstileApi();
    mocks.signup.mockRejectedValue(new AuthFlowError("bot_verification_failed"));
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);
    await screen.findByRole("group", { name: "Vérification anti-robot" });
    await waitFor(() => expect(api.render).toHaveBeenCalled());
    fillSignup();

    const options = api.render.mock.calls[0][1] as RenderedTurnstileOptions;
    act(() => options.callback("turnstile-token"));
    fireEvent.click(screen.getByRole("button", { name: /Créer mon compte/ }));

    expect(await screen.findByText("login.errors.bot_verification_failed")).toBeInTheDocument();
    await waitFor(() => expect(api.reset).toHaveBeenCalledWith("widget-1"));
    expect(screen.getByRole("button", { name: /Créer mon compte/ })).toBeDisabled();
  });

  it("refuses a sign-up submitted without a token even when the button is bypassed", async () => {
    vi.mocked(fetch).mockResolvedValue(turnstileConfig(true) as Response);
    stubTurnstileApi();
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);
    await screen.findByRole("group", { name: "Vérification anti-robot" });
    fillSignup();

    fireEvent.submit(submitForm());
    expect(await screen.findByText("login.errors.bot_verification_required")).toBeInTheDocument();
    expect(mocks.signup).not.toHaveBeenCalled();
  });

  it("blocks sign-up when the anti-robot configuration cannot be read", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, false) as Response);
    render(<LoginRoute initialMode="signup" onLoginSuccess={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("login.errors.bot_verification_unavailable");
    fillSignup();
    expect(screen.getByRole("button", { name: /Créer mon compte/ })).toBeDisabled();
  });

  it("does not fetch the configuration for the sign-in form", () => {
    render(<LoginRoute onLoginSuccess={vi.fn()} />);
    expect(fetch).not.toHaveBeenCalled();
    expect(within(screen.getByRole("main")).queryByRole("group")).not.toBeInTheDocument();
  });
});
