// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DashboardRoute from "../../../src/app/routes/dashboard";
import type { AuthSession } from "../../../src/app/lib/api";

const queries = vi.hoisted(() => ({
  kpis: vi.fn(() => ({ data: { raw_records_count: 2 }, isLoading: false })),
  threats: vi.fn(() => ({ data: [], isLoading: false })),
  shield: vi.fn(() => ({ data: { score_grade: "A" } })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({ activeDomain: "own.test", domains: [{ zone_name: "own.test" }] }),
}));
vi.mock("../../../src/app/lib/api", () => ({
  useKPIStats: queries.kpis,
  useThreatLogs: queries.threats,
  useDomainShieldStatus: queries.shield,
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("customer dashboard for platform administrators", () => {
  it.each([false, true])("renders only the owned domain with platform capability %s", (isPlatformAdmin) => {
    const session = {
      workspace_id: "own-workspace", display_name: "Michael", role: "owner",
      is_platform_admin: isPlatformAdmin, onboarding_required: false,
    } as AuthSession;
    render(<DashboardRoute session={session} onGoToSettings={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("dashboard.welcome Michael");
    expect(screen.queryByText(/Console d'Administration|Pipeline de Données|Total Scannés \(Global\)/)).not.toBeInTheDocument();
    expect(queries.kpis).toHaveBeenCalledWith("own-workspace", "own.test");
    expect(queries.threats).toHaveBeenCalledWith("own.test");
    expect(queries.shield).toHaveBeenCalledWith("own.test", true);
  });
});

describe("KPI figures while the statistics load", () => {
  it("shows a quiet placeholder in each card, with the loading label only for screen readers", () => {
    queries.kpis.mockReturnValue({ data: undefined, isLoading: true });
    const session = {
      workspace_id: "own-workspace", display_name: "Michael", role: "owner",
      is_platform_admin: false, onboarding_required: false,
    } as AuthSession;
    const { container } = render(<DashboardRoute session={session} onGoToSettings={vi.fn()} />);

    const labels = screen.getAllByText("common.loading");
    expect(labels).toHaveLength(4);
    for (const label of labels) {
      expect(label).toHaveClass("sr-only");
      expect(label.closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
    }
    expect(container.querySelectorAll('[aria-busy="true"] span[aria-hidden="true"]')).toHaveLength(4);
  });
});
