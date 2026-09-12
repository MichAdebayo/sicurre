// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CGURoute from "../../../src/app/routes/cgu";
import ConfidentialiteRoute from "../../../src/app/routes/confidentialite";
import MentionsLegalesRoute from "../../../src/app/routes/mentions-legales";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: { div: "div" },
}));

afterEach(cleanup);

const pages = [
  {
    name: "CGU",
    Route: CGURoute,
    title: "Conditions Générales d'Utilisation",
    sections: [
      "1. Objet des CGU",
      "2. Connexion & Intégration Cloudflare",
      "3. Engagements & Responsabilités",
      "4. Modification et Résiliation",
      "5. Droit applicable & Juridiction",
    ],
  },
  {
    name: "Confidentialite",
    Route: ConfidentialiteRoute,
    title: "Politique de Confidentialité",
    sections: [
      "1. Engagements RGPD et Souveraineté",
      "2. Cloudflare Email Routing & autorisations",
      "3. Stockage minimal et quarantaine temporaire",
      "4. Masquage automatique des Données Personnelles (PII)",
      "5. Révocation de vos autorisations",
    ],
  },
  {
    name: "MentionsLegales",
    Route: MentionsLegalesRoute,
    title: "Mentions Légales",
    sections: ["1. Éditeur du site", "2. Hébergement", "3. Nous contacter", "4. Propriété intellectuelle"],
  },
];

describe.each(pages)("$name legal page", ({ Route, title, sections }) => {
  it("exposes the header, main and footer landmarks with the Sicurre brand", () => {
    render(<Route onBack={vi.fn()} />);
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("img", { name: "Sicurre Logo" })).toBeInTheDocument();
    expect(within(header).getByText("Sicurre")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("© 2026 Sicurre. Tous droits réservés.");
  });

  it("titles the page and dates its last update", () => {
    render(<Route onBack={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText("Dernière mise à jour : 18 juin 2026")).toBeInTheDocument();
  });

  it("lists every numbered section as a level 2 heading inside the main region", () => {
    render(<Route onBack={vi.fn()} />);
    const main = screen.getByRole("main");
    const headings = within(main).getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(headings).toEqual(sections);
  });

  it("returns to the home page through the labelled back control", () => {
    const onBack = vi.fn();
    render(<Route onBack={onBack} />);
    fireEvent.click(screen.getByRole("button", { name: "Retour à l'accueil" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});

describe("CGU content", () => {
  it("names the three Cloudflare permissions the user grants", () => {
    render(<CGURoute onBack={vi.fn()} />);
    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual([
      "Inspecter les métadonnées des e-mails entrants en temps réel (expéditeur, sujet, verdict de score).",
      "Configurer les enregistrements DNS requis (SPF, DKIM, DMARC) pour la sécurisation du domaine.",
      "Conserver en quarantaine isolée temporaire les messages identifiés comme malveillants.",
    ]);
    expect(screen.getByText(/soumises au droit français/)).toBeInTheDocument();
  });
});

describe("Confidentialite content", () => {
  it("states the quarantine retention and the PII placeholders", () => {
    render(<ConfidentialiteRoute onBack={vi.fn()} />);
    expect(
      screen.getByText(/le MIME original d'un message classé comme phishing est placé dans une quarantaine privée pendant 14 jours au maximum/),
    ).toBeInTheDocument();
    expect(screen.getByText("Les messages clients ne servent pas à entraîner un modèle public.")).toBeInTheDocument();
    expect(screen.getByText("[EMAIL]")).toBeInTheDocument();
    expect(screen.getByText("[PHONE]")).toBeInTheDocument();
    expect(screen.getByText("[IBAN]")).toBeInTheDocument();
  });

  it("lists the Cloudflare token scopes and the stored metadata", () => {
    render(<ConfidentialiteRoute onBack={vi.fn()} />);
    expect(screen.getByText("DNS zone read/edit")).toBeInTheDocument();
    expect(screen.getByText("Email Routing read/edit")).toBeInTheDocument();
    expect(screen.getByText("Workers read/edit")).toBeInTheDocument();
    expect(screen.getByText("Adresse de l'expéditeur et du destinataire")).toBeInTheDocument();
    expect(screen.getByText("Verdict de classification (Légitime, Spam, Phishing) et score de confiance associé")).toBeInTheDocument();
  });
});

describe("Mentions legales content", () => {
  it("names the publisher, the hosts and the contact address", () => {
    render(<MentionsLegalesRoute onBack={vi.fn()} />);
    expect(screen.getByText("Responsable de la publication :")).toBeInTheDocument();
    expect(screen.getByText("Neon Inc.")).toBeInTheDocument();
    expect(screen.getByText("Hetzner Online GmbH")).toBeInTheDocument();
    expect(screen.getByText("Cloudflare, Inc.")).toBeInTheDocument();
    expect(screen.getByText(/contact@sicurre\.com/)).toBeInTheDocument();
  });
});
