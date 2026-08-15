import { describe, expect, it, vi } from "vitest";

import {
  RETRYABLE_STATUSES,
  TransientError,
  isRetryableStatus,
  retryDelayMs,
  withRetry,
} from "../../../scripts/deploy/retry.mjs";

/** Collect delays instead of waiting, so the suite stays fast and deterministic. */
function recordingSleep() {
  const delays = [];
  return { delays, sleep: async (ms) => void delays.push(ms) };
}

describe("retry policy", () => {
  it("retries the statuses a waking or overloaded instance returns", () => {
    // 503 is the one that failed CD run 31902227921.
    expect(isRetryableStatus(503)).toBe(true);
    expect(isRetryableStatus(502)).toBe(true);
    expect(isRetryableStatus(504)).toBe(true);
    expect(isRetryableStatus(429)).toBe(true);
  });

  it("does not retry errors that repeating cannot fix", () => {
    for (const status of [400, 401, 403, 404, 409, 412, 422]) {
      expect(isRetryableStatus(status)).toBe(false);
    }
    expect(RETRYABLE_STATUSES.has(500)).toBe(false);
  });

  it("backs off exponentially but stays capped", () => {
    const options = { baseMs: 2000, maxMs: 30000 };
    expect(retryDelayMs(1, options)).toBe(2000);
    expect(retryDelayMs(2, options)).toBe(4000);
    expect(retryDelayMs(3, options)).toBe(8000);
    expect(retryDelayMs(4, options)).toBe(16000);
    expect(retryDelayMs(5, options)).toBe(30000);
    expect(retryDelayMs(50, options)).toBe(30000);
  });
});

describe("withRetry", () => {
  it("returns immediately when the first attempt succeeds", async () => {
    const { delays, sleep } = recordingSleep();
    const operation = vi.fn(async () => "provisioned");

    await expect(withRetry(operation, { sleep })).resolves.toBe("provisioned");
    expect(operation).toHaveBeenCalledTimes(1);
    expect(delays).toEqual([]);
  });

  it("recovers once a suspended instance finishes loading", async () => {
    const { delays, sleep } = recordingSleep();
    const loading = new TransientError(
      'GET /api/datasources failed: 503 {"code":"Loading","message":'
        + '"Your instance is loading, and will be ready shortly."}',
      { status: 503 },
    );
    const operation = vi
      .fn()
      .mockRejectedValueOnce(loading)
      .mockRejectedValueOnce(loading)
      .mockResolvedValue({ status: 200, body: [] });

    const result = await withRetry(operation, { sleep, baseMs: 2000, maxMs: 30000 });

    expect(result).toEqual({ status: 200, body: [] });
    expect(operation).toHaveBeenCalledTimes(3);
    expect(delays).toEqual([2000, 4000]);
  });

  it("fails fast on a non-transient error without sleeping", async () => {
    const { delays, sleep } = recordingSleep();
    const operation = vi.fn(async () => {
      throw new Error("GET /api/datasources failed: 401 invalid token");
    });

    await expect(withRetry(operation, { sleep })).rejects.toThrow("401 invalid token");
    expect(operation).toHaveBeenCalledTimes(1);
    expect(delays).toEqual([]);
  });

  it("gives up after the attempt budget and surfaces the last error", async () => {
    const { delays, sleep } = recordingSleep();
    const operation = vi.fn(async () => {
      throw new TransientError("still loading", { status: 503 });
    });

    await expect(
      withRetry(operation, { sleep, maxAttempts: 4, baseMs: 1000, maxMs: 5000 }),
    ).rejects.toThrow("still loading");

    // Four attempts means three waits: the budget is bounded, not infinite.
    expect(operation).toHaveBeenCalledTimes(4);
    expect(delays).toEqual([1000, 2000, 4000]);
  });

  it("reports each retry so a slow deploy is explainable from the CD log", async () => {
    const { sleep } = recordingSleep();
    const onRetry = vi.fn();
    const operation = vi
      .fn()
      .mockRejectedValueOnce(new TransientError("loading", { status: 503 }))
      .mockResolvedValue("ok");

    await withRetry(operation, { sleep, onRetry, baseMs: 2000 });

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onRetry.mock.calls[0][0]).toMatchObject({ attempt: 1, delayMs: 2000 });
  });

  it("retries network faults, which arrive as thrown errors rather than statuses", async () => {
    const { delays, sleep } = recordingSleep();
    const operation = vi
      .fn()
      .mockRejectedValueOnce(
        new TransientError("POST /api/dashboards/db failed: ECONNRESET", {
          cause: new Error("ECONNRESET"),
        }),
      )
      .mockResolvedValue("ok");

    await expect(withRetry(operation, { sleep })).resolves.toBe("ok");
    expect(operation).toHaveBeenCalledTimes(2);
    expect(delays).toEqual([2000]);
  });
});
