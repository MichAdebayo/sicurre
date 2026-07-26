import { describe, expect, it, vi } from "vitest";

import { runWithStartupRetry } from "../../../auth-service/startup.js";

describe("Better Auth startup retry", () => {
  it("recovers from transient database connection failures", async () => {
    const operation = vi.fn()
      .mockRejectedValueOnce(new Error("connection timeout"))
      .mockRejectedValueOnce(new Error("connection timeout"))
      .mockResolvedValue("ready");
    const sleep = vi.fn().mockResolvedValue(undefined);
    const onRetry = vi.fn();

    await expect(runWithStartupRetry(operation, {
      sleep,
      onRetry,
    })).resolves.toBe("ready");

    expect(operation).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenNthCalledWith(1, 2_000);
    expect(sleep).toHaveBeenNthCalledWith(2, 4_000);
    expect(onRetry).toHaveBeenCalledTimes(2);
  });

  it("surfaces the final error after bounded retries", async () => {
    const failure = new Error("database unavailable");
    const operation = vi.fn().mockRejectedValue(failure);

    await expect(runWithStartupRetry(operation, {
      maxAttempts: 3,
      initialDelayMs: 1,
      sleep: vi.fn().mockResolvedValue(undefined),
    })).rejects.toBe(failure);

    expect(operation).toHaveBeenCalledTimes(3);
  });
});
