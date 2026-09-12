// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThreatRow } from "../../../src/app/components/threats/threat-row";
import type { ThreatLog } from "../../../src/app/lib/api";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
  motion: { div: "div" },
}));

vi.mock("../../../src/app/lib/api", () => ({}));

const threat = (overrides: Partial<ThreatLog> = {}): ThreatLog => ({
  id: "threat-1",
  message_id: "<msg-1@example.com>",
  subject: "Votre compte est suspendu",
  sender: "attaquant@exemple.fr",
  body_preview: "Cliquez ici pour réactiver votre compte.",
  verdict: "phishing",
  confidence: 0.93,
  status: "active",
  received_at: "2026-09-10T12:00:00Z",
  latency_ms: 412.6,
  explanation: "Lien de connexion vers un domaine inconnu.",
  model_version: "sicurre-onnx-v3",
  model_revision: "abcdef1234567890",
  privacy_reference: "ref-1",
  content_redacted: false,
  ...overrides,
});

afterEach(cleanup);

describe("ThreatRow", () => {
  it("shows the subject, the verdict badge, the received date and the quarantine action for an active threat", () => {
    render(<ThreatRow threat={threat()} onUpdateStatus={vi.fn()} />);
    expect(screen.getByText("Votre compte est suspendu")).toBeInTheDocument();
    expect(screen.getByText("expediteur@sicurre-logs.fr")).toBeInTheDocument();
    expect(screen.getByText("threats.badge_phishing")).toBeInTheDocument();
    expect(screen.getByText(/\/09\/2026/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mettre en quarantaine" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restaurer" })).not.toBeInTheDocument();
  });

  it("falls back to a placeholder when the subject is empty", () => {
    render(<ThreatRow threat={threat({ subject: "" })} onUpdateStatus={vi.fn()} />);
    expect(screen.getByText("(Aucun objet)")).toBeInTheDocument();
  });

  it("asks to trash an active threat and to restore a trashed one", () => {
    const onUpdateStatus = vi.fn();
    const { unmount } = render(<ThreatRow threat={threat()} onUpdateStatus={onUpdateStatus} />);
    fireEvent.click(screen.getByRole("button", { name: "Mettre en quarantaine" }));
    expect(onUpdateStatus).toHaveBeenCalledWith("threat-1", "trashed");
    unmount();

    render(<ThreatRow threat={threat({ status: "trashed" })} onUpdateStatus={onUpdateStatus} />);
    expect(screen.queryByRole("button", { name: "Mettre en quarantaine" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restaurer" }));
    expect(onUpdateStatus).toHaveBeenCalledWith("threat-1", "restored");
    expect(onUpdateStatus).toHaveBeenCalledTimes(2);
  });

  it("keeps the row collapsed until the subject is clicked, then reveals the explanation, preview and model identity", () => {
    render(<ThreatRow threat={threat()} onUpdateStatus={vi.fn()} />);
    expect(screen.queryByText("Pourquoi ce verdict")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Votre compte est suspendu"));

    expect(screen.getByText("Pourquoi ce verdict")).toBeInTheDocument();
    expect(screen.getByText("Lien de connexion vers un domaine inconnu.")).toBeInTheDocument();
    expect(screen.getByText("Cliquez ici pour réactiver votre compte.")).toBeInTheDocument();
    expect(screen.getByText("sicurre-onnx-v3")).toBeInTheDocument();
    expect(screen.getByText("abcdef123456")).toBeInTheDocument();
    expect(screen.getByTitle("abcdef1234567890")).toBeInTheDocument();
    expect(screen.getByText(/Latence/)).toHaveTextContent("413");
    expect(screen.queryByText("non enregistré")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Votre compte est suspendu"));
    expect(screen.queryByText("Pourquoi ce verdict")).not.toBeInTheDocument();
  });

  it("shows the fallbacks when the explanation, preview, model identity and latency are absent", () => {
    render(
      <ThreatRow
        threat={threat({
          explanation: undefined,
          body_preview: "",
          model_version: null,
          model_revision: null,
          latency_ms: undefined,
          verdict: "spam",
        })}
        onUpdateStatus={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Votre compte est suspendu"));

    expect(screen.queryByText("Pourquoi ce verdict")).not.toBeInTheDocument();
    expect(screen.getByText("Aucun aperçu du contenu de l'e-mail disponible.")).toBeInTheDocument();
    expect(screen.getByText("non enregistré")).toBeInTheDocument();
    expect(screen.queryByText(/Révision/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Latence/)).not.toBeInTheDocument();
    expect(screen.getByText("threats.badge_spam")).toBeInTheDocument();
  });

  it("tints the row hover according to the verdict", () => {
    const { container, unmount } = render(<ThreatRow threat={threat({ verdict: "legitimate" })} onUpdateStatus={vi.fn()} />);
    expect(container.firstElementChild).toHaveClass("hover:bg-safe-bg/50");
    unmount();

    const spam = render(<ThreatRow threat={threat({ verdict: "spam" })} onUpdateStatus={vi.fn()} />);
    expect(spam.container.firstElementChild).toHaveClass("hover:bg-warning-bg/50");
    spam.unmount();

    const phishing = render(<ThreatRow threat={threat({ verdict: "phishing" })} onUpdateStatus={vi.fn()} />);
    expect(phishing.container.firstElementChild).toHaveClass("hover:bg-error/5");
  });
});
