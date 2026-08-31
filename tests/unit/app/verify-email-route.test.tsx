// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VerifyEmailRoute from "../../../src/app/routes/verify-email";
import { verifyEmailFromLink } from "../../../src/app/lib/email-verification";

vi.mock("../../../src/app/lib/email-verification", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../../src/app/lib/email-verification")>(),
  verifyEmailFromLink: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("automatic email verification", () => {
  it("starts verification once without another click, including StrictMode rerenders", () => {
    window.history.replaceState({}, "", "/verify-email#token=secret-token");
    const { rerender } = render(<StrictMode><VerifyEmailRoute onNavigateToLogin={vi.fn()} /></StrictMode>);

    expect(window.location.hash).toBe("#token=secret-token");
    expect(verifyEmailFromLink).toHaveBeenCalledExactlyOnceWith("secret-token", window.location.origin, `${window.location.origin}/api/auth`);
    expect(screen.getByRole("status")).toHaveTextContent("verify_email.verifying");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<StrictMode><VerifyEmailRoute onNavigateToLogin={vi.fn()} /></StrictMode>);
    expect(verifyEmailFromLink).toHaveBeenCalledTimes(1);
  });

  it("rejects a link without a token", () => {
    window.history.replaceState({}, "", "/verify-email");
    const onNavigateToLogin = vi.fn();
    render(<VerifyEmailRoute onNavigateToLogin={onNavigateToLogin} />);

    expect(screen.getByText("verify_email.invalid_link")).toBeInTheDocument();
    expect(verifyEmailFromLink).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "verify_email.back_to_login" }));
    expect(onNavigateToLogin).toHaveBeenCalledOnce();
  });
});
