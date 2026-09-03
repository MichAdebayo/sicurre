import { describe, expect, it } from "vitest";
import { withOperationsRoutes } from "../../../scripts/deploy/notification-policy.mjs";
import { readFileSync } from "node:fs";

const matches = (route, labels) => route.object_matchers.every(([key, operator, value]) =>
  operator === "=" && labels[key] === value);

describe("shared Operations routing", () => {
  it("routes application and ML rules without using the empty default receiver", () => {
    const policy = withOperationsRoutes({ receiver: "empty" }, "Sicurre Operations");
    for (const labels of [{ stack: "sicurre" }, { service: "sicurre-ml", severity: "critical" }]) {
      expect(policy.routes.find((route) => matches(route, labels))?.receiver).toBe("Sicurre Operations");
    }
    expect(policy.routes.some((route) => matches(route, { service: "unrelated" }))).toBe(false);
    expect(policy.receiver).toBe("empty");
  });

  it("preserves unrelated policies and does not duplicate managed routes on repeated deployment", () => {
    const unrelated = { receiver: "Other team", object_matchers: [["team", "=", "other"]] };
    const original = { receiver: "empty", routes: [unrelated] };
    const updated = withOperationsRoutes(original, "Sicurre Operations");
    expect(withOperationsRoutes(updated, "Sicurre Operations")).toEqual(updated);
    expect(updated.routes).toContainEqual(unrelated);
    expect(original.routes).toEqual([unrelated]);
  });

  it("bounds demonstration notifications without changing normal incident repeat timing", () => {
    const app = withOperationsRoutes({}, "Sicurre Operations").routes[0];
    expect(app.group_interval).toBe("5m");
    expect(app.repeat_interval).toBe("4h");
    expect(app.routes[0].group_interval).toBe("1m");
    expect(matches(app.routes[0], { exercise: "synthetic" })).toBe(true);
  });

  it("preserves existing child routes and mute intervals", () => {
    const child = { receiver: "Incident team", object_matchers: [["severity", "=", "critical"]] };
    const updated = withOperationsRoutes({ routes: [{
      receiver: "Old", object_matchers: [["stack", "=", "sicurre"]],
      mute_time_intervals: ["maintenance"], routes: [child],
    }] }, "Sicurre Operations");
    expect(updated.routes[0].routes).toContainEqual(child);
    expect(updated.routes[0].mute_time_intervals).toEqual(["maintenance"]);
    expect(withOperationsRoutes(updated, "Sicurre Operations")).toEqual(updated);
  });

  it("migrates the old name-based route without duplicates", () => {
    const old = { object_matchers: [["alertname", "=", "Sicurre controlled operational exercise"]] };
    const policy = withOperationsRoutes({ routes: [{
      object_matchers: [["stack", "=", "sicurre"]], routes: [old],
    }] }, "Sicurre Operations");
    expect(policy.routes[0].routes).toHaveLength(1);
    expect(policy.routes[0].routes[0].object_matchers).toEqual([["exercise", "=", "synthetic"]]);
  });

  it("names each supported synthetic incident and keeps routing details out of subjects", () => {
    const config = JSON.parse(readFileSync("deploy/grafana/alerts/sicurre-alerts.json", "utf8"));
    const exercises = config.rules.filter((rule) => rule.labels?.exercise === "synthetic");
    expect(exercises.map((rule) => rule.labels.exercise_type).sort()).toEqual([
      "api_unavailable", "elevated_5xx", "high_latency",
    ]);
    for (const rule of exercises) {
      expect(rule.expression).toContain(`exercise_type="${rule.labels.exercise_type}"`);
      expect(rule.title).toContain("(synthetic test)");
      expect(rule.for).toBe("1m");
    }
    expect(new Set(exercises.map((rule) => rule.title)).size).toBe(3);
    expect(config.contactPoint.settings.subject).toContain(".CommonLabels.alertname");
    expect(config.contactPoint.settings.subject).not.toContain(".CommonLabels.Values");
    expect(config.contactPoint.disableResolveMessage).toBe(false);
  });
});
