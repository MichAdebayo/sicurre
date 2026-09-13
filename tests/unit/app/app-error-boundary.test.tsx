// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "../../../src/app/components/common/app-error-boundary";

const stale = vi.hoisted(() => ({
  reloadOnceForStaleBuild: vi.fn(() => true),
  reloadPage: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../src/app/lib/stale-build", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../src/app/lib/stale-build")>();
  return { ...actual, reloadOnceForStaleBuild: stale.reloadOnceForStaleBuild, reloadPage: stale.reloadPage };
});

function Throws({ error }: { error: unknown }): never {
  throw error;
}

beforeEach(() => {
  // React logs every caught render error; the boundary is the thing under test.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  stale.reloadOnceForStaleBuild.mockClear();
  stale.reloadPage.mockClear();
});

describe("AppErrorBoundary", () => {
  it("renders the application while nothing fails", () => {
    render(
      <AppErrorBoundary>
        <p>Application Sicurre</p>
      </AppErrorBoundary>,
    );

    expect(screen.getByText("Application Sicurre")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reloads once when a page file from an earlier deploy is missing, instead of a white screen", () => {
    const error = new TypeError(
      "Failed to fetch dynamically imported module: https://sicurre.com/assets/settings-Dr3J7C2R.js",
    );

    render(
      <AppErrorBoundary>
        <Throws error={error} />
      </AppErrorBoundary>,
    );

    expect(stale.reloadOnceForStaleBuild).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert")).toHaveTextContent("common.page_load_error");
  });

  it("shows a message and a reload button for any other render failure, without reloading on its own", () => {
    render(
      <AppErrorBoundary>
        <Throws error={new Error("Cannot read properties of undefined (reading 'map')")} />
      </AppErrorBoundary>,
    );

    expect(stale.reloadOnceForStaleBuild).not.toHaveBeenCalled();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("common.page_load_error");

    fireEvent.click(screen.getByRole("button", { name: "common.reload" }));
    expect(stale.reloadPage).toHaveBeenCalledOnce();
  });

  it("still shows the fallback when something throws a value that is not an Error", () => {
    render(
      <AppErrorBoundary>
        <Throws error={null} />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
