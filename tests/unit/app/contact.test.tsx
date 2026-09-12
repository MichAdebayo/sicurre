// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ContactRoute from "../../../src/app/routes/contact";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: { div: "div" },
}));

const location = { href: "" };

beforeEach(() => {
  location.href = "";
  vi.stubGlobal("location", location);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function fillForm({ name = "Jean Dupont", email = "jean@entreprise.fr", message = "Bonjour" } = {}) {
  fireEvent.change(screen.getByPlaceholderText("Jean Dupont"), { target: { value: name } });
  fireEvent.change(screen.getByPlaceholderText("jean@entreprise.fr"), { target: { value: email } });
  fireEvent.change(screen.getByPlaceholderText("Décrivez votre demande en détail..."), { target: { value: message } });
}

describe("Contact page", () => {
  it("exposes the header, main and footer landmarks and the brand", () => {
    render(<ContactRoute onBack={vi.fn()} />);
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("img", { name: "Sicurre Logo" })).toBeInTheDocument();
    expect(within(header).getByText("Sicurre")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("© 2026 Sicurre. Tous droits réservés.");
  });

  it("explains that the message is prepared here and sent from the user's own mail client", () => {
    render(<ContactRoute onBack={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1, name: "Discutons ensemble" })).toBeInTheDocument();
    expect(screen.getByText("Préparez votre message ici, puis envoyez-le depuis votre messagerie habituelle.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Sécurité & Chiffrement" })).toBeInTheDocument();
    expect(
      screen.getByText("Cette page n’enregistre pas votre message. Votre application de messagerie prend en charge l’envoi."),
    ).toBeInTheDocument();
    expect(screen.getByText("contact@sicurre.com")).toBeInTheDocument();
    expect(screen.getByText("Roubaix, France")).toBeInTheDocument();
  });

  it("offers the four request subjects with technical support selected by default", () => {
    render(<ContactRoute onBack={vi.fn()} />);
    const subject = screen.getByLabelText("Sujet de votre demande") as HTMLSelectElement;
    expect(subject.value).toBe("support");
    expect(within(subject).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Support Technique / Fausse classification",
      "Demande Commerciale / Tarifs",
      "Signalement de Sécurité / Bug Bounty",
      "Autre demande",
    ]);
  });

  it("returns to the home page through the labelled back control", () => {
    const onBack = vi.fn();
    render(<ContactRoute onBack={onBack} />);
    fireEvent.click(screen.getByRole("button", { name: "Retour à l'accueil" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("opens the mail client with the subject and body built from the form", () => {
    render(<ContactRoute onBack={vi.fn()} />);
    fillForm({ name: "Jean Dupont", email: "jean@entreprise.fr", message: "Faux positif sur une facture" });
    fireEvent.change(screen.getByLabelText("Sujet de votre demande"), { target: { value: "security" } });
    fireEvent.click(screen.getByRole("button", { name: "Ouvrir ma messagerie" }));

    const expectedSubject = encodeURIComponent("[Sicurre - security] Jean Dupont");
    const expectedBody = encodeURIComponent("Nom: Jean Dupont\nE-mail: jean@entreprise.fr\n\nFaux positif sur une facture");
    expect(location.href).toBe(`mailto:contact@sicurre.com?subject=${expectedSubject}&body=${expectedBody}`);
  });

  it("keeps the default subject when the user does not change it", () => {
    render(<ContactRoute onBack={vi.fn()} />);
    fillForm();
    fireEvent.submit(screen.getByRole("button", { name: "Ouvrir ma messagerie" }).closest("form")!);
    expect(location.href).toContain(`subject=${encodeURIComponent("[Sicurre - support] Jean Dupont")}`);
  });

  it("does nothing when a required field is still empty", () => {
    render(<ContactRoute onBack={vi.fn()} />);
    const form = screen.getByRole("button", { name: "Ouvrir ma messagerie" }).closest("form")!;

    fireEvent.submit(form);
    expect(location.href).toBe("");

    fillForm({ message: "" });
    fireEvent.submit(form);
    expect(location.href).toBe("");

    fillForm({ email: "" });
    fireEvent.submit(form);
    expect(location.href).toBe("");

    fillForm({ name: "" });
    fireEvent.submit(form);
    expect(location.href).toBe("");
  });
});
