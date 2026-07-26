export type StartupRetryOptions = {
  maxAttempts?: number;
  initialDelayMs?: number;
  sleep?: (delayMs: number) => Promise<void>;
  onRetry?: (error: unknown, attempt: number, delayMs: number) => void;
};

const DEFAULT_MAX_ATTEMPTS = 5;
const DEFAULT_INITIAL_DELAY_MS = 2_000;
const MAX_DELAY_MS = 10_000;

function defaultSleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

export async function runWithStartupRetry<T>(
  operation: () => Promise<T>,
  options: StartupRetryOptions = {},
): Promise<T> {
  const maxAttempts = options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
  const initialDelayMs = options.initialDelayMs ?? DEFAULT_INITIAL_DELAY_MS;
  const sleep = options.sleep ?? defaultSleep;

  if (maxAttempts < 1) {
    throw new Error("maxAttempts must be at least 1.");
  }

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      if (attempt === maxAttempts) throw error;

      const delayMs = Math.min(initialDelayMs * (2 ** (attempt - 1)), MAX_DELAY_MS);
      options.onRetry?.(error, attempt, delayMs);
      await sleep(delayMs);
    }
  }

  throw new Error("Startup retry loop exited unexpectedly.");
}
