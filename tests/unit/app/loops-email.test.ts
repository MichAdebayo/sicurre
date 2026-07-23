import { describe, expect, it, vi } from "vitest";

import {
  LOOPS_TRANSACTIONAL_URL,
  LoopsDeliveryError,
  sendLoopsTransactional,
} from "../../../auth-service/loops.js";

const message = {
  transactionalId: "cm-template",
  email: "user@example.test",
  dataVariables: { firstName: "Ada", verificationUrl: "https://example.test/verify" },
};

describe("Loops transactional email provider", () => {
  it("uses the canonical transactional endpoint and bearer contract", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 200 }));

    await sendLoopsTransactional(message, "secret", fetcher);

    expect(fetcher).toHaveBeenCalledOnce();
    const [url, request] = fetcher.mock.calls[0];
    expect(url).toBe(LOOPS_TRANSACTIONAL_URL);
    expect(request?.headers).toEqual({
      Authorization: "Bearer secret",
      "Content-Type": "application/json",
    });
    expect(JSON.parse(String(request?.body))).toEqual(message);
  });

  it("fails closed when provider configuration is missing", async () => {
    await expect(sendLoopsTransactional(message, "")).rejects.toThrow(LoopsDeliveryError);
    await expect(
      sendLoopsTransactional({ ...message, transactionalId: "" }, "secret"),
    ).rejects.toThrow("transactional ID");
  });

  it("surfaces provider and transport failures without exposing the body", async () => {
    const rejected = vi.fn(async () => new Response("sensitive detail", { status: 400 }));
    await expect(sendLoopsTransactional(message, "secret", rejected)).rejects.toMatchObject({
      status: 400,
      message: "Loops rejected the transactional email with HTTP 400",
    });

    const offline = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    await expect(sendLoopsTransactional(message, "secret", offline)).rejects.toThrow(
      "before receiving a response",
    );
  });
});
