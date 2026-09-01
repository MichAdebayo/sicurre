// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
    i18n: { language: "fr" },
  }),
}));

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({ activeDomain: "vinse.app" }),
}));

const reported = vi.fn();
const quarantineItems = vi.fn();

vi.mock("../../../src/app/lib/api", () => ({
  useQuarantineItems: () => quarantineItems(),
  useReleaseQuarantine: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteQuarantine: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReleaseAndWhitelist: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReportedEmails: () => reported(),
}));

import QuarantineRoute from "../../../src/app/routes/quarantine";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function withReports(items: unknown[], isLoading = false) {
  quarantineItems.mockReturnValue({ data: [], isLoading: false });
  reported.mockReturnValue({ data: { items }, isLoading });
}

describe("forwarded reports on the quarantine page", () => {
  it("confirms receipt of a forwarded report", () => {
    withReports([
      { id: "rep-1", received_at: "2026-08-30T21:04:00Z", size_bytes: 4200, status: "received" },
    ]);

    render(<QuarantineRoute />);

    expect(screen.getByText("quarantine.reports_title")).toBeInTheDocument();
    // 4200 bytes rendered compactly, so the size reads as evidence not noise.
    expect(screen.getByText(/4\.1 Ko/)).toBeInTheDocument();
  });

  it("never renders message content, only metadata", () => {
    // The row the API layer sees carries more than the UI may show. Even if a
    // future change widened the endpoint, this page must not print a body.
    withReports([
      {
        id: "rep-1",
        received_at: "2026-08-30T21:04:00Z",
        size_bytes: 4200,
        status: "received",
        subject: "[URGENT] Confirmez votre RIB",
        body_text: "Merci de fournir votre RIB",
        storage_uri: "r2://bucket/ws-alpha/rep-1.eml",
      },
    ]);

    render(<QuarantineRoute />);

    expect(screen.queryByText(/Confirmez votre RIB/)).not.toBeInTheDocument();
    expect(screen.queryByText(/r2:\/\//)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Merci de fournir votre RIB");
  });

  it("invites a first report rather than showing an empty box", () => {
    withReports([]);

    render(<QuarantineRoute />);

    expect(screen.getByText("quarantine.reports_empty")).toBeInTheDocument();
  });

  it("shows a loading state instead of claiming there are none", () => {
    withReports([], true);

    render(<QuarantineRoute />);

    expect(screen.getByText("common.loading")).toBeInTheDocument();
    expect(screen.queryByText("quarantine.reports_empty")).not.toBeInTheDocument();
  });
});
