import { describe, expect, it } from "vitest";

import {
  getSidebarPageFromPath,
  resolveAuthorizedPage,
  sidebarPagePaths,
} from "../../../src/app/lib/navigation";

describe("authenticated navigation", () => {
  it("maps every sidebar page to a stable direct URL", () => {
    for (const [page, path] of Object.entries(sidebarPagePaths)) {
      expect(getSidebarPageFromPath(path)).toBe(page);
      expect(getSidebarPageFromPath(`${path}/`)).toBe(page);
    }
    expect(getSidebarPageFromPath("/login")).toBeNull();
  });

  it("opens administrators' own workspace unless admin access is explicitly requested", () => {
    expect(resolveAuthorizedPage("dashboard", {
      isPlatformAdmin: true,
      onboardingRequired: false,
    })).toBe("dashboard");
    expect(resolveAuthorizedPage("settings", {
      isPlatformAdmin: true,
      onboardingRequired: false,
    })).toBe("settings");
    expect(resolveAuthorizedPage(null, {
      isPlatformAdmin: true, onboardingRequired: false,
    })).toBe("dashboard");
    expect(resolveAuthorizedPage("logs", {
      isPlatformAdmin: true, onboardingRequired: true,
    })).toBe("logs");
    expect(resolveAuthorizedPage("dashboard", {
      isPlatformAdmin: true, onboardingRequired: true,
    })).toBe("settings");
    expect(resolveAuthorizedPage("support", {
      isPlatformAdmin: true, onboardingRequired: true,
    })).toBe("support");
  });

  it("locks onboarding customers to settings and rejects the admin route", () => {
    expect(resolveAuthorizedPage("threats", {
      isPlatformAdmin: false,
      onboardingRequired: true,
    })).toBe("settings");
    expect(resolveAuthorizedPage("logs", {
      isPlatformAdmin: false,
      onboardingRequired: false,
    })).toBe("dashboard");
  });
});
