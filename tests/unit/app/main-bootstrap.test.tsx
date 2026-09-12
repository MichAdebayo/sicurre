// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import React, { type ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../src/app/locales/en.json";
import fr from "../../../src/app/locales/fr.json";

const mocks = vi.hoisted(() => ({
  createRoot: vi.fn(),
  render: vi.fn(),
  unmount: vi.fn(),
}));

vi.mock("react-dom/client", () => ({
  default: { createRoot: mocks.createRoot },
  createRoot: mocks.createRoot,
}));

vi.mock("../../../src/app/App.tsx", () => ({
  default: () => <div>Application Sicurre</div>,
}));

vi.mock("../../../src/app/index.css", () => ({}));

async function bootstrap() {
  await import("../../../src/app/main.tsx");
  const i18n = (await import("i18next")).default;
  return { i18n };
}

const renderedTree = (): ReactElement => mocks.render.mock.calls[0][0] as ReactElement;

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  document.documentElement.lang = "";
  mocks.createRoot.mockReturnValue({ render: mocks.render, unmount: mocks.unmount });
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  mocks.createRoot.mockReset();
  mocks.render.mockReset();
  document.body.innerHTML = "";
});

describe("application bootstrap", () => {
  it("mounts the application once into the #root element", async () => {
    await bootstrap();

    expect(mocks.createRoot).toHaveBeenCalledTimes(1);
    expect(mocks.createRoot).toHaveBeenCalledWith(document.getElementById("root"));
    expect(mocks.render).toHaveBeenCalledTimes(1);

    render(renderedTree());
    expect(screen.getByText("Application Sicurre")).toBeInTheDocument();
  });

  it("wraps the application in StrictMode and a query client that does not refetch on focus", async () => {
    await bootstrap();

    const tree = renderedTree();
    expect(tree.type).toBe(React.StrictMode);

    const provider = (tree.props as { children: ReactElement }).children;
    expect(provider.type).toBe(QueryClientProvider);

    const client = (provider.props as { client: { getDefaultOptions: () => { queries?: Record<string, unknown> } } }).client;
    expect(client.getDefaultOptions().queries).toEqual(
      expect.objectContaining({ refetchOnWindowFocus: false, retry: 1 }),
    );
  });

  it("starts in French by default and keeps the document language in sync with i18next", async () => {
    const { i18n } = await bootstrap();

    expect(i18n.language).toBe("fr");
    expect(document.documentElement.lang).toBe("fr");
    expect(i18n.t("threats.title")).toBe(fr.threats.title);

    await i18n.changeLanguage("en-GB");
    expect(document.documentElement.lang).toBe("en");

    await i18n.changeLanguage("fr");
    expect(document.documentElement.lang).toBe("fr");
  });

  it("restores the language the visitor stored earlier", async () => {
    localStorage.setItem("sicurre_lang", "en");

    const { i18n } = await bootstrap();

    expect(i18n.language).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(i18n.t("threats.title")).toBe(en.threats.title);
  });

  it("falls back to the French copy for a key missing from the stored language", async () => {
    localStorage.setItem("sicurre_lang", "en");

    const { i18n } = await bootstrap();

    expect(i18n.t("threats.title", { lng: "de" })).toBe(fr.threats.title);
  });
});
