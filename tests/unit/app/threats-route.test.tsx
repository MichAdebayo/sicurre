// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ThreatsRoute from "../../../src/app/routes/threats";
import type { ThreatLog, ThreatPage, ThreatQuery } from "../../../src/app/lib/api";

const state = vi.hoisted(() => ({
  page: { data: undefined as unknown, isLoading: false, error: null as unknown },
  chart: undefined as unknown,
  reportAddress: "",
  activeDomain: "vinse.app",
  language: "fr",
  isPending: false,
  mutateAsync: vi.fn(),
  pageCalls: [] as Array<{ domain: string; query: Record<string, unknown> }>,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: state.language } }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
  motion: { div: "div", span: "span" },
}));

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({ activeDomain: state.activeDomain }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useThreatPage: (domain: string, query: Record<string, unknown>) => {
    state.pageCalls.push({ domain, query });
    return state.page;
  },
  useThreatLogs: () => ({ data: state.chart }),
  useSetThreatVisibility: () => ({ mutateAsync: state.mutateAsync, isPending: state.isPending }),
  useReportAddress: () => ({ data: state.reportAddress ? { address: state.reportAddress } : undefined }),
}));

const threat = (overrides: Partial<ThreatLog> = {}): ThreatLog => ({
  id: "t-1",
  message_id: "m-1",
  subject: "Facture en attente",
  sender: "compta@exemple.test",
  body_preview: "",
  verdict: "phishing",
  confidence: 0.93,
  status: "active",
  received_at: "2026-03-02T10:00:00.000Z",
  latency_ms: 420,
  privacy_reference: "MSG-0001",
  content_redacted: true,
  ...overrides,
});

const page = (items: ThreatLog[], overrides: Partial<ThreatPage> = {}): ThreatPage => ({
  items,
  page: 1,
  page_size: 10,
  total: items.length,
  pages: 1,
  ...overrides,
});

const lastQuery = (): ThreatQuery => state.pageCalls[state.pageCalls.length - 1].query as ThreatQuery;

const isoAt = (date: Date) => date.toISOString();

const daysAgo = (days: number, hour = 12) => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  date.setHours(hour, 0, 0, 0);
  return date;
};

beforeEach(() => {
  state.page = { data: page([threat()]), isLoading: false, error: null };
  state.chart = undefined;
  state.reportAddress = "";
  state.activeDomain = "vinse.app";
  state.language = "fr";
  state.isPending = false;
  state.pageCalls = [];
  state.mutateAsync.mockReset();
  state.mutateAsync.mockResolvedValue({ updated: 1, hidden: true });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("threat journal listing", () => {
  it("lists the processed events with their privacy reference, verdict and risk", () => {
    state.page.data = page([
      threat(),
      threat({ id: "t-2", privacy_reference: "MSG-0002", verdict: "legitimate", confidence: 0.12, content_redacted: false }),
    ]);

    render(<ThreatsRoute />);

    expect(screen.getByRole("heading", { level: 1, name: "threats.title" })).toBeInTheDocument();
    expect(screen.getByText("threats.subtitle")).toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getAllByText("threats.processed_reference")).toHaveLength(2);
    expect(within(table).getByText("threats.content_discarded")).toBeInTheDocument();
    expect(within(table).getByText("threats.content_quarantined")).toBeInTheDocument();
    expect(within(table).getByText("threats.badge_phishing")).toBeInTheDocument();
    expect(within(table).getByText("threats.badge_legitimate")).toBeInTheDocument();
    expect(within(table).getByText("93 %")).toBeInTheDocument();
    expect(within(table).getByText("12 %")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox", { name: "threats.select_item" })).toHaveLength(2);

    expect(state.pageCalls[0].domain).toBe("vinse.app");
    expect(lastQuery()).toEqual({
      page: 1,
      pageSize: 10,
      verdict: "all",
      dateRange: "all",
      search: "",
      hidden: false,
    });
    expect(screen.queryByText("threats.pagination")).not.toBeInTheDocument();
  });

  it("shows a skeleton while loading, an error message on failure and an empty state without events", () => {
    state.page = { data: undefined, isLoading: true, error: null };
    const first = render(<ThreatsRoute />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("threats.no_records")).not.toBeInTheDocument();
    expect(screen.queryByText("common.error_occurred")).not.toBeInTheDocument();
    first.unmount();

    state.page = { data: undefined, isLoading: false, error: new Error("boom") };
    const second = render(<ThreatsRoute />);
    expect(screen.getByText("common.error_occurred")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    second.unmount();

    state.page = { data: page([]), isLoading: false, error: null };
    render(<ThreatsRoute />);
    expect(screen.getByText("threats.no_records")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("filters and pagination", () => {
  it("sends the verdict, date range, search and hidden filters to the query and returns to the first page", async () => {
    state.page.data = page([threat()], { total: 25, pages: 3 });
    render(<ThreatsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "common.next" }));
    expect(lastQuery().page).toBe(2);

    fireEvent.click(screen.getByRole("button", { name: "threats.badge_spam" }));
    expect(lastQuery()).toEqual(expect.objectContaining({ verdict: "spam", page: 1 }));

    fireEvent.click(screen.getByRole("button", { name: "common.next" }));
    fireEvent.change(screen.getByRole("combobox", { name: "threats.date_filter_label" }), { target: { value: "7d" } });
    expect(lastQuery()).toEqual(expect.objectContaining({ dateRange: "7d", page: 1 }));

    fireEvent.click(screen.getByRole("button", { name: "common.next" }));
    fireEvent.change(screen.getByPlaceholderText("common.search"), { target: { value: "facture" } });
    await waitFor(() => expect(lastQuery()).toEqual(expect.objectContaining({ search: "facture", page: 1 })));

    fireEvent.click(screen.getByRole("button", { name: "common.next" }));
    fireEvent.click(screen.getByRole("button", { name: "threats.show_hidden" }));
    expect(screen.getByRole("button", { name: "threats.show_visible" })).toBeInTheDocument();
    await waitFor(() => expect(lastQuery()).toEqual(expect.objectContaining({ hidden: true, page: 1 })));

    fireEvent.click(screen.getByRole("button", { name: "threats.all" }));
    expect(lastQuery().verdict).toBe("all");
  });

  it("walks through the pages and disables the edge controls", () => {
    state.page.data = page([threat()], { total: 25, pages: 3 });
    render(<ThreatsRoute />);

    expect(screen.getByText("threats.pagination")).toBeInTheDocument();
    const previous = () => screen.getByRole("button", { name: "common.previous" });
    const next = () => screen.getByRole("button", { name: "common.next" });

    expect(previous()).toBeDisabled();
    expect(next()).toBeEnabled();

    fireEvent.click(next());
    expect(lastQuery().page).toBe(2);
    expect(previous()).toBeEnabled();

    fireEvent.click(next());
    expect(lastQuery().page).toBe(3);
    expect(next()).toBeDisabled();

    fireEvent.click(previous());
    expect(lastQuery().page).toBe(2);
  });

  it("returns to the first page when the active domain changes", async () => {
    state.page.data = page([threat()], { total: 25, pages: 3 });
    const view = render(<ThreatsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "common.next" }));
    expect(lastQuery()).toEqual(expect.objectContaining({ page: 2 }));

    state.activeDomain = "sicurre.com";
    view.rerender(<ThreatsRoute />);

    await waitFor(() => expect(state.pageCalls[state.pageCalls.length - 1]).toEqual(
      expect.objectContaining({ domain: "sicurre.com", query: expect.objectContaining({ page: 1 }) }),
    ));
  });
});

describe("hiding and restoring events", () => {
  it("hides the selected events and confirms with a dismissable toast", async () => {
    state.page.data = page([threat(), threat({ id: "t-2", privacy_reference: "MSG-0002" })]);
    render(<ThreatsRoute />);

    expect(screen.queryByText("threats.selected_count")).not.toBeInTheDocument();

    const [first] = screen.getAllByRole("checkbox", { name: "threats.select_item" });
    fireEvent.click(first);
    expect(first).toBeChecked();
    expect(screen.getByText("threats.selected_count")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "threats.hide_selected" }));

    await waitFor(() => expect(state.mutateAsync).toHaveBeenCalledWith({ ids: ["t-1"], hidden: true }));
    const toast = await screen.findByRole("status");
    expect(toast).toHaveTextContent("threats.hide_success");
    expect(screen.queryByText("threats.selected_count")).not.toBeInTheDocument();
    expect(first).not.toBeChecked();

    fireEvent.click(within(toast).getByRole("button", { name: "Fermer la notification" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("selects and unselects the whole page from the header checkbox", () => {
    state.page.data = page([threat(), threat({ id: "t-2", privacy_reference: "MSG-0002" })]);
    render(<ThreatsRoute />);

    const selectPage = screen.getByRole("checkbox", { name: "threats.select_page" });
    expect(selectPage).not.toBeChecked();

    fireEvent.click(selectPage);
    expect(selectPage).toBeChecked();
    screen.getAllByRole("checkbox", { name: "threats.select_item" }).forEach((box) => expect(box).toBeChecked());
    expect(screen.getByText("threats.selected_count")).toBeInTheDocument();

    fireEvent.click(selectPage);
    expect(selectPage).not.toBeChecked();
    screen.getAllByRole("checkbox", { name: "threats.select_item" }).forEach((box) => expect(box).not.toBeChecked());
    expect(screen.queryByText("threats.selected_count")).not.toBeInTheDocument();
  });

  it("unselects a single row again and drops the selection bar", () => {
    render(<ThreatsRoute />);

    const box = screen.getByRole("checkbox", { name: "threats.select_item" });
    fireEvent.click(box);
    expect(screen.getByText("threats.selected_count")).toBeInTheDocument();
    fireEvent.click(box);
    expect(box).not.toBeChecked();
    expect(screen.queryByText("threats.selected_count")).not.toBeInTheDocument();
  });

  it("restores the selected events from the hidden view", async () => {
    state.mutateAsync.mockResolvedValue({ updated: 1, hidden: false });
    render(<ThreatsRoute />);

    fireEvent.click(screen.getByRole("button", { name: "threats.show_hidden" }));
    await waitFor(() => expect(lastQuery().hidden).toBe(true));

    fireEvent.click(screen.getByRole("checkbox", { name: "threats.select_page" }));
    fireEvent.click(screen.getByRole("button", { name: "threats.restore_selected" }));

    await waitFor(() => expect(state.mutateAsync).toHaveBeenCalledWith({ ids: ["t-1"], hidden: false }));
    expect(await screen.findByRole("status")).toHaveTextContent("threats.restore_success");
  });

  it("blocks the visibility action while a request is in flight", () => {
    state.isPending = true;
    render(<ThreatsRoute />);

    fireEvent.click(screen.getByRole("checkbox", { name: "threats.select_item" }));
    expect(screen.getByRole("button", { name: "threats.hide_selected" })).toBeDisabled();
  });
});

describe("reporting a missed phishing", () => {
  it("does not offer the report address before it is known", () => {
    render(<ThreatsRoute />);
    expect(screen.queryByText("threats.report_missed_title")).not.toBeInTheDocument();
  });

  it("copies the report address to the clipboard and confirms", async () => {
    state.reportAddress = "signalement@sicurre.com";
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });

    render(<ThreatsRoute />);

    fireEvent.click(screen.getByText("threats.report_missed_title"));
    expect(screen.getByText("threats.report_missed_description")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "threats.copy_address" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("signalement@sicurre.com"));
    expect(await screen.findByRole("status")).toHaveTextContent("threats.report_address_copied");
  });
});

describe("CSV export", () => {
  it("downloads the listed events as a CSV report", async () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:sicurre/report");
    vi.stubGlobal("URL", Object.assign(Object.create(URL), { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    render(<ThreatsRoute />);
    fireEvent.click(screen.getByRole("button", { name: "threats.export_report" }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    expect(blob.type).toBe("text/csv;charset=utf-8;");
    const csv = await blob.text();
    expect(csv.split("\n")[0]).toBe("Date,Sender,Subject,Verdict,Confidence,Status");
    expect(csv).toContain('"2026-03-02T10:00:00.000Z","compta@exemple.test","Facture en attente","phishing","0.93","active"');
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("does nothing when there is nothing to export", () => {
    state.page.data = page([]);
    const createObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(Object.create(URL), { createObjectURL, revokeObjectURL: vi.fn() }));

    render(<ThreatsRoute />);
    fireEvent.click(screen.getByRole("button", { name: "threats.export_report" }));

    expect(createObjectURL).not.toHaveBeenCalled();
  });
});

describe("latency chart", () => {
  const circles = () => screen.getByRole("img", { name: "threats.latency_title" }).querySelectorAll("circle");

  it("explains that nothing is measured yet when no event carries a latency", () => {
    state.chart = [threat({ latency_ms: 0 }), threat({ id: "t-2", latency_ms: undefined })];
    render(<ThreatsRoute />);

    expect(screen.getByText("threats.latency_title")).toBeInTheDocument();
    expect(screen.getByText("threats.latency_description")).toBeInTheDocument();
    expect(screen.getByText("threats.latency_measure")).toBeInTheDocument();
    expect(screen.getByText("threats.latency_empty")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("plots one point per measured day over the whole history and shows the nearest point on hover", () => {
    state.chart = [
      threat({ id: "a1", received_at: "2026-03-02T09:00:00.000Z", latency_ms: 400 }),
      threat({ id: "a2", received_at: "2026-03-02T15:00:00.000Z", latency_ms: 600 }),
      threat({ id: "b1", received_at: "2026-03-03T12:00:00.000Z", latency_ms: 0 }),
      threat({ id: "c1", received_at: "2026-03-05T12:00:00.000Z", latency_ms: 300 }),
    ];
    render(<ThreatsRoute />);

    const chart = screen.getByRole("img", { name: "threats.latency_title" });
    expect(screen.queryByText("threats.latency_empty")).not.toBeInTheDocument();
    expect(circles()).toHaveLength(2);
    expect(within(chart).getByText("600")).toBeInTheDocument();
    expect(within(chart).getByText("0")).toBeInTheDocument();
    expect(within(chart).getByText("ms")).toBeInTheDocument();
    expect(screen.queryByText("threats.latency_average")).not.toBeInTheDocument();

    const surface = chart.parentElement as HTMLElement;
    surface.getBoundingClientRect = () => ({ left: 0, width: 1040, top: 0, height: 256, right: 1040, bottom: 256, x: 0, y: 0, toJSON: () => ({}) });

    fireEvent.mouseMove(surface, { clientX: 70 });
    expect(screen.getByText("threats.latency_average")).toBeInTheDocument();
    expect(screen.getByText("500 ms")).toBeInTheDocument();
    expect(screen.getByText("threats.email_count").nextElementSibling).toHaveTextContent("2");

    fireEvent.mouseMove(surface, { clientX: 975 });
    expect(screen.getByText("300 ms")).toBeInTheDocument();
    expect(screen.getByText("threats.email_count").nextElementSibling).toHaveTextContent("1");

    fireEvent.mouseLeave(surface);
    expect(screen.queryByText("threats.latency_average")).not.toBeInTheDocument();
  });

  it("labels the axis and the timestamps in the language of the interface", () => {
    state.chart = [threat({ received_at: "2026-03-02T12:00:00.000Z", latency_ms: 300 })];
    state.page.data = page([threat({ received_at: "2026-03-02T12:00:00.000Z" })]);
    const frenchLabel = new Date("2026-03-02T12:00:00").toLocaleDateString("fr-FR", { month: "short", day: "numeric" });
    const englishLabel = new Date("2026-03-02T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const englishStamp = new Date("2026-03-02T12:00:00.000Z").toLocaleString("en-US", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    expect(frenchLabel).not.toBe(englishLabel);

    const view = render(<ThreatsRoute />);
    expect(screen.getByText(frenchLabel)).toBeInTheDocument();
    expect(screen.queryByText(englishStamp)).not.toBeInTheDocument();

    state.language = "en";
    view.rerender(<ThreatsRoute />);
    expect(screen.getByText(englishLabel)).toBeInTheDocument();
    expect(screen.getByText(englishStamp)).toBeInTheDocument();

    const select = () => screen.getByRole("combobox", { name: "threats.date_filter_label" });
    (["today", "7d", "month", "last_month"] as const).forEach((range) => {
      fireEvent.change(select(), { target: { value: range } });
      expect(lastQuery().dateRange).toBe(range);
    });
  });

  it("switches to hourly points for today and thins the axis labels", () => {
    const now = new Date();
    state.chart = [threat({ received_at: isoAt(now), latency_ms: 250 })];
    render(<ThreatsRoute />);

    fireEvent.change(screen.getByRole("combobox", { name: "threats.date_filter_label" }), { target: { value: "today" } });

    expect(screen.getByRole("img", { name: "threats.latency_title" })).toBeInTheDocument();
    expect(circles()).toHaveLength(1);
    const axis = screen.getByRole("img").parentElement?.lastElementChild as HTMLElement;
    expect(axis.children.length).toBeGreaterThanOrEqual(6);
    expect(axis.children.length).toBeLessThan(24);
  });

  it("covers the last seven days, the current month and the previous month", () => {
    const now = new Date();
    const previousMonthDay = new Date(now.getFullYear(), now.getMonth() - 1, 10, 12, 0, 0, 0);
    state.chart = [
      threat({ id: "w1", received_at: isoAt(daysAgo(2)), latency_ms: 800 }),
      threat({ id: "m1", received_at: isoAt(daysAgo(0)), latency_ms: 120 }),
      threat({ id: "p1", received_at: isoAt(previousMonthDay), latency_ms: 90 }),
    ];
    render(<ThreatsRoute />);
    const select = () => screen.getByRole("combobox", { name: "threats.date_filter_label" });
    const axis = () => screen.getByRole("img").parentElement?.lastElementChild as HTMLElement;

    fireEvent.change(select(), { target: { value: "7d" } });
    expect(axis().children).toHaveLength(7);
    expect(circles().length).toBeGreaterThanOrEqual(1);

    fireEvent.change(select(), { target: { value: "month" } });
    expect(axis().children.length).toBeGreaterThanOrEqual(1);
    expect(circles().length).toBeGreaterThanOrEqual(1);

    fireEvent.change(select(), { target: { value: "last_month" } });
    const daysInPreviousMonth = new Date(now.getFullYear(), now.getMonth(), 0).getDate();
    expect(axis().children.length).toBeGreaterThanOrEqual(6);
    expect(axis().children.length).toBeLessThanOrEqual(daysInPreviousMonth);
    expect(circles()).toHaveLength(1);
  });
});
