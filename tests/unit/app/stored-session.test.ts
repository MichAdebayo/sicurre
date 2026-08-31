// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import { clearStoredSession } from "../../../src/app/lib/api";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe("clearStoredSession", () => {
  it("removes tenant data whose key is not knowable in advance", () => {
    // These are named after the data they hold, so a fixed list cannot cover
    // them. This is exactly what survived logout before.
    localStorage.setItem("sicurre:active-domain:ws-abc123", "vinse.app");
    localStorage.setItem("sicurre_domain_shield_status:vinse.app", '{"spf":{"valid":true}}');
    localStorage.setItem("sicurre_last_active_domain", "vinse.app");
    sessionStorage.setItem("sicurre:kpis:ws-abc123:vinse.app", '{"threats_phishing_count":2}');

    clearStoredSession();

    expect(localStorage.getItem("sicurre:active-domain:ws-abc123")).toBeNull();
    expect(localStorage.getItem("sicurre_domain_shield_status:vinse.app")).toBeNull();
    expect(localStorage.getItem("sicurre_last_active_domain")).toBeNull();
    expect(sessionStorage.getItem("sicurre:kpis:ws-abc123:vinse.app")).toBeNull();
  });

  it("removes the identity keys it always removed", () => {
    localStorage.setItem("sicurre_user_email", "michael@vinse.app");
    localStorage.setItem("sicurre_user_name", "Michael Adebayo");
    localStorage.setItem("sicurre_user_role", "owner");
    localStorage.setItem("sicurre_auth_provider", "password");

    clearStoredSession();

    for (const key of [
      "sicurre_user_email",
      "sicurre_user_name",
      "sicurre_user_role",
      "sicurre_auth_provider",
    ]) {
      expect(localStorage.getItem(key)).toBeNull();
    }
  });

  it("keeps device preferences, which say nothing about who was signed in", () => {
    localStorage.setItem("sicurre_theme", "dark");
    localStorage.setItem("sicurre_lang", "fr");
    localStorage.setItem("sicurre_rail_collapsed", "1");

    clearStoredSession();

    expect(localStorage.getItem("sicurre_theme")).toBe("dark");
    expect(localStorage.getItem("sicurre_lang")).toBe("fr");
    expect(localStorage.getItem("sicurre_rail_collapsed")).toBe("1");
  });

  it("leaves storage belonging to other applications alone", () => {
    localStorage.setItem("unrelated_app_token", "keep-me");

    clearStoredSession();

    expect(localStorage.getItem("unrelated_app_token")).toBe("keep-me");
  });
});
