// @vitest-environment node

import { afterEach, describe, expect, it } from "vitest";

import {
  buildTrustedOrigins,
  isProductionEnvironment,
} from "../../../auth-service/trusted-origins";

const ORIGINAL = process.env.SICURRE_ENVIRONMENT;

afterEach(() => {
  process.env.SICURRE_ENVIRONMENT = ORIGINAL;
});

describe("trusted origins", () => {
  it("never trusts a developer machine in production", () => {
    const origins = buildTrustedOrigins({
      configuredOrigin: "https://sicurre.com",
      isProduction: true,
    });

    expect(origins).toEqual(["https://sicurre.com"]);
    // credentials:true is passed alongside this list, so a dev origin here
    // would let any page on the victim's own localhost read authenticated
    // responses from production.
    expect(origins.some((o) => o.includes("5173"))).toBe(false);
  });

  it("still trusts the dev server outside production", () => {
    const origins = buildTrustedOrigins({
      configuredOrigin: "http://localhost:5173",
      isProduction: false,
    });

    expect(origins).toContain("http://localhost:5173");
    expect(origins).toContain("http://127.0.0.1:5173");
  });

  it("drops an unset frontend origin rather than emitting undefined", () => {
    expect(
      buildTrustedOrigins({ configuredOrigin: undefined, isProduction: true }),
    ).toEqual([]);
  });

  it("reads the environment flag the service already sets", () => {
    process.env.SICURRE_ENVIRONMENT = "production";
    expect(isProductionEnvironment()).toBe(true);

    process.env.SICURRE_ENVIRONMENT = "  PRODUCTION  ";
    expect(isProductionEnvironment()).toBe(true);

    process.env.SICURRE_ENVIRONMENT = "development";
    expect(isProductionEnvironment()).toBe(false);

    delete process.env.SICURRE_ENVIRONMENT;
    expect(isProductionEnvironment()).toBe(false);
  });
});
