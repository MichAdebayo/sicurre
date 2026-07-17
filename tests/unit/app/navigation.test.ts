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

  it("keeps platform administrators outside customer mailbox routes", () => {
    expect(resolveAuthorizedPage("dashboard", {
      isPlatformAdmin: true,
      onboardingRequired: false,
    })).toBe("logs");
    expect(resolveAuthorizedPage("settings", {
      isPlatformAdmin: true,
      onboardingRequired: false,
    })).toBe("settings");
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
