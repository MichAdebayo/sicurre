// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Turnstile } from "../../../src/app/components/auth/turnstile";

const SCRIPT_ID = "cloudflare-turnstile-script";

type RenderOptions = {
  sitekey: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
};

function stubTurnstileApi() {
  const api = {
    render: vi.fn<(container: string, options: Record<string, unknown>) => string>(() => "widget-1"),
    remove: vi.fn(),
    reset: vi.fn(),
  };
  vi.stubGlobal("turnstile", api);
  return api;
}

function lastRenderOptions(api: ReturnType<typeof stubTurnstileApi>): RenderOptions {
  return api.render.mock.calls[api.render.mock.calls.length - 1][1] as RenderOptions;
}

function renderWidget(overrides: Partial<React.ComponentProps<typeof Turnstile>> = {}) {
  const props = {
    siteKey: "site-key",
    resetSignal: 0,
    onVerify: vi.fn(),
    onExpire: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
  const view = render(<Turnstile {...props} />);
  return { ...view, props };
}

beforeEach(() => {
  document.getElementById(SCRIPT_ID)?.remove();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.getElementById(SCRIPT_ID)?.remove();
});

describe("Turnstile widget", () => {
  it("renders the widget into its container when the API is already loaded", async () => {
    const api = stubTurnstileApi();
    const { props } = renderWidget();

    const group = screen.getByRole("group", { name: "Vérification anti-robot" });
    await waitFor(() => expect(api.render).toHaveBeenCalledTimes(1));
    expect(api.render).toHaveBeenCalledWith(`#${group.id}`, expect.objectContaining({
      sitekey: "site-key",
      theme: "dark",
      language: "fr",
      action: "signup",
      callback: props.onVerify,
      "expired-callback": props.onExpire,
      "error-callback": props.onError,
    }));
    expect(document.getElementById(SCRIPT_ID)).toBeNull();
  });

  it("forwards the token, the expiry and the error callbacks", async () => {
    const api = stubTurnstileApi();
    const { props } = renderWidget();
    await waitFor(() => expect(api.render).toHaveBeenCalled());

    const options = lastRenderOptions(api);
    options.callback("token-abc");
    options["expired-callback"]();
    options["error-callback"]();

    expect(props.onVerify).toHaveBeenCalledWith("token-abc");
    expect(props.onExpire).toHaveBeenCalledTimes(1);
    expect(props.onError).toHaveBeenCalledTimes(1);
  });

  it("removes the widget on unmount", async () => {
    const api = stubTurnstileApi();
    const { unmount } = renderWidget();
    await waitFor(() => expect(api.render).toHaveBeenCalled());

    unmount();
    expect(api.remove).toHaveBeenCalledWith("widget-1");
  });

  it("resets the widget when the reset signal increments, never on the first render", async () => {
    const api = stubTurnstileApi();
    const { rerender, props } = renderWidget();
    await waitFor(() => expect(api.render).toHaveBeenCalled());
    expect(api.reset).not.toHaveBeenCalled();

    rerender(<Turnstile {...props} resetSignal={1} />);
    expect(api.reset).toHaveBeenCalledWith("widget-1");
  });

  it("injects the Cloudflare script once and renders after it loads", async () => {
    const createElement = vi.spyOn(document, "createElement");
    const { props } = renderWidget();

    const script = document.getElementById(SCRIPT_ID) as HTMLScriptElement;
    expect(script).not.toBeNull();
    expect(script.src).toBe("https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit");
    expect(script.async).toBe(true);
    expect(script.defer).toBe(true);
    expect(createElement).toHaveBeenCalledWith("script");
    expect(props.onError).not.toHaveBeenCalled();

    const api = stubTurnstileApi();
    act(() => {
      script.dispatchEvent(new Event("load"));
    });
    await waitFor(() => expect(api.render).toHaveBeenCalledTimes(1));
  });

  it("reports an error when the script fails to load", async () => {
    const { props } = renderWidget();
    const script = document.getElementById(SCRIPT_ID) as HTMLScriptElement;

    act(() => {
      script.dispatchEvent(new Event("error"));
    });
    await waitFor(() => expect(props.onError).toHaveBeenCalledTimes(1));
  });

  it("waits on a script another instance already injected", async () => {
    const existing = document.createElement("script");
    existing.id = SCRIPT_ID;
    document.head.appendChild(existing);
    const createElement = vi.spyOn(document, "createElement");

    const { props } = renderWidget();
    expect(createElement).not.toHaveBeenCalledWith("script");
    expect(document.querySelectorAll(`#${SCRIPT_ID}`)).toHaveLength(1);

    const api = stubTurnstileApi();
    act(() => {
      existing.dispatchEvent(new Event("load"));
    });
    await waitFor(() => expect(api.render).toHaveBeenCalledTimes(1));
    expect(props.onError).not.toHaveBeenCalled();
  });

  it("reports an error when the shared script fails", async () => {
    const existing = document.createElement("script");
    existing.id = SCRIPT_ID;
    document.head.appendChild(existing);

    const { props } = renderWidget();
    act(() => {
      existing.dispatchEvent(new Event("error"));
    });
    await waitFor(() => expect(props.onError).toHaveBeenCalledTimes(1));
  });

  it("does not render into a container that unmounted while the script was loading", async () => {
    const { unmount } = renderWidget();
    const script = document.getElementById(SCRIPT_ID) as HTMLScriptElement;
    unmount();

    const api = stubTurnstileApi();
    act(() => {
      script.dispatchEvent(new Event("load"));
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(api.render).not.toHaveBeenCalled();
    expect(api.remove).not.toHaveBeenCalled();
  });
});
