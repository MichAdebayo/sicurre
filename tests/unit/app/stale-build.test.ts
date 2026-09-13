// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  installStaleBuildReload,
  isChunkLoadError,
  reloadOnceForStaleBuild,
} from "../../../src/app/lib/stale-build";

function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
  };
}

afterEach(() => {
  sessionStorage.clear();
});

describe("isChunkLoadError", () => {
  it.each([
    "Failed to fetch dynamically imported module: https://sicurre.com/assets/settings-Dr3J7C2R.js",
    "error loading dynamically imported module: https://sicurre.com/assets/settings-Dr3J7C2R.js",
    "Importing a module script failed.",
    "Failed to load module script: Expected a JavaScript-or-Wasm module script but the server responded with a MIME type of \"text/html\".",
    "Unable to preload CSS for /assets/settings-Dr3J7C2R.css",
  ])("recognises a missing page file: %s", (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true);
    expect(isChunkLoadError(message)).toBe(true);
  });

  it("leaves ordinary render errors alone", () => {
    expect(isChunkLoadError(new Error("Cannot read properties of undefined (reading 'map')"))).toBe(false);
    expect(isChunkLoadError(undefined)).toBe(false);
    expect(isChunkLoadError({ message: "Failed to fetch dynamically imported module" })).toBe(false);
  });
});

describe("reloadOnceForStaleBuild", () => {
  it("reloads and remembers when it did", () => {
    const storage = memoryStorage();
    const reload = vi.fn();

    expect(reloadOnceForStaleBuild(storage, reload, 1_000_000)).toBe(true);

    expect(reload).toHaveBeenCalledOnce();
    expect(storage.setItem).toHaveBeenCalledWith("sicurre:stale-build-reload-at", "1000000");
  });

  it("does not reload again moments after a reload, so an outage cannot loop", () => {
    const storage = memoryStorage({ "sicurre:stale-build-reload-at": "1000000" });
    const reload = vi.fn();

    expect(reloadOnceForStaleBuild(storage, reload, 1_005_000)).toBe(false);
    expect(reload).not.toHaveBeenCalled();

    expect(reloadOnceForStaleBuild(storage, reload, 1_010_000)).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
  });

  it("does not reload when there is nowhere to remember the reload", () => {
    const reload = vi.fn();
    const blocked = {
      getItem: () => null,
      setItem: () => {
        throw new Error("storage blocked");
      },
    };

    expect(reloadOnceForStaleBuild(null, reload, 1_000_000)).toBe(false);
    expect(reloadOnceForStaleBuild(blocked, reload, 1_000_000)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("uses the session storage of the tab by default", () => {
    const reload = vi.fn();

    expect(reloadOnceForStaleBuild(undefined, reload, 2_000_000)).toBe(true);
    expect(sessionStorage.getItem("sicurre:stale-build-reload-at")).toBe("2000000");
    expect(reloadOnceForStaleBuild(undefined, reload, 2_001_000)).toBe(false);
  });
});

describe("installStaleBuildReload", () => {
  it("recovers when Vite reports that a page file failed to load", () => {
    const target = new EventTarget();
    const recover = vi.fn(() => true);

    installStaleBuildReload(target as unknown as Window, recover);
    target.dispatchEvent(new Event("other-event"));
    expect(recover).not.toHaveBeenCalled();

    target.dispatchEvent(new Event("vite:preloadError", { cancelable: true }));
    expect(recover).toHaveBeenCalledOnce();
  });
});
