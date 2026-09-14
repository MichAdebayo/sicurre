import { describe, expect, it } from "vitest";

import { tidyPreviewText } from "../../../src/app/lib/quarantine-preview";

describe("tidyPreviewText", () => {
  it("normalises Windows and old Mac line endings", () => {
    expect(tidyPreviewText("Bonjour,\r\nVotre colis\rest bloqué.")).toBe("Bonjour,\nVotre colis\nest bloqué.");
  });

  it("turns whitespace-only lines into blank lines and keeps one blank line between paragraphs", () => {
    const stored = "Madame, Monsieur,\r\n \r\n\t\r\n \r\n\r\nUn remboursement est en attente.\r\n \r\nCordialement";
    expect(tidyPreviewText(stored)).toBe("Madame, Monsieur,\n\nUn remboursement est en attente.\n\nCordialement");
  });

  it("closes up a double-spaced message and keeps its real paragraph breaks", () => {
    const stored = [
      "Un remboursement de 312,45 EUR est en attente de versement sur",
      " ",
      "votre compte.",
      "",
      "Nos services n'ont pas pu finaliser",
      "",
      "l'operation.",
      "",
      " ",
      "",
      "Merci de mettre a jour",
      "",
      "vos coordonnees.",
    ].join("\r\n");

    expect(tidyPreviewText(stored)).toBe(
      "Un remboursement de 312,45 EUR est en attente de versement sur\n"
        + "votre compte.\n"
        + "Nos services n'ont pas pu finaliser\n"
        + "l'operation.\n\n"
        + "Merci de mettre a jour\n"
        + "vos coordonnees.",
    );
  });

  it("leaves a normally written message with paragraphs of several lines as it is", () => {
    const stored = "Bonjour,\nVoici le lien.\n\nMerci de cliquer\navant ce soir.\n\nCordialement";
    expect(tidyPreviewText(stored)).toBe(stored);
  });

  it("strips trailing spaces but keeps the text and its indentation", () => {
    expect(tidyPreviewText("  > cité   \nIBAN [IBAN]  ")).toBe("> cité\nIBAN [IBAN]");
    expect(tidyPreviewText("ligne\n  indentée")).toBe("ligne\n  indentée");
  });

  it("drops leading and trailing blank lines and handles an empty preview", () => {
    expect(tidyPreviewText("\r\n\r\n  \r\nTexte\r\n\r\n")).toBe("Texte");
    expect(tidyPreviewText("")).toBe("");
    expect(tidyPreviewText(null)).toBe("");
    expect(tidyPreviewText(undefined)).toBe("");
  });
});
