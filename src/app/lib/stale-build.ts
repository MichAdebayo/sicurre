/**
 * Recovery for a page left open across a deploy.
 *
 * Every build names its page files by content hash. A tab opened before a
 * deploy still runs the previous build, so the first time it opens a page it
 * has not loaded yet it asks for a file the new build no longer has, the
 * import fails, and without this the screen stays white until a manual
 * refresh. Reloading once picks up the current build.
 */

const RELOAD_KEY = "sicurre:stale-build-reload-at";
/** A second failure this soon after a reload is a real outage, not a stale tab. */
const RELOAD_WINDOW_MS = 10_000;

type ReloadStorage = Pick<Storage, "getItem" | "setItem">;

const CHUNK_LOAD_ERROR =
  /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Expected a JavaScript(-or-Wasm)? module script|Unable to preload CSS|ChunkLoadError/i;

/** True for the errors browsers raise when a page file cannot be loaded. */
export function isChunkLoadError(error: unknown): boolean {
  if (error instanceof Error) return CHUNK_LOAD_ERROR.test(`${error.name} ${error.message}`);
  return typeof error === "string" && CHUNK_LOAD_ERROR.test(error);
}

export function reloadPage(): void {
  window.location.reload();
}

function sessionStore(): ReloadStorage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Reload once to pick up the current build. Returns false, without reloading,
 * when a reload already happened moments ago or when there is nowhere to
 * remember it, so a real outage cannot turn into a reload loop.
 */
export function reloadOnceForStaleBuild(
  storage: ReloadStorage | null = sessionStore(),
  reload: () => void = reloadPage,
  now: number = Date.now(),
): boolean {
  if (!storage) return false;
  try {
    const last = Number(storage.getItem(RELOAD_KEY) ?? 0);
    if (last && now - last < RELOAD_WINDOW_MS) return false;
    storage.setItem(RELOAD_KEY, String(now));
  } catch {
    return false;
  }
  reload();
  return true;
}

/** Vite raises `vite:preloadError` when a page file or its dependencies fail to load. */
export function installStaleBuildReload(
  target: Pick<Window, "addEventListener"> = window,
  recover: () => boolean = () => reloadOnceForStaleBuild(),
): void {
  target.addEventListener("vite:preloadError", () => {
    recover();
  });
}
