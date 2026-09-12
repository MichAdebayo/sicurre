// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../../src/app/components/ui/card";

afterEach(cleanup);

describe("Card", () => {
  it("renders a default bordered card containing its children", () => {
    render(<Card data-testid="card">Contenu</Card>);
    const card = screen.getByTestId("card");
    expect(card).toHaveTextContent("Contenu");
    expect(card).toHaveClass("bg-surface-lowest");
    expect(card).toHaveClass("border");
  });

  it("expresses each visual variant through its surface class", () => {
    render(
      <>
        <Card data-testid="safe" variant="safe" />
        <Card data-testid="alert" variant="alert" />
        <Card data-testid="dark" variant="dark" />
      </>,
    );
    expect(screen.getByTestId("safe")).toHaveClass("bg-surface-safe");
    expect(screen.getByTestId("alert")).toHaveClass("bg-surface-alert");
    expect(screen.getByTestId("dark")).toHaveClass("glass-card-dark");
    expect(screen.getByTestId("dark")).toHaveClass("text-white");
  });

  it("expresses each elevation level", () => {
    render(
      <>
        <Card data-testid="flat" elevation="flat" />
        <Card data-testid="hover" elevation="hover" />
        <Card data-testid="shadow" elevation="shadow" />
      </>,
    );
    expect(screen.getByTestId("flat")).not.toHaveClass("shadow-lg");
    expect(screen.getByTestId("hover")).toHaveClass("hover:shadow-md");
    expect(screen.getByTestId("shadow")).toHaveClass("shadow-lg");
  });

  it("forwards attributes and merges a custom class name", () => {
    render(<Card className="p-6" role="region" aria-label="Résumé" />);
    const region = screen.getByRole("region", { name: "Résumé" });
    expect(region).toHaveClass("p-6");
    expect(region).toHaveClass("rounded-xl");
  });
});

describe("Card sections", () => {
  it("compose a header with a heading, a description and a body", () => {
    render(
      <Card>
        <CardHeader data-testid="header" className="custom-header">
          <div>
            <CardTitle className="custom-title">Menaces</CardTitle>
            <CardDescription className="custom-description">Dernières détections</CardDescription>
          </div>
        </CardHeader>
        <CardContent data-testid="content" className="custom-content">
          <p>Corps de la carte</p>
        </CardContent>
      </Card>,
    );

    const title = screen.getByRole("heading", { level: 3, name: "Menaces" });
    expect(title).toHaveClass("custom-title");

    const description = screen.getByText("Dernières détections");
    expect(description.tagName).toBe("P");
    expect(description).toHaveClass("custom-description");

    const header = screen.getByTestId("header");
    expect(header).toContainElement(title);
    expect(header).toHaveClass("custom-header");

    const content = screen.getByTestId("content");
    expect(content).toHaveTextContent("Corps de la carte");
    expect(content).toHaveClass("custom-content");
    expect(content).toHaveClass("space-y-4");
  });
});
