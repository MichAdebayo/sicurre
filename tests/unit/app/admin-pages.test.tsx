// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import fr from "../../../src/app/locales/fr.json";
import en from "../../../src/app/locales/en.json";
import LogsRoute from "../../../src/app/routes/logs";
import AdminIntegrationsRoute from "../../../src/app/routes/admin-integrations";
import AdminReviewsRoute from "../../../src/app/routes/admin-reviews";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(), domains: vi.fn(), refetch: vi.fn(), erase: vi.fn(), loading: false, error: false, erasePending: false,
  overviewData: {
    summary: { workspaces_count: 2, threat_events_count: 10, feedback_count: 3, false_negative_count: 1, reported_email_count: 1, cloudflare_active_count: 1, cloudflare_integrations_count: 2, support_open_count: 0 },
    verdicts: [{ verdict: "legitimate", count: 7 }], recent_feedback: [], recent_quarantine: [], recent_support: [],
  },
}));
vi.mock("../../../src/app/lib/api", () => ({
  useAdminOverview: () => {
    mocks.overview();
    return { data: mocks.error || mocks.loading ? undefined : mocks.overviewData, isLoading: mocks.loading, isError: mocks.error, refetch: mocks.refetch };
  },
  useAdminDomains: (page: number, search: string) => {
    mocks.domains(page, search);
    return { data: mocks.loading || mocks.error ? undefined : { total: 21, pages: 2, page, items: search ? [] : [{ zone_name: "example.test", user_email: "owner@example.test", status: "active", updated_at: "2026-09-03T10:00:00Z" }] }, isLoading: mocks.loading, isError: mocks.error, refetch: mocks.refetch };
  },
  useEraseAdminAccount: () => ({ mutateAsync: mocks.erase, isPending: mocks.erasePending, reset: vi.fn() }),
}));

function renderPage(page: ReactNode, language = "fr") {
  const i18n = createInstance();
  i18n.init({ lng: language, resources: { fr: { translation: fr }, en: { translation: en } }, initImmediate: false });
  return render(<I18nextProvider i18n={i18n}>{page}</I18nextProvider>);
}
afterEach(() => { cleanup(); vi.clearAllMocks(); mocks.loading = false; mocks.error = false; mocks.erasePending = false; });

describe("dedicated admin pages", () => {
  it.each(["fr", "en"])("renders overview independently with translated labels (%s)", (language) => {
    renderPage(<LogsRoute />, language);
    const copy = language === "fr" ? fr : en;
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(copy.admin.views.overview);
    expect(screen.getByText(copy.admin.metrics.workspaces)).toBeVisible();
    expect(screen.queryByText(copy.admin.recent_support)).not.toBeInTheDocument();
    expect(mocks.domains).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: copy.admin.refresh }));
    expect(mocks.refetch).toHaveBeenCalledOnce();
  });

  it("keeps support requests in administrative reviews, not customer navigation", () => {
    renderPage(<AdminReviewsRoute />, "en");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(en.admin.views.reviews);
    expect(screen.getByRole("heading", { name: "Recent support requests" })).toBeVisible();
    expect(screen.queryByText("Verdict distribution")).not.toBeInTheDocument();
  });

  it("paginates and searches integrations without fetching the overview", async () => {
    renderPage(<AdminIntegrationsRoute />);
    expect(screen.getByText("example.test")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Suivant" }));
    expect(mocks.domains).toHaveBeenLastCalledWith(2, "");
    fireEvent.change(screen.getByRole("textbox", { name: "Domaine ou propriétaire" }), { target: { value: "missing" } });
    await waitFor(() => expect(mocks.domains).toHaveBeenLastCalledWith(1, "missing"));
    expect(screen.getByText("Aucun domaine correspondant.")).toBeVisible();
    expect(mocks.overview).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Actualiser" }));
    expect(mocks.refetch).toHaveBeenCalledOnce();
  });

  it.each(["loading", "error"] as const)("does not show an empty domains message during %s", (state) => {
    mocks[state] = true;
    renderPage(<AdminIntegrationsRoute />);
    expect(screen.queryByText("Aucun domaine connecté.")).not.toBeInTheDocument();
    expect(screen.getByRole(state === "loading" ? "status" : "alert")).toBeVisible();
  });
});

describe("account erasure from the console", () => {
  const dialog = () => screen.getByRole("alertdialog");
  const confirmButton = () => within(dialog()).getByRole("button", { name: "Supprimer" });
  const rowDelete = () => screen.getByRole("button", { name: "Supprimer le compte owner@example.test" });

  it("lists the domains in a table with the owner, status and update date", () => {
    renderPage(<AdminIntegrationsRoute />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Domaine" })).toBeVisible();
    expect(within(table).getByRole("columnheader", { name: "Propriétaire" })).toBeVisible();
    expect(within(table).getByRole("cell", { name: "owner@example.test" })).toBeVisible();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("asks once in a short dialog from the row action, then confirms with a notification", async () => {
    mocks.erase.mockResolvedValue({ status: "deleted" });
    renderPage(<AdminIntegrationsRoute />);

    fireEvent.click(rowDelete());
    expect(within(dialog()).getByText("Supprimer le compte")).toBeInTheDocument();
    expect(within(dialog()).getByText("Cette action est irréversible.")).toBeInTheDocument();
    expect(within(dialog()).getByText("owner@example.test")).toBeInTheDocument();
    expect(within(dialog()).queryByRole("checkbox")).not.toBeInTheDocument();

    fireEvent.click(confirmButton());
    expect(await screen.findByText("Compte supprimé : owner@example.test")).toBeInTheDocument();
    expect(mocks.erase).toHaveBeenCalledWith("owner@example.test");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("deletes the ticked accounts from the selection button", async () => {
    mocks.erase.mockResolvedValue({ status: "deleted" });
    renderPage(<AdminIntegrationsRoute />);

    expect(screen.queryByRole("button", { name: /Supprimer \(/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Sélectionner tous les comptes de la page" }));
    expect(screen.getByRole("checkbox", { name: "Sélectionner le compte owner@example.test" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Supprimer (1)" }));
    fireEvent.click(confirmButton());

    await waitFor(() => expect(mocks.erase).toHaveBeenCalledWith("owner@example.test"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Supprimer \(/ })).not.toBeInTheDocument());
  });

  it("offers no delete action on the signed-in admin's own row", () => {
    renderPage(<AdminIntegrationsRoute currentEmail="Owner@Example.test" />);

    expect(screen.getByText("Votre compte")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Supprimer le compte owner@example.test" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Sélectionner le compte owner@example.test" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner tous les comptes de la page" })).toBeDisabled();
  });

  it("refuses the admin's own address in the form without opening the dialog", () => {
    renderPage(<AdminIntegrationsRoute currentEmail="admin@example.test" />);

    fireEvent.change(screen.getByRole("textbox", { name: "Adresse e-mail du compte" }), { target: { value: " Admin@Example.test " } });
    fireEvent.click(screen.getByRole("button", { name: "Supprimer" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Supprimez votre propre compte depuis vos paramètres.");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(mocks.erase).not.toHaveBeenCalled();
  });

  it("opens the same dialog for an address typed in the form and cancels cleanly", async () => {
    renderPage(<AdminIntegrationsRoute />);
    const openButton = screen.getByRole("button", { name: "Supprimer" });

    expect(openButton).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Adresse e-mail du compte" }), { target: { value: " New@Example.test " } });
    fireEvent.click(openButton);
    expect(within(dialog()).getByText("new@example.test")).toBeInTheDocument();

    fireEvent.click(within(dialog()).getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(mocks.erase).not.toHaveBeenCalled();
  });

  it("shows each refusal in French with the account it concerns", async () => {
    mocks.erase.mockRejectedValueOnce(new Error("No account with this email"));
    renderPage(<AdminIntegrationsRoute />);
    fireEvent.click(rowDelete());
    fireEvent.click(confirmButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("owner@example.test : Aucun compte avec cette adresse.");

    mocks.erase.mockRejectedValueOnce("offline");
    fireEvent.click(rowDelete());
    fireEvent.click(confirmButton());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("La suppression n’a pas abouti."));
  });

  it("shows the deletion in progress and cannot be dismissed while it runs", () => {
    mocks.erasePending = true;
    renderPage(<AdminIntegrationsRoute />);
    fireEvent.click(rowDelete());

    expect(within(dialog()).getByRole("button", { name: "Suppression…" })).toBeDisabled();
    fireEvent.keyDown(dialog(), { key: "Escape" });
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });
});

describe("refresh button", () => {
  it("spins only while a refresh the admin asked for is running", async () => {
    let finish!: () => void;
    mocks.refetch.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; }));
    renderPage(<AdminIntegrationsRoute />);
    const button = screen.getByRole("button", { name: "Actualiser" });

    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await act(async () => { finish(); });
    await waitFor(() => expect(button).toBeEnabled());
    expect(mocks.refetch).toHaveBeenCalledOnce();
  });
});
