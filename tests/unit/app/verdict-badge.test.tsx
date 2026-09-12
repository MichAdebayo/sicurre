// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VerdictBadge } from "../../../src/app/components/threats/verdict-badge";

const translate = vi.hoisted(() => vi.fn((key: string) => key));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate }),
}));

beforeEach(() => {
  translate.mockClear();
});

afterEach(cleanup);

describe("VerdictBadge", () => {
  it("labels a legitimate verdict with the safe tone and a shield icon", () => {
    const { container } = render(<VerdictBadge verdict="legitimate" confidence={0.97} />);
    expect(screen.getByText("threats.badge_legitimate")).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("text-safe");
    expect(container.querySelector(".lucide-shield-check")).not.toBeNull();
  });

  it("labels a phishing verdict with the error tone and an alert shield", () => {
    const { container } = render(<VerdictBadge verdict="phishing" confidence={0.91} />);
    expect(screen.getByText("threats.badge_phishing")).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("text-error");
    expect(container.querySelector(".lucide-shield-alert")).not.toBeNull();
  });

  it("treats a quarantine verdict like phishing", () => {
    const { container } = render(<VerdictBadge verdict="quarantine" confidence={0.5} />);
    expect(screen.getByText("threats.badge_phishing")).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("text-error");
  });

  it("labels a spam verdict with the spam tone and a mail warning icon", () => {
    const { container } = render(<VerdictBadge verdict="spam" confidence={0.66} />);
    expect(screen.getByText("threats.badge_spam")).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("text-spam-text");
    expect(container.querySelector(".lucide-mail-warning")).not.toBeNull();
  });

  it("shows the risk as a rounded percentage by default", () => {
    render(<VerdictBadge verdict="phishing" confidence={0.8749} />);
    expect(screen.getByText("threats.risk_value")).toBeInTheDocument();
    expect(translate).toHaveBeenCalledWith("threats.risk_value", { value: 87 });
  });

  it("hides the risk when showRisk is false", () => {
    render(<VerdictBadge verdict="phishing" confidence={0.8} showRisk={false} />);
    expect(screen.queryByText("threats.risk_value")).not.toBeInTheDocument();
  });
});
