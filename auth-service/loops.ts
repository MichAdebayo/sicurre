export const LOOPS_TRANSACTIONAL_URL = "https://app.loops.so/api/v1/transactional";

export type LoopsTransactionalMessage = {
  transactionalId: string;
  email: string;
  dataVariables: Record<string, string>;
};

export class LoopsDeliveryError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "LoopsDeliveryError";
  }
}

export async function sendLoopsTransactional(
  message: LoopsTransactionalMessage,
  apiKey: string | undefined = process.env.LOOPS_API_KEY?.trim(),
  fetcher: typeof fetch = fetch,
): Promise<void> {
  if (!apiKey) {
    throw new LoopsDeliveryError("Loops API key is not configured");
  }
  if (!message.transactionalId.trim()) {
    throw new LoopsDeliveryError("Loops transactional ID is not configured");
  }

  let response: Response;
  try {
    response = await fetcher(LOOPS_TRANSACTIONAL_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(message),
      signal: AbortSignal.timeout(10_000),
    });
  } catch (error) {
    const deliveryError = new LoopsDeliveryError(
      "Loops request failed before receiving a response",
    );
    deliveryError.cause = error;
    throw deliveryError;
  }

  if (!response.ok) {
    throw new LoopsDeliveryError(
      `Loops rejected the transactional email with HTTP ${response.status}`,
      response.status,
    );
  }
}
