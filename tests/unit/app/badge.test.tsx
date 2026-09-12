// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Badge } from "../../../src/app/components/ui/badge";

afterEach(cleanup);

describe("Badge", () => {
  it("renders its children inside an inline span with the neutral variant by default", () => {
    render(<Badge>Nouveau</Badge>);
    const badge = screen.getByText("Nouveau");
    expect(badge.tagName).toBe("SPAN");
    expect(badge).toHaveClass("text-on-surface-variant");
  });

  it("expresses each variant through its tone class", () => {
    render(
      <>
        <Badge variant="info">info</Badge>
        <Badge variant="warning">warning</Badge>
        <Badge variant="critical">critical</Badge>
        <Badge variant="success">success</Badge>
        <Badge variant="neutral">neutral</Badge>
      </>,
    );
    expect(screen.getByText("info")).toHaveClass("text-primary");
    expect(screen.getByText("warning")).toHaveClass("text-secondary");
    expect(screen.getByText("critical")).toHaveClass("text-error");
    expect(screen.getByText("success")).toHaveClass("text-safe");
    expect(screen.getByText("neutral")).toHaveClass("text-on-surface-variant");
  });

  it("forwards extra attributes and merges a custom class name", () => {
    render(
      <Badge variant="success" className="ml-2" title="Statut" data-testid="status-badge">
        Actif
      </Badge>
    );
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("Actif");
    expect(badge).toHaveAttribute("title", "Statut");
    expect(badge).toHaveClass("ml-2");
    expect(badge).toHaveClass("text-safe");
  });
});
