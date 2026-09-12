// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ActivityFeed, type ActivityItem } from "../../../src/app/components/threats/activity-feed";

const activities: ActivityItem[] = [
  { id: "a1", type: "info", title: "Analyse terminée", description: "12 e-mails analysés", timestamp: "09:12" },
  { id: "a2", type: "warning", title: "SPF incomplet", description: "Le record SPF ne couvre pas Cloudflare", timestamp: "09:40" },
  { id: "a3", type: "critical", title: "Phishing bloqué", description: "Lien vers un domaine usurpé", timestamp: "10:05" },
  { id: "a4", type: "success", title: "DMARC renforcé", description: "Politique passée en reject", timestamp: "11:30" },
];

afterEach(cleanup);

describe("ActivityFeed", () => {
  it("renders every activity with its title, description and timestamp", () => {
    render(<ActivityFeed activities={activities} />);
    for (const item of activities) {
      expect(screen.getByText(item.title)).toBeInTheDocument();
      expect(screen.getByText(item.description)).toBeInTheDocument();
      expect(screen.getByText(item.timestamp)).toBeInTheDocument();
    }
    expect(screen.queryByText("Aucune activité récente.")).not.toBeInTheDocument();
  });

  it("gives each activity type its own tone and icon", () => {
    const { container } = render(<ActivityFeed activities={activities} />);
    const entry = (title: string) => screen.getByText(title).closest(".border-l-4") as HTMLElement;

    expect(entry("Analyse terminée")).toHaveClass("border-l-primary");
    expect(entry("Analyse terminée").querySelector(".lucide-info")).not.toBeNull();

    expect(entry("SPF incomplet")).toHaveClass("border-l-secondary");
    expect(entry("SPF incomplet").querySelector(".lucide-triangle-alert")).not.toBeNull();

    expect(entry("Phishing bloqué")).toHaveClass("border-l-error");
    expect(entry("Phishing bloqué").querySelector(".lucide-octagon-alert")).not.toBeNull();

    expect(entry("DMARC renforcé")).toHaveClass("border-l-safe");
    expect(entry("DMARC renforcé").querySelector(".lucide-circle-check")).not.toBeNull();

    expect(container.querySelectorAll(".border-l-4")).toHaveLength(4);
  });

  it("shows the French empty state when there are no activities", () => {
    render(<ActivityFeed activities={[]} />);
    expect(screen.getByText("Aucune activité récente.")).toBeInTheDocument();
  });

  it("applies a custom class name to the list wrapper", () => {
    const { container } = render(<ActivityFeed activities={[]} className="max-h-96" />);
    expect(container.firstElementChild).toHaveClass("max-h-96");
    expect(container.firstElementChild).toHaveClass("flex-col");
  });
});
