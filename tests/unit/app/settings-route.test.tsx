// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SettingsRoute from "../../../src/app/routes/settings";
import type { AuthSession } from "../../../src/app/lib/api";

const mocks = vi.hoisted(() => ({
  retrySetup: vi.fn(),
  refetchDomains: vi.fn(),
  refetchWsToken: vi.fn(),
  teardown: vi.fn(),
  saveToken: vi.fn(),
  deleteToken: vi.fn(),
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
  changeLanguage: vi.fn(),
  state: {
    authProvider: "password" as string,
    domains: undefined as unknown,
    domainsLoading: false,
    setupPending: false,
    savePending: false,
    passwordPending: false,
    tokenConfigured: true,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: mocks.changeLanguage, language: "fr" },
  }),
}));

vi.mock("../../../src/app/components/common/cloudflare-integrator", () => ({
  CloudflareIntegrator: ({ onSuccess, userEmail }: { onSuccess: () => void; userEmail: string }) => (
    <div>
      <span>Cloudflare wizard for {userEmail}</span>
      <button type="button" onClick={onSuccess}>wizard done</button>
    </div>
  ),
}));

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({ activeDomain: "vinse.app" }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  getStoredAuthProvider: () => mocks.state.authProvider,
  useChangePassword: () => ({ mutateAsync: mocks.changePassword, isPending: mocks.state.passwordPending, reset: vi.fn() }),
  useUpdateProfile: () => ({ mutateAsync: mocks.updateProfile, isPending: false, reset: vi.fn() }),
  useCloudflareList: () => ({
    data: mocks.state.domains,
    isLoading: mocks.state.domainsLoading,
    refetch: mocks.refetchDomains,
  }),
  useSetupCloudflare: () => ({ mutateAsync: mocks.retrySetup, isPending: mocks.state.setupPending, reset: vi.fn() }),
  useTeardownCloudflare: () => ({ mutateAsync: mocks.teardown, isPending: false, reset: vi.fn() }),
  useWorkspaceCloudflareToken: () => ({ data: { configured: mocks.state.tokenConfigured }, refetch: mocks.refetchWsToken }),
  useSaveWorkspaceCloudflareToken: () => ({ mutateAsync: mocks.saveToken, isPending: mocks.state.savePending, reset: vi.fn() }),
  useDeleteWorkspaceCloudflareToken: () => ({ mutateAsync: mocks.deleteToken, isPending: false, reset: vi.fn() }),
  useDomainShieldStatus: () => ({ data: undefined, isLoading: false }),
  // The notifications tab mounts the alerts route in settings mode.
  useAlertPreferences: () => ({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() }),
  useUpdateAlertPreferences: () => ({ mutateAsync: vi.fn(), isPending: false, reset: vi.fn() }),
  useSecurityRules: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateSecurityRule: () => ({ mutateAsync: vi.fn(), isPending: false, reset: vi.fn() }),
  useDeleteSecurityRule: () => ({ mutateAsync: vi.fn(), isPending: false, reset: vi.fn() }),
  useAlertHistory: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useDismissAlert: () => ({ mutateAsync: vi.fn(), isPending: false, reset: vi.fn() }),
  useMarkDomainAlertsRead: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
}));

const failedDomain = {
  id: "integration-1",
  status: "error",
  zone_name: "vinse.app",
  destination_email: "michael@vinse.app",
};

const session = (overrides: Partial<AuthSession> = {}): AuthSession => ({
  id: "user-1",
  email: "michael@vinse.app",
  display_name: "Michael Adebayo",
  role: "owner",
  workspace_id: "workspace-1",
  workspace_name: "vinse.app Workspace",
  is_platform_admin: false,
  has_cloudflare_integration: false,
  threat_count: 0,
  onboarding_required: false,
  sla_latency_ms: 2000,
  ...overrides,
});

const tab = (name: string) => screen.getByRole("button", { name });
const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement;

beforeEach(() => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  mocks.state.domains = [failedDomain];
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  mocks.state.authProvider = "password";
  mocks.state.domainsLoading = false;
  mocks.state.setupPending = false;
  mocks.state.savePending = false;
  mocks.state.passwordPending = false;
  mocks.state.tokenConfigured = true;
});

describe("connected domain recovery", () => {
  it("retries a failed existing domain from its table row", async () => {
    mocks.retrySetup.mockResolvedValue({ status: "provisioning" });
    render(<SettingsRoute initialTab="domains" session={session({ onboarding_required: true })} />);

    expect(screen.getByText("settings.onboarding_retry")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "settings.retry_domain" })).toBeInTheDocument();
    expect(screen.getByText("settings.add_another_domain")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "settings.retry_domain" }));

    await waitFor(() => expect(mocks.retrySetup).toHaveBeenCalledWith({
      zone_name: "vinse.app",
      destination_email: "michael@vinse.app",
    }));
    expect(mocks.refetchDomains).toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent("settings.retry_started");
  });

  it("shows a spinner on the row being retried while the setup call is pending", async () => {
    mocks.retrySetup.mockImplementation(() => {
      mocks.state.setupPending = true;
      return new Promise((resolve) => setTimeout(() => resolve({ status: "provisioning" }), 20));
    });
    render(<SettingsRoute initialTab="domains" session={session()} />);

    const retry = screen.getByRole("button", { name: "settings.retry_domain" });
    fireEvent.click(retry);

    await waitFor(() => expect(retry).toBeDisabled());
    expect(retry.querySelector(".animate-spin")).not.toBeNull();
    mocks.state.setupPending = false;
    await screen.findByRole("status");
  });

  it("surfaces the server message when the retry fails", async () => {
    mocks.retrySetup.mockRejectedValue(new Error("Zone introuvable"));
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.retry_domain" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Zone introuvable");
    expect(mocks.refetchDomains).not.toHaveBeenCalled();
  });

  it("falls back to the retry failure copy when the rejection is not an Error", async () => {
    mocks.retrySetup.mockRejectedValue("nope");
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.retry_domain" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("settings.retry_failed");
  });

  it("does nothing when the failed domain has no recipient to retry with", () => {
    mocks.state.domains = [{ ...failedDomain, destination_email: "" }];
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.retry_domain" }));

    expect(mocks.retrySetup).not.toHaveBeenCalled();
  });
});

describe("settings navigation", () => {
  it("opens on the profile tab and switches tabs from the section list", () => {
    render(<SettingsRoute session={session()} />);

    expect(screen.getByRole("navigation", { name: "settings.title" })).toBeInTheDocument();
    expect(tab("settings.tab_profile")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("settings.profile_desc")).toBeInTheDocument();

    fireEvent.click(tab("settings.tab_security"));
    expect(tab("settings.tab_security")).toHaveAttribute("aria-current", "page");
    expect(tab("settings.tab_profile")).not.toHaveAttribute("aria-current");
    expect(screen.getByText("settings.security_desc")).toBeInTheDocument();

    fireEvent.click(tab("settings.tab_preferences"));
    expect(screen.getByText("settings.preferences_desc")).toBeInTheDocument();

    fireEvent.click(tab("settings.tab_notifications"));
    expect(screen.getByText("alerts.preferences_for_domain")).toBeInTheDocument();

    fireEvent.click(tab("settings.tab_integrations"));
    expect(screen.getByText("settings.integrations_desc")).toBeInTheDocument();
  });

  it("opens on the domains tab when onboarding is still required", () => {
    render(<SettingsRoute session={session({ onboarding_required: true })} />);

    expect(tab("settings.tab_domains")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("settings.onboarding_required")).toBeInTheDocument();
  });

  it("follows the session back to the domains tab when onboarding becomes required", () => {
    const { rerender } = render(<SettingsRoute session={session()} />);
    expect(tab("settings.tab_profile")).toHaveAttribute("aria-current", "page");

    rerender(<SettingsRoute session={session({ onboarding_required: true, display_name: "Michael" })} />);
    expect(tab("settings.tab_domains")).toHaveAttribute("aria-current", "page");
    fireEvent.click(tab("settings.tab_profile"));
    expect(input("settings.first_name")).toHaveValue("Michael");
    expect(input("settings.last_name")).toHaveValue("");
  });
});

describe("profile tab", () => {
  it("splits the display name and restores the local profile fields", () => {
    localStorage.setItem("sicurre_profile_title", "CTO");
    localStorage.setItem("sicurre_profile_company", "Vinse");
    localStorage.setItem("sicurre_profile_role", "admin");
    render(<SettingsRoute session={session({ display_name: "Michael A. Adebayo" })} />);

    expect(input("settings.first_name")).toHaveValue("Michael");
    expect(input("settings.last_name")).toHaveValue("A. Adebayo");
    expect(input("settings.email")).toHaveValue("michael@vinse.app");
    expect(input("settings.email")).toBeDisabled();
    expect(input("settings.job_title")).toHaveValue("CTO");
    expect(input("settings.company")).toHaveValue("Vinse");
    expect(screen.getByLabelText("settings.user_role")).toHaveValue("admin");
  });

  it("saves the combined name and persists the local fields", async () => {
    mocks.updateProfile.mockResolvedValue({ status: "ok" });
    render(<SettingsRoute session={session()} />);

    fireEvent.change(input("settings.first_name"), { target: { value: " Mika " } });
    fireEvent.change(input("settings.last_name"), { target: { value: "Adebayo " } });
    fireEvent.change(input("settings.job_title"), { target: { value: "Fondateur" } });
    fireEvent.change(input("settings.company"), { target: { value: "Sicurre" } });
    fireEvent.change(screen.getByLabelText("settings.user_role"), { target: { value: "member" } });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(mocks.updateProfile).toHaveBeenCalledWith({ display_name: "Mika Adebayo" }));
    expect(await screen.findByRole("status")).toHaveTextContent("settings.save_success");
    expect(localStorage.getItem("sicurre_profile_title")).toBe("Fondateur");
    expect(localStorage.getItem("sicurre_profile_company")).toBe("Sicurre");
    expect(localStorage.getItem("sicurre_profile_role")).toBe("member");
  });

  it("surfaces the server message when the profile save fails", async () => {
    mocks.updateProfile.mockRejectedValue(new Error("Nom trop long"));
    render(<SettingsRoute session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Nom trop long");
    expect(localStorage.getItem("sicurre_profile_title")).toBeNull();
  });

  it("falls back to the profile failure copy when the rejection is not an Error and clears the toast", async () => {
    mocks.updateProfile.mockRejectedValue("nope");
    render(<SettingsRoute session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("settings.profile_save_failed");
    fireEvent.click(within(toast).getByRole("button", { name: "Fermer la notification" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
});

describe("security tab", () => {
  const fillPasswords = (current: string, next: string, confirm: string) => {
    fireEvent.change(input("settings.current_password"), { target: { value: current } });
    fireEvent.change(input("settings.new_password"), { target: { value: next } });
    fireEvent.change(input("settings.confirm_password"), { target: { value: confirm } });
  };

  it("explains that Google handles the login when the session came from Google", () => {
    mocks.state.authProvider = "google";
    render(<SettingsRoute initialTab="security" session={session()} />);

    expect(screen.getByText("settings.google_login_active")).toBeInTheDocument();
    expect(screen.getByText("settings.google_login_desc")).toBeInTheDocument();
    expect(screen.queryByLabelText("settings.current_password")).not.toBeInTheDocument();
  });

  it("validates the password form before calling the API", () => {
    render(<SettingsRoute initialTab="security" session={session()} />);
    const submit = screen.getByRole("button", { name: "settings.update_password" });

    fireEvent.click(submit);
    expect(screen.getByText("settings.password_required")).toBeInTheDocument();

    fillPasswords("ancien", "nouveau-mdp", "different");
    fireEvent.click(submit);
    expect(screen.getByText("settings.password_mismatch")).toBeInTheDocument();

    fillPasswords("ancien", "court", "court");
    fireEvent.click(submit);
    expect(screen.getByText("settings.password_minimum")).toBeInTheDocument();

    expect(mocks.changePassword).not.toHaveBeenCalled();
  });

  it("changes the password and clears the form on success", async () => {
    mocks.changePassword.mockResolvedValue({ status: "ok" });
    render(<SettingsRoute initialTab="security" session={session()} />);

    fillPasswords("ancien-mdp", "nouveau-mdp", "nouveau-mdp");
    fireEvent.click(screen.getByRole("button", { name: "settings.update_password" }));

    await waitFor(() => expect(mocks.changePassword).toHaveBeenCalledWith({
      current_password: "ancien-mdp",
      new_password: "nouveau-mdp",
    }));
    expect(await screen.findByText("settings.password_updated")).toBeInTheDocument();
    expect(input("settings.current_password")).toHaveValue("");
    expect(input("settings.new_password")).toHaveValue("");
    expect(input("settings.confirm_password")).toHaveValue("");
  });

  it("shows the server message when the password change is refused", async () => {
    mocks.changePassword.mockRejectedValue(new Error("Mot de passe actuel incorrect"));
    render(<SettingsRoute initialTab="security" session={session()} />);

    fillPasswords("faux", "nouveau-mdp", "nouveau-mdp");
    fireEvent.click(screen.getByRole("button", { name: "settings.update_password" }));

    expect(await screen.findByText("Mot de passe actuel incorrect")).toBeInTheDocument();
    expect(screen.queryByText("settings.password_updated")).not.toBeInTheDocument();
  });

  it("falls back to the generic failure copy when the rejection is not an Error", async () => {
    mocks.changePassword.mockRejectedValue("nope");
    render(<SettingsRoute initialTab="security" session={session()} />);

    fillPasswords("faux", "nouveau-mdp", "nouveau-mdp");
    fireEvent.click(screen.getByRole("button", { name: "settings.update_password" }));

    expect(await screen.findByText("settings.password_update_failed")).toBeInTheDocument();
  });

  it("disables the submit button while the change is pending", () => {
    mocks.state.passwordPending = true;
    render(<SettingsRoute initialTab="security" session={session()} />);

    expect(screen.getByRole("button", { name: "settings.update_password" })).toBeDisabled();
  });
});

describe("preferences tab", () => {
  it("changes the interface language and persists it", () => {
    render(<SettingsRoute initialTab="preferences" session={session()} />);

    const language = screen.getByRole("combobox", { name: "settings.interface_language" });
    expect(language).toHaveValue("fr");
    fireEvent.change(language, { target: { value: "en" } });

    expect(language).toHaveValue("en");
    expect(localStorage.getItem("sicurre_lang")).toBe("en");
    expect(mocks.changeLanguage).toHaveBeenCalledWith("en");
  });

  it("switches the visual theme through the shared theme store", () => {
    render(<SettingsRoute initialTab="preferences" session={session()} />);

    const theme = screen.getByRole("combobox", { name: "settings.visual_theme" });
    expect(theme).toHaveValue("light");
    fireEvent.change(theme, { target: { value: "dark" } });

    expect(theme).toHaveValue("dark");
    expect(localStorage.getItem("sicurre_theme")).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");

    fireEvent.change(theme, { target: { value: "light" } });
    expect(document.documentElement).not.toHaveClass("dark");
  });
});

describe("domains tab", () => {
  it("shows the loading skeleton and hides the footprint while the list loads", () => {
    mocks.state.domains = undefined;
    mocks.state.domainsLoading = true;
    render(<SettingsRoute initialTab="domains" session={session()} />);

    expect(screen.getByText("settings.domains_title")).toBeInTheDocument();
    expect(screen.queryByText("settings.no_domains")).not.toBeInTheDocument();
    expect(screen.queryByText("settings.footprint_title")).not.toBeInTheDocument();
  });

  it("invites the first domain when none is connected", () => {
    mocks.state.domains = [];
    render(<SettingsRoute initialTab="domains" session={session({ onboarding_required: true })} />);

    expect(screen.getByText("settings.no_domains")).toBeInTheDocument();
    expect(screen.getByText("settings.onboarding_add_domain")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "settings.add_domain" })).toBeInTheDocument();
  });

  it("opens the Cloudflare wizard, cancels it, then confirms a newly added domain", async () => {
    mocks.state.domains = [];
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.add_domain" }));
    expect(screen.getByText("settings.new_cloudflare_domain")).toBeInTheDocument();
    expect(screen.getByText("Cloudflare wizard for michael@vinse.app")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "settings.add_domain" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByText("settings.new_cloudflare_domain")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "settings.add_domain" }));
    fireEvent.click(screen.getByRole("button", { name: "wizard done" }));

    expect(await screen.findByRole("status")).toHaveTextContent("settings.domain_added");
    expect(mocks.refetchDomains).toHaveBeenCalled();
    expect(screen.queryByText("settings.new_cloudflare_domain")).not.toBeInTheDocument();
  });

  it("closes the wizard when another tab is opened", () => {
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.add_another_domain" }));
    fireEvent.click(tab("settings.tab_profile"));
    fireEvent.click(tab("settings.tab_domains"));

    expect(screen.queryByText("settings.new_cloudflare_domain")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "settings.add_another_domain" })).toBeInTheDocument();
  });

  it("labels every domain status and lists each domain in the footprint", () => {
    mocks.state.domains = [
      { id: "d-1", status: "active", zone_name: "vinse.app", destination_email: "a@vinse.app" },
      { id: "d-2", status: "error", zone_name: "broken.test", destination_email: "b@broken.test" },
      { id: "d-3", status: "provisioning", zone_name: "pending.test", destination_email: "c@pending.test" },
    ];
    render(<SettingsRoute initialTab="domains" session={session()} />);

    const table = screen.getByRole("table");
    expect(within(table).getByText("settings.active_setup")).toBeInTheDocument();
    expect(within(table).getByText("settings.error_setup")).toBeInTheDocument();
    expect(within(table).getByText("settings.verify_setup")).toBeInTheDocument();
    expect(within(table).getAllByRole("button", { name: "settings.retry_domain" })).toHaveLength(1);
    expect(within(table).getAllByRole("button", { name: "settings.disconnect_domain_named" })).toHaveLength(3);
    expect(screen.getByText("settings.footprint_title")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "pending.test" })).toBeInTheDocument();
  });

  it("asks for confirmation before disconnecting and cancels cleanly", () => {
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.disconnect_domain_named" }));
    expect(screen.getByText("settings.disconnect_domain")).toBeInTheDocument();
    expect(screen.getByText("settings.disconnect_domain_desc")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByText("settings.disconnect_domain")).not.toBeInTheDocument();
    expect(mocks.teardown).not.toHaveBeenCalled();
  });

  it("disconnects the domain after confirmation and refreshes the list", async () => {
    mocks.teardown.mockResolvedValue({ status: "removed" });
    mocks.refetchDomains.mockResolvedValue(undefined);
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.disconnect_domain_named" }));
    fireEvent.click(screen.getByRole("button", { name: "settings.remove" }));

    await waitFor(() => expect(mocks.teardown).toHaveBeenCalledWith({ integration_id: "integration-1" }));
    expect(await screen.findByRole("status")).toHaveTextContent("settings.domain_disconnected");
    expect(mocks.refetchDomains).toHaveBeenCalled();
    expect(screen.queryByText("settings.disconnect_domain")).not.toBeInTheDocument();
  });

  it("surfaces the server message when the teardown fails", async () => {
    mocks.teardown.mockRejectedValue(new Error("Intégration verrouillée"));
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.disconnect_domain_named" }));
    fireEvent.click(screen.getByRole("button", { name: "settings.remove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Intégration verrouillée");
  });

  it("falls back to the disconnect failure copy when the rejection is not an Error", async () => {
    mocks.teardown.mockRejectedValue("nope");
    render(<SettingsRoute initialTab="domains" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.disconnect_domain_named" }));
    fireEvent.click(screen.getByRole("button", { name: "settings.remove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("settings.domain_disconnect_failed");
  });
});

describe("integrations tab", () => {
  const openTokenForm = () => {
    fireEvent.click(screen.getByRole("button", { name: "settings.edit_token" }));
    return screen.getByPlaceholderText(/^e\.g\. 8x_/) as HTMLInputElement;
  };

  it("hides the domain selector when no domain is connected and reports the missing token", () => {
    mocks.state.domains = [];
    mocks.state.tokenConfigured = false;
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    expect(screen.queryByRole("combobox", { name: "settings.domain_label" })).not.toBeInTheDocument();
    expect(screen.getByText("settings.no_active_integration")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "settings.edit_token" })).not.toBeInTheDocument();
  });

  it("selects the first connected domain and lets the user pick another", () => {
    mocks.state.domains = [
      { id: "d-1", status: "active", zone_name: "vinse.app", destination_email: "a@vinse.app" },
      { id: "d-2", status: "active", zone_name: "second.test", destination_email: "b@second.test" },
    ];
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    const selector = screen.getByRole("combobox", { name: "settings.domain_label" });
    expect(selector).toHaveValue("d-1");
    fireEvent.change(selector, { target: { value: "d-2" } });
    expect(selector).toHaveValue("d-2");
    expect(screen.getByText("settings.connected")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Cloudflare" })).toBeInTheDocument();
  });

  it("opens the token form, toggles its visibility and cancels without saving", () => {
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    const field = openTokenForm();
    expect(field).toHaveAttribute("type", "password");
    expect(screen.getByText("settings.cloudflare_token_desc")).toBeInTheDocument();

    const toggle = within(field.closest("form")!).getAllByRole("button").find((button) => button.textContent === "")!;
    fireEvent.click(toggle);
    expect(field).toHaveAttribute("type", "text");
    fireEvent.click(toggle);
    expect(field).toHaveAttribute("type", "password");

    fireEvent.change(field, { target: { value: "tok" } });
    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByPlaceholderText(/^e\.g\. 8x_/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "settings.edit_token" })).toBeInTheDocument();
    expect(mocks.saveToken).not.toHaveBeenCalled();
  });

  it("refuses an empty token before calling the API", async () => {
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    const field = openTokenForm();
    fireEvent.change(field, { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "settings.save_integration" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("settings.token_required");
    expect(mocks.saveToken).not.toHaveBeenCalled();
  });

  it("saves the trimmed token, closes the form and refreshes both queries", async () => {
    mocks.saveToken.mockResolvedValue({ configured: true });
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    const field = openTokenForm();
    fireEvent.change(field, { target: { value: "  8x_secret  " } });
    fireEvent.click(screen.getByRole("button", { name: "settings.save_integration" }));

    await waitFor(() => expect(mocks.saveToken).toHaveBeenCalledWith("8x_secret"));
    expect(await screen.findByRole("status")).toHaveTextContent("settings.token_saved");
    expect(mocks.refetchWsToken).toHaveBeenCalled();
    expect(mocks.refetchDomains).toHaveBeenCalled();
    expect(screen.queryByPlaceholderText(/^e\.g\. 8x_/)).not.toBeInTheDocument();
  });

  it("shows the verifying label and disables the submit while the save is pending", () => {
    mocks.state.savePending = true;
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    openTokenForm();
    expect(screen.getByRole("button", { name: "settings.verifying" })).toBeDisabled();
  });

  it("surfaces the server message when the token is rejected", async () => {
    mocks.saveToken.mockRejectedValue(new Error("Jeton invalide"));
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    fireEvent.change(openTokenForm(), { target: { value: "8x_bad" } });
    fireEvent.click(screen.getByRole("button", { name: "settings.save_integration" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Jeton invalide");
    expect(screen.getByPlaceholderText(/^e\.g\. 8x_/)).toBeInTheDocument();
  });

  it("falls back to the token failure copy when the rejection has no message", async () => {
    mocks.saveToken.mockRejectedValue({});
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    fireEvent.change(openTokenForm(), { target: { value: "8x_bad" } });
    fireEvent.click(screen.getByRole("button", { name: "settings.save_integration" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("settings.token_save_failed");
  });

  it("asks for confirmation before revoking and cancels cleanly", () => {
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.revoke_access" }));
    expect(screen.getByText("settings.revoke_api_title")).toBeInTheDocument();
    expect(screen.getByText("settings.revoke_api_desc")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByText("settings.revoke_api_title")).not.toBeInTheDocument();
    expect(mocks.deleteToken).not.toHaveBeenCalled();
  });

  it("revokes the token after confirmation and refreshes both queries", async () => {
    mocks.deleteToken.mockResolvedValue({ configured: false });
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.revoke_access" }));
    fireEvent.click(screen.getByRole("button", { name: "settings.revoke" }));

    await waitFor(() => expect(mocks.deleteToken).toHaveBeenCalledOnce());
    expect(await screen.findByRole("status")).toHaveTextContent("settings.token_deleted");
    expect(mocks.refetchWsToken).toHaveBeenCalled();
    expect(mocks.refetchDomains).toHaveBeenCalled();
    expect(screen.queryByText("settings.revoke_api_title")).not.toBeInTheDocument();
  });

  it("surfaces the server message when the revocation fails", async () => {
    mocks.deleteToken.mockRejectedValue(new Error("Révocation refusée"));
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.revoke_access" }));
    fireEvent.click(screen.getByRole("button", { name: "settings.revoke" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Révocation refusée");
  });

  it("falls back to the revocation failure copy when the rejection has no message", async () => {
    mocks.deleteToken.mockRejectedValue({});
    render(<SettingsRoute initialTab="integrations" session={session()} />);

    fireEvent.click(screen.getByRole("button", { name: "settings.revoke_access" }));
    fireEvent.click(screen.getByRole("button", { name: "settings.revoke" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("settings.token_delete_failed");
  });
});
