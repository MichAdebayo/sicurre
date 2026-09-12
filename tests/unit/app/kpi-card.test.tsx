// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { KPICard } from "../../../src/app/components/ui/kpi-card";

afterEach(cleanup);

describe("KPICard", () => {
  it("renders the title and the value without an icon or a trend", () => {
    render(<KPICard title="E-mails analysés" value={1284} />);
    expect(screen.getByText("E-mails analysés")).toBeInTheDocument();
    expect(screen.getByText("1284")).toBeInTheDocument();
    expect(screen.queryByTestId("kpi-icon")).not.toBeInTheDocument();
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
  });

  it("renders the icon when one is provided", () => {
    render(<KPICard title="Menaces" value="12" icon={<svg data-testid="kpi-icon" />} />);
    expect(screen.getByTestId("kpi-icon")).toBeInTheDocument();
  });

  it("shows a positive trend in the safe tone with an upward arrow and its label", () => {
    const { container } = render(
      <KPICard title="Taux de détection" value="98 %" trend={{ value: 4, isPositive: true, label: "vs. semaine dernière" }} />,
    );
    const trend = screen.getByText("4%");
    expect(trend).toHaveClass("text-safe");
    expect(trend).not.toHaveClass("text-error");
    expect(screen.getByText("vs. semaine dernière")).toBeInTheDocument();
    expect(container.querySelector(".lucide-arrow-up-right")).not.toBeNull();
    expect(container.querySelector(".lucide-arrow-down-right")).toBeNull();
  });

  it("shows a negative trend in the error tone with a downward arrow and no label", () => {
    const { container } = render(
      <KPICard title="Faux positifs" value={3} trend={{ value: 12, isPositive: false }} />,
    );
    const trend = screen.getByText("12%");
    expect(trend).toHaveClass("text-error");
    expect(container.querySelector(".lucide-arrow-down-right")).not.toBeNull();
    expect(container.querySelector(".lucide-arrow-up-right")).toBeNull();
    expect(screen.queryByText(/semaine/)).not.toBeInTheDocument();
  });

  it("passes a custom class name to the underlying card", () => {
    const { container } = render(<KPICard title="Score" value="A" className="col-span-2" />);
    expect(container.firstElementChild).toHaveClass("col-span-2");
    expect(container.firstElementChild).toHaveClass("rounded-xl");
  });
});
