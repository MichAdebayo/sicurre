import { describe, expect, it } from "vitest";

import { loginSchema, settingsSchema, signUpSchema } from "../../../src/app/lib/schemas";

describe("frontend form contracts", () => {
  it("accepts valid login and signup payloads", () => {
    expect(loginSchema.safeParse({ email: "user@example.test", password: "secret12" }).success).toBe(true);
    expect(signUpSchema.safeParse({ name: "Ada", email: "ada@example.test", password: "secret12" }).success).toBe(true);
  });

  it("rejects malformed identity inputs", () => {
    expect(loginSchema.safeParse({ email: "invalid", password: "short" }).success).toBe(false);
    expect(signUpSchema.safeParse({ name: "A", email: "invalid", password: "short" }).success).toBe(false);
  });

  it("enforces settings URL and scheduler interval", () => {
    const valid = { apiKey: "key", apiUrl: "https://api.sicurre.com/v1/classify", schedulerEnabled: true, schedulerInterval: 60 };
    expect(settingsSchema.safeParse(valid).success).toBe(true);
    expect(settingsSchema.safeParse({ ...valid, schedulerInterval: 59 }).success).toBe(false);
    expect(settingsSchema.safeParse({ ...valid, apiUrl: "not-a-url" }).success).toBe(false);
  });
});
