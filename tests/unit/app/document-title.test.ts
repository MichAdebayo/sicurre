import { describe, expect, it } from "vitest";

import {
  buildDocumentTitle,
  documentTitleKeys,
} from "../../../src/app/lib/document-title";
import { sidebarPagePaths } from "../../../src/app/lib/navigation";

const labels: Record<string, string> = {
  "page_titles.login": "Connexion",
  "page_titles.dashboard": "Tableau de bord",
  "page_titles.domain_shield": "Bouclier de domaine",
  "page_titles.admin": "Console d’administration",
};

const translate = (key: string) => labels[key] ?? key;

describe("browser document titles", () => {
  it("keeps the public homepage title limited to the product name", () => {
    expect(buildDocumentTitle("landing", translate)).toBe("Sicurre");
  });

  it.each([
    ["login", "Connexion | Sicurre"],
    ["dashboard", "Tableau de bord | Sicurre"],
    ["domain-shield", "Bouclier de domaine | Sicurre"],
    ["logs", "Console d’administration | Sicurre"],
  ] as const)("builds the %s route title", (view, expected) => {
    expect(buildDocumentTitle(view, translate)).toBe(expected);
  });

  it("defines a title for every authenticated route", () => {
    for (const page of Object.keys(sidebarPagePaths)) {
      expect(documentTitleKeys[page as keyof typeof documentTitleKeys]).toBeTruthy();
    }
  });
});
