// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ActiveDomainProvider,
  useActiveDomain,
} from "../../../src/app/contexts/active-domain";

const integrations = [
  { id: "1", zone_name: "vinse.app", status: "active" },
  { id: "2", zone_name: "sicurre.com", status: "active" },
];

vi.mock("../../../src/app/lib/api", () => ({
  useCloudflareList: () => ({ data: integrations, isLoading: false }),
}));

function Probe() {
  const { activeDomain, setActiveDomain } = useActiveDomain();
  return (
    <button type="button" onClick={() => setActiveDomain("sicurre.com")}>
      {activeDomain}
    </button>
  );
}

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
});
