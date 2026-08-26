// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VerifyEmailRoute from "../../../src/app/routes/verify-email";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
});

describe("verification confirmation page", () => {
  it("keeps the token client-side and exposes one explicit confirmation", () => {
    window.history.replaceState({}, "", "/verify-email#token=secret-token");
    render(<VerifyEmailRoute onNavigateToLogin={vi.fn()} />);

    expect(window.location.hash).toBe("#token=secret-token");
    const confirm = screen.getByRole("link", { name: "verify_email.confirm" });
    const url = new URL(confirm.getAttribute("href")!, window.location.origin);
    expect(url.pathname).toBe("/api/auth/verify-email");
    expect(url.searchParams.get("token")).toBe("secret-token");
  });

  it("rejects a link without a token", () => {
    window.history.replaceState({}, "", "/verify-email");
    render(<VerifyEmailRoute onNavigateToLogin={vi.fn()} />);

    expect(screen.getByText("verify_email.invalid_link")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "verify_email.confirm" })).not.toBeInTheDocument();
  });
});
