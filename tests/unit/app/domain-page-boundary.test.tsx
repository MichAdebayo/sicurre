// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DomainPageBoundary } from "../../../src/app/components/common/domain-page-boundary";

const context = vi.hoisted(() => ({
  state: { activeDomain: "", isLoading: false, isError: false, retry: vi.fn() },
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../src/app/contexts/active-domain", () => ({ useActiveDomain: () => context.state }));

const page = <p>Domain page</p>;

afterEach(() => {
  cleanup();
  context.state = { activeDomain: "", isLoading: false, isError: false, retry: vi.fn() };
});

describe("domain page boundary", () => {
  it("shows the page skeleton while the domain list loads", () => {
    context.state = { ...context.state, isLoading: true, activeDomain: "vinse.app" };
    render(<DomainPageBoundary>{page}</DomainPageBoundary>);
    expect(screen.getByRole("status", { name: "common.loading" })).toBeInTheDocument();
    expect(screen.queryByText("Domain page")).not.toBeInTheDocument();
  });

  it("renders a page that opted in as soon as a domain is known", () => {
    context.state = { ...context.state, isLoading: true, activeDomain: "vinse.app" };
    render(<DomainPageBoundary renderWhileLoading>{page}</DomainPageBoundary>);
    expect(screen.getByText("Domain page")).toBeInTheDocument();
  });

  it("still waits when the page opted in but no domain is known yet", () => {
    context.state = { ...context.state, isLoading: true };
    render(<DomainPageBoundary renderWhileLoading>{page}</DomainPageBoundary>);
    expect(screen.getByRole("status", { name: "common.loading" })).toBeInTheDocument();
  });

  it("offers a retry when the list fails, and renders the page once it has loaded", () => {
    context.state = { ...context.state, isError: true };
    const { rerender } = render(<DomainPageBoundary>{page}</DomainPageBoundary>);
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    expect(context.state.retry).toHaveBeenCalledOnce();

    context.state = { ...context.state, isError: false, activeDomain: "vinse.app" };
    rerender(<DomainPageBoundary>{page}</DomainPageBoundary>);
    expect(screen.getByText("Domain page")).toBeInTheDocument();
  });
});
