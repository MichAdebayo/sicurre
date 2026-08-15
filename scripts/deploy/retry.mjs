/**
 * Bounded retry for deployment-time HTTP calls.
 *
 * Grafana Cloud suspends idle free-tier instances and answers with
 * `503 {"code":"Loading"}` while one wakes up. That is a transient state, not a
 * deployment failure, but without a retry it turns an otherwise successful
 * release red and forces a manual re-run.
 *
 * Only conditions that can plausibly clear on their own are retried. Auth,
 * payload, and not-found errors fail immediately, because repeating them just
 * delays the real error.
 */

/** HTTP statuses that may succeed if the same request is repeated. */
export const RETRYABLE_STATUSES = new Set([429, 502, 503, 504]);

/** Raised for a failure worth repeating. Anything else propagates at once. */
export class TransientError extends Error {
  constructor(message, { status, cause } = {}) {
    super(message);
    this.name = "TransientError";
    this.status = status;
    this.cause = cause;
  }
}

export function isRetryableStatus(status) {
  return RETRYABLE_STATUSES.has(status);
}

/**
 * Exponential backoff capped at `maxMs`, so a long outage does not turn into an
 * unbounded wait. Attempt numbers are 1-based.
 */
export function retryDelayMs(attempt, { baseMs = 2000, maxMs = 30000 } = {}) {
  const exponential = baseMs * 2 ** (Math.max(attempt, 1) - 1);
  return Math.min(exponential, maxMs);
}

const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Run `operation` until it succeeds, raises a non-transient error, or exhausts
 * `maxAttempts`. `sleep` is injectable so tests do not wait in real time.
 */
export async function withRetry(operation, options = {}) {
  const {
    maxAttempts = 6,
    baseMs = 2000,
    maxMs = 30000,
    sleep = defaultSleep,
    onRetry = () => {},
  } = options;

  for (let attempt = 1; ; attempt += 1) {
    try {
      return await operation(attempt);
    } catch (error) {
      const retryable = error instanceof TransientError;
      if (!retryable || attempt >= maxAttempts) throw error;
      const delayMs = retryDelayMs(attempt, { baseMs, maxMs });
      onRetry({ attempt, maxAttempts, delayMs, error });
      await sleep(delayMs);
    }
  }
}
