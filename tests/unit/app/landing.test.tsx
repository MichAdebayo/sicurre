// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LandingRoute from "../../../src/app/routes/landing";

const mocks = vi.hoisted(() => ({
  changeLanguage: vi.fn(),
  i18n: { language: "fr" },
  translate: { current: (key: string) => key },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => mocks.translate.current(key),
    i18n: { language: mocks.i18n.language, changeLanguage: mocks.changeLanguage },
  }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: { div: "div", section: "section" },
}));

vi.mock("../../../src/app/components/landing/email-gateway-animation", () => ({
  EmailGatewayAnimation: () => <p>gateway animation</p>,
}));

type ObserverCallback = (entries: Array<{ isIntersecting: boolean }>) => void;
const observers: Array<{ callback: ObserverCallback; disconnect: ReturnType<typeof vi.fn> }> = [];

class FakeIntersectionObserver {
  callback: ObserverCallback;
  disconnect = vi.fn();
  constructor(callback: ObserverCallback) {
    this.callback = callback;
    observers.push(this);
  }
  observe() {
    this.callback([{ isIntersecting: true }]);
  }
  unobserve() {}
}

function props() {
  return {
    onNavigateToLogin: vi.fn(),
    onNavigateToSignUp: vi.fn(),
    onNavigateToMentionsLegales: vi.fn(),
    onNavigateToConfidentialite: vi.fn(),
    onNavigateToContact: vi.fn(),
  };
}

beforeEach(() => {
  observers.length = 0;
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  mocks.changeLanguage.mockReset();
  mocks.i18n.language = "fr";
  mocks.translate.current = (key: string) => key;
  localStorage.clear();
  document.documentElement.lang = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Landing page", () => {
  it("exposes the header, main and footer landmarks with the brand and the hero animation", () => {
    render(<LandingRoute {...props()} />);
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("img", { name: "Sicurre Logo" })).toBeInTheDocument();
    expect(within(header).getByText("Sicurre")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("landing.footer_copyright");
    expect(screen.getByText("gateway animation")).toBeInTheDocument();
  });

  it("titles the hero with both lines and the description", () => {
    render(<LandingRoute {...props()} />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("landing.hero_title_line1");
    expect(heading).toHaveTextContent("landing.hero_title_line2");
    expect(screen.getByText("landing.hero_desc")).toBeInTheDocument();
  });

  it("drops the second hero line when the translation is empty", () => {
    mocks.translate.current = (key: string) => (key === "landing.hero_title_line2" ? "" : key);
    render(<LandingRoute {...props()} />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("landing.hero_title_line1");
    expect(heading).not.toHaveTextContent("landing.hero_title_line2");
  });

  it("routes the header, hero, integration and closing calls to action", () => {
    const handlers = props();
    render(<LandingRoute {...handlers} />);
    fireEvent.click(screen.getByRole("button", { name: "landing.nav_login" }));
    expect(handlers.onNavigateToLogin).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "landing.nav_cta" }));
    fireEvent.click(screen.getByRole("button", { name: "landing.hero_cta_primary" }));
    fireEvent.click(screen.getByRole("button", { name: "landing.integration_cta" }));
    fireEvent.click(screen.getByRole("button", { name: "landing.cta_section_trial" }));
    expect(handlers.onNavigateToSignUp).toHaveBeenCalledTimes(4);
    expect(screen.getByText("landing.cta_no_card")).toBeInTheDocument();
  });

  it("routes the footer links to the legal pages and the contact page", () => {
    const handlers = props();
    render(<LandingRoute {...handlers} />);
    const footer = screen.getByRole("contentinfo");
    fireEvent.click(within(footer).getByRole("button", { name: "landing.footer_mentions" }));
    fireEvent.click(within(footer).getByRole("button", { name: "landing.footer_privacy" }));
    fireEvent.click(within(footer).getByRole("button", { name: "landing.footer_contact" }));
    expect(handlers.onNavigateToMentionsLegales).toHaveBeenCalledTimes(1);
    expect(handlers.onNavigateToConfidentialite).toHaveBeenCalledTimes(1);
    expect(handlers.onNavigateToContact).toHaveBeenCalledTimes(1);
  });

  it("repeats the marquee items twice so the banner can loop", () => {
    render(<LandingRoute {...props()} />);
    for (const key of [
      "landing.marquee_zero_trust",
      "landing.marquee_ai",
      "landing.marquee_gmail",
      "landing.marquee_sovereign",
      "landing.marquee_rgpd",
      "landing.marquee_realtime",
    ]) {
      expect(screen.getAllByText(key)).toHaveLength(2);
    }
  });

  it("presents the three feature cards with their stat, label, title and preview", () => {
    render(<LandingRoute {...props()} />);
    expect(screen.getByRole("heading", { level: 2, name: "landing.features_title" })).toBeInTheDocument();
    expect(screen.getByText("landing.features_desc")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual([
      "landing.feat_ai_title",
      "landing.feat_remediation_title",
      "landing.feat_dns_title",
    ]);
    expect(screen.getByText("landing.feat_ai_stat")).toBeInTheDocument();
    expect(screen.getByText("landing.feat_remediation_label")).toBeInTheDocument();
    expect(screen.getByText("landing.feat_dns_desc")).toBeInTheDocument();
    expect(screen.getByText("landing.preview_verdict")).toBeInTheDocument();
    expect(screen.getByText("landing.preview_score")).toBeInTheDocument();
    expect(screen.getByText("landing.preview_action")).toBeInTheDocument();
    expect(screen.getByText("landing.preview_retention")).toBeInTheDocument();
    expect(screen.getByText("landing.preview_active")).toBeInTheDocument();
    expect(screen.getByText("SPF ✓")).toBeInTheDocument();
    expect(screen.getByText("DKIM ✓")).toBeInTheDocument();
    expect(screen.getByText("DMARC ✓")).toBeInTheDocument();
  });

  it("shows the closing section with its three trust badges", () => {
    render(<LandingRoute {...props()} />);
    expect(screen.getByRole("heading", { level: 2, name: "landing.cta_section_title" })).toBeInTheDocument();
    expect(screen.getByText("landing.cta_section_desc")).toBeInTheDocument();
    expect(screen.getByText("landing.cta_badge_rgpd")).toBeInTheDocument();
    expect(screen.getByText("landing.cta_badge_sovereign")).toBeInTheDocument();
    expect(screen.getByText("landing.cta_badge_instant")).toBeInTheDocument();
  });

  it("observes each fading section and disconnects the observers on unmount", () => {
    const { unmount } = render(<LandingRoute {...props()} />);
    expect(observers.length).toBeGreaterThan(0);
    unmount();
    for (const observer of observers) {
      expect(observer.disconnect).toHaveBeenCalledTimes(1);
    }
  });

  it("walks the four integration steps in a loop, one every 2.8 seconds", () => {
    vi.useFakeTimers();
    render(<LandingRoute {...props()} />);
    expect(screen.getByRole("heading", { level: 2, name: "landing.integration_title" })).toBeInTheDocument();
    expect(screen.getByText("landing.integration_desc")).toBeInTheDocument();
    for (const step of [1, 2, 3, 4]) {
      expect(screen.getByText(`landing.integration_step_${step}_title`)).toBeInTheDocument();
      expect(screen.getByText(`landing.integration_step_${step}_desc`)).toBeInTheDocument();
    }
    act(() => {
      vi.advanceTimersByTime(2800 * 4);
    });
    expect(screen.getByText("landing.integration_step_1_title")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(2800);
    });
    expect(screen.getByText("landing.integration_step_4_title")).toBeInTheDocument();
  });

  it("tracks the scroll position for the sticky header", () => {
    render(<LandingRoute {...props()} />);
    Object.defineProperty(window, "scrollY", { value: 40, configurable: true, writable: true });
    fireEvent.scroll(window);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true, writable: true });
    fireEvent.scroll(window);
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });
});

describe("Landing language switcher", () => {
  it("shows the French flag for the current language and opens the menu on demand", () => {
    render(<LandingRoute {...props()} />);
    const toggle = screen.getByRole("button", { name: "🇫🇷" });
    expect(screen.queryByRole("button", { name: /English/ })).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: /Français/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /English/ })).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.queryByRole("button", { name: /English/ })).not.toBeInTheDocument();
  });

  it("switches to English, remembers the choice and closes the menu", () => {
    render(<LandingRoute {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "🇫🇷" }));
    fireEvent.click(screen.getByRole("button", { name: /English/ }));
    expect(mocks.changeLanguage).toHaveBeenCalledWith("en");
    expect(localStorage.getItem("sicurre_lang")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(screen.queryByRole("button", { name: /English/ })).not.toBeInTheDocument();
  });

  it("shows the British flag when English is active and switches back to French", () => {
    mocks.i18n.language = "en";
    render(<LandingRoute {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "🇬🇧" }));
    fireEvent.click(screen.getByRole("button", { name: /Français/ }));
    expect(mocks.changeLanguage).toHaveBeenCalledWith("fr");
    expect(localStorage.getItem("sicurre_lang")).toBe("fr");
    expect(document.documentElement.lang).toBe("fr");
  });
});
