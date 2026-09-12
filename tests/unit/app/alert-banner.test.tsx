// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertBanner } from "../../../src/app/components/common/alert-banner";

afterEach(cleanup);

describe("AlertBanner", () => {
  it("shows the message with a named close control, in the warning tone by default", () => {
    const { container } = render(<AlertBanner message="Votre certificat expire dans 3 jours" />);
    expect(screen.getByText("Votre certificat expire dans 3 jours")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fermer la bannière d'alerte" })).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("bg-secondary-container");
    expect(container.firstElementChild).not.toHaveClass("bg-error-container");
  });

  it("uses the critical tone when asked", () => {
    const { container } = render(<AlertBanner type="critical" message="Domaine inscrit sur liste noire" />);
    expect(container.firstElementChild).toHaveClass("bg-error-container");
    expect(container.firstElementChild).not.toHaveClass("bg-secondary-container");
  });

  it("disappears when closed and notifies the caller", () => {
    const onClose = vi.fn();
    render(<AlertBanner message="Attention" onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Fermer la bannière d'alerte" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Attention")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("can be closed without an onClose handler", () => {
    render(<AlertBanner message="Attention" />);
    fireEvent.click(screen.getByRole("button", { name: "Fermer la bannière d'alerte" }));
    expect(screen.queryByText("Attention")).not.toBeInTheDocument();
  });

  it("merges a custom class name", () => {
    const { container } = render(<AlertBanner message="Attention" className="sticky top-0" />);
    expect(container.firstElementChild).toHaveClass("sticky");
    expect(container.firstElementChild).toHaveClass("top-0");
  });
});
