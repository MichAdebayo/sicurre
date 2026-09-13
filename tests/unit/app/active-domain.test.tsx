// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ActiveDomainProvider,
  useActiveDomain,
} from "../../../src/app/contexts/active-domain";

const integrations = [
  { id: "1", zone_name: "vinse.app", status: "active" },
  { id: "2", zone_name: "sicurre.com", status: "active" },
];

const list = vi.hoisted(() => ({ state: { data: undefined as unknown, isLoading: false } }));

vi.mock("../../../src/app/lib/api", () => ({
  useCloudflareList: () => list.state,
}));

function Probe() {
  const { activeDomain, setActiveDomain } = useActiveDomain();
  return (
    <button type="button" onClick={() => setActiveDomain("sicurre.com")}>
      {activeDomain}
    </button>
  );
}

beforeEach(() => {
  list.state = { data: integrations, isLoading: false };
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("active domain context", () => {
  it("defaults to an owned active domain and persists an owned selection", () => {
    render(
      <ActiveDomainProvider workspaceId="workspace-1">
        <Probe />
      </ActiveDomainProvider>,
    );

    const domain = screen.getByRole("button", { name: "vinse.app" });
    fireEvent.click(domain);

    expect(screen.getByRole("button", { name: "sicurre.com" })).toBeInTheDocument();
    expect(localStorage.getItem("sicurre:active-domain:workspace-1")).toBe("sicurre.com");
  });

  it("ignores a stored domain that no longer belongs to the workspace", () => {
    localStorage.setItem("sicurre:active-domain:workspace-1", "foreign.test");

    render(
      <ActiveDomainProvider workspaceId="workspace-1">
        <Probe />
      </ActiveDomainProvider>,
    );

    expect(screen.getByRole("button", { name: "vinse.app" })).toBeInTheDocument();
  });

  it("opens on the session's domain while the list loads, without remembering it", () => {
    list.state = { data: undefined, isLoading: true };

    render(
      <ActiveDomainProvider workspaceId="workspace-1" initialDomain=" Vinse.App ">
        <Probe />
      </ActiveDomainProvider>,
    );

    expect(screen.getByRole("button", { name: "vinse.app" })).toBeInTheDocument();
    expect(localStorage.getItem("sicurre:active-domain:workspace-1")).toBeNull();
  });

  it("waits for the list when a stored choice exists, so it never opens on the wrong domain", () => {
    localStorage.setItem("sicurre:active-domain:workspace-1", "sicurre.com");
    list.state = { data: undefined, isLoading: true };

    render(
      <ActiveDomainProvider workspaceId="workspace-1" initialDomain="vinse.app">
        <Probe />
      </ActiveDomainProvider>,
    );

    expect(screen.getByRole("button")).toHaveTextContent(/^$/);
    expect(localStorage.getItem("sicurre:active-domain:workspace-1")).toBe("sicurre.com");
  });

  it("lets the loaded list decide once it arrives", () => {
    list.state = { data: undefined, isLoading: true };
    const { rerender } = render(
      <ActiveDomainProvider workspaceId="workspace-1" initialDomain="gone.test">
        <Probe />
      </ActiveDomainProvider>,
    );
    expect(screen.getByRole("button", { name: "gone.test" })).toBeInTheDocument();

    list.state = { data: integrations, isLoading: false };
    rerender(
      <ActiveDomainProvider workspaceId="workspace-1" initialDomain="gone.test">
        <Probe />
      </ActiveDomainProvider>,
    );

    expect(screen.getByRole("button", { name: "vinse.app" })).toBeInTheDocument();
    expect(localStorage.getItem("sicurre:active-domain:workspace-1")).toBe("vinse.app");
  });
});
