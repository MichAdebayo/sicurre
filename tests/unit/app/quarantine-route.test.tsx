// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { forwardRef, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import QuarantineRoute from "../../../src/app/routes/quarantine";
import type { QuarantineItem } from "../../../src/app/lib/api";

const state = vi.hoisted(() => ({
  items: { data: undefined as unknown, isLoading: false, error: null as unknown, refetch: vi.fn() },
  reports: { data: undefined as unknown, isLoading: false },
  release: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  remove: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  whitelist: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));

vi.mock("framer-motion", () => {
  const strip = (props: Record<string, unknown>) => {
    const { initial, animate, exit, transition, whileHover, whileTap, layout, ...rest } = props;
    void initial; void animate; void exit; void transition; void whileHover; void whileTap; void layout;
    return rest;
  };
  const Div = forwardRef<HTMLDivElement, Record<string, unknown>>((props, ref) => <div ref={ref} {...strip(props)} />);
  const Span = forwardRef<HTMLSpanElement, Record<string, unknown>>((props, ref) => <span ref={ref} {...strip(props)} />);
  return {
    AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
    motion: { div: Div, span: Span },
  };
});

vi.mock("../../../src/app/contexts/active-domain", () => ({
  useActiveDomain: () => ({ activeDomain: "vinse.app" }),
}));

vi.mock("../../../src/app/lib/api", () => ({
  useQuarantineItems: () => state.items,
  useReleaseQuarantine: () => state.release,
  useDeleteQuarantine: () => state.remove,
  useReleaseAndWhitelist: () => state.whitelist,
  useReportedEmails: () => state.reports,
}));

const DAY = 24 * 60 * 60 * 1000;

const item = (overrides: Partial<QuarantineItem> = {}): QuarantineItem => ({
  id: "q-1",
  domain: "vinse.app",
  message_id: "m-1",
  subject: "Votre colis est bloqué",
  sender: "livraison@exemple.test",
  body_text: "Cliquez <a href='http://x'>ici</a> & \"payez\"\nmaintenant 'svp'",
  safety_verdict: "phishing",
  composite_score: 0.874,
  status: "quarantined",
  created_at: "2026-09-01T10:00:00.000Z",
  expires_at: new Date(Date.now() + 3 * DAY + 5 * 60 * 60 * 1000).toISOString(),
  ...overrides,
});

function setItems(items: QuarantineItem[] | undefined, extra: Partial<typeof state.items> = {}) {
  state.items = { data: items, isLoading: false, error: null, refetch: vi.fn(), ...extra };
}

/** The eye buttons carry only an icon, so they are the buttons without a name. */
function previewButtons() {
  return screen.getAllByRole("button").filter((button) => button.textContent === "");
}

function openPreview(index = 0) {
  fireEvent.click(previewButtons()[index]);
  return screen.getByRole("dialog", { name: "quarantine.safe_preview" });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  setItems(undefined);
  state.reports = { data: undefined, isLoading: false };
  state.release.isPending = false;
  state.remove.isPending = false;
  state.whitelist.isPending = false;
});

describe("quarantine route states", () => {
  it("shows the loading skeleton before claiming the quarantine is empty", () => {
    setItems(undefined, { isLoading: true });
    render(<QuarantineRoute />);

    expect(screen.getByText("quarantine.title")).toBeInTheDocument();
    expect(screen.queryByText("quarantine.no_items")).not.toBeInTheDocument();
    expect(screen.queryByText("common.error_occurred")).not.toBeInTheDocument();
  });

  it("shows the error state when the quarantine query fails", () => {
    setItems(undefined, { error: new Error("boom") });
    render(<QuarantineRoute />);

    expect(screen.getByText("common.error_occurred")).toBeInTheDocument();
    expect(screen.queryByText("quarantine.no_items")).not.toBeInTheDocument();
  });

  it("shows the empty state when nothing is quarantined", () => {
    setItems([]);
    render(<QuarantineRoute />);

    expect(screen.getByText("quarantine.no_items")).toBeInTheDocument();
    expect(screen.queryByText("quarantine.header_count")).not.toBeInTheDocument();
  });

  it("only lists phishing verdicts and counts them in the header", () => {
    setItems([
      item({ id: "q-1", sender: "phish@exemple.test" }),
      item({ id: "q-2", sender: "safe@exemple.test", safety_verdict: "safe" }),
    ]);
    render(<QuarantineRoute />);

    expect(screen.getByText("quarantine.header_count")).toBeInTheDocument();
    expect(screen.getByText("phish@exemple.test")).toBeInTheDocument();
    expect(screen.queryByText("safe@exemple.test")).not.toBeInTheDocument();
    expect(screen.getByText("Phishing")).toBeInTheDocument();
  });

  it("falls back to the no-subject label and derives the remaining time from the expiry", () => {
    setItems([
      item({ id: "q-1", subject: "", sender: "a@exemple.test" }),
      item({ id: "q-2", sender: "b@exemple.test", expires_at: "" }),
      item({ id: "q-3", sender: "c@exemple.test", expires_at: "not-a-date" }),
      item({ id: "q-4", sender: "d@exemple.test", expires_at: new Date(Date.now() - DAY).toISOString() }),
    ]);
    render(<QuarantineRoute />);

    expect(screen.getByText("threats.no_subject")).toBeInTheDocument();
    expect(screen.getByText(/^3 d \d+ h$/)).toBeInTheDocument();
    expect(screen.getAllByText("14 d")).toHaveLength(2);
    expect(screen.getByText("quarantine.expired")).toBeInTheDocument();
  });

  it("paginates nine cards per page and resets the preview when the page changes", () => {
    const many = Array.from({ length: 10 }, (_, index) => item({ id: `q-${index}`, sender: `s${index}@exemple.test` }));
    setItems(many);
    render(<QuarantineRoute />);

    expect(screen.getByText("threats.pagination")).toBeInTheDocument();
    expect(screen.getByText("s0@exemple.test")).toBeInTheDocument();
    expect(screen.queryByText("s9@exemple.test")).not.toBeInTheDocument();
    const previous = screen.getByRole("button", { name: "common.previous" });
    const next = screen.getByRole("button", { name: "common.next" });
    expect(previous).toBeDisabled();
    expect(next).toBeEnabled();

    openPreview(0);
    expect(screen.getByRole("dialog", { name: "quarantine.safe_preview" })).toBeInTheDocument();

    fireEvent.click(next);
    expect(screen.getByText("s9@exemple.test")).toBeInTheDocument();
    expect(screen.queryByText("s0@exemple.test")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "common.next" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "common.previous" }));
    expect(screen.getByText("s0@exemple.test")).toBeInTheDocument();
  });
});

describe("quarantine preview dialog", () => {
  it("opens a safe preview with the sender, subject, verdict, score and a sandboxed frame", () => {
    setItems([item()]);
    render(<QuarantineRoute />);

    const dialog = openPreview();
    expect(within(dialog).getByText("livraison@exemple.test")).toBeInTheDocument();
    expect(within(dialog).getByText("Votre colis est bloqué")).toBeInTheDocument();
    expect(within(dialog).getByText("phishing")).toBeInTheDocument();
    expect(within(dialog).getByText(/quarantine.composite_score : 87%/)).toBeInTheDocument();
    expect(within(dialog).getByText("quarantine.preview_notice")).toBeInTheDocument();
    expect(within(dialog).getByText("quarantine.action_note")).toBeInTheDocument();

    const frame = within(dialog).getByTitle("quarantine.safe_preview") as HTMLIFrameElement;
    expect(frame).toHaveAttribute("sandbox", "");
    expect(frame.getAttribute("srcdoc")).toContain("&lt;a href=&#039;http://x&#039;&gt;ici&lt;/a&gt; &amp; &quot;payez&quot;<br />maintenant");
    expect(frame.getAttribute("srcdoc")).not.toContain("<a href");
  });

  it("shows the no-subject label inside the preview when the subject is empty", () => {
    setItems([item({ subject: "" })]);
    render(<QuarantineRoute />);

    const dialog = openPreview();
    expect(within(dialog).getByText("threats.no_subject")).toBeInTheDocument();
  });

  it("closes the preview from the close button and from the Escape key", () => {
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "common.close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const dialog = openPreview();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("releases the message, confirms it and refetches the list", async () => {
    state.release.mutateAsync.mockResolvedValue({ status: "released" });
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.release" }));

    await waitFor(() => expect(state.release.mutateAsync).toHaveBeenCalledWith("q-1"));
    expect(await screen.findByRole("status")).toHaveTextContent("quarantine.release_short_success");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(state.items.refetch).toHaveBeenCalledOnce();
  });

  it("releases and whitelists the sender, then confirms it", async () => {
    state.whitelist.mutateAsync.mockResolvedValue({ status: "released" });
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.whitelist" }));

    await waitFor(() => expect(state.whitelist.mutateAsync).toHaveBeenCalledWith("q-1"));
    expect(await screen.findByRole("status")).toHaveTextContent("quarantine.whitelist_short_success");
    expect(state.items.refetch).toHaveBeenCalledOnce();
  });

  it.each([
    ["Email Sending is not enabled", "quarantine.errors.email_sending"],
    ["No destination address", "quarantine.errors.destination"],
    ["Missing Routing Addresses", "quarantine.errors.destination"],
    ["Original email content is unavailable", "quarantine.errors.original_unavailable"],
    ["Active Cloudflare integration required", "quarantine.errors.integration_required"],
    ["Something else", "quarantine.errors.delivery_failed"],
  ])("maps the release failure %j to the %s key", async (message, key) => {
    state.release.mutateAsync.mockRejectedValue(new Error(message));
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.release" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(key);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(state.items.refetch).not.toHaveBeenCalled();
  });

  it("falls back to the delivery failure key when the whitelist rejection is not an Error", async () => {
    state.whitelist.mutateAsync.mockRejectedValue("nope");
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.whitelist" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("quarantine.errors.delivery_failed");
  });

  it("dismisses the error toast from its close button", async () => {
    state.release.mutateAsync.mockRejectedValue(new Error("Something else"));
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.release" }));
    const toast = await screen.findByRole("alert");
    fireEvent.click(within(toast).getByRole("button", { name: "Fermer la notification" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("quarantine delete confirmation", () => {
  it("asks for confirmation and cancels without deleting", () => {
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.delete" }));

    const confirm = screen.getByRole("alertdialog", { name: "quarantine.confirm_delete" });
    expect(within(confirm).getByText("quarantine.confirm_delete_desc")).toBeInTheDocument();
    expect(within(confirm).getByRole("button", { name: "common.cancel" })).toHaveFocus();

    fireEvent.click(within(confirm).getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(state.remove.mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "quarantine.safe_preview" })).toBeInTheDocument();
  });

  it("deletes the message after confirmation and closes both dialogs", async () => {
    state.remove.mutateAsync.mockResolvedValue({ status: "deleted" });
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.delete" }));
    const confirm = screen.getByRole("alertdialog", { name: "quarantine.confirm_delete" });
    fireEvent.click(within(confirm).getByRole("button", { name: "quarantine.delete" }));

    await waitFor(() => expect(state.remove.mutateAsync).toHaveBeenCalledWith("q-1"));
    expect(await screen.findByRole("status")).toHaveTextContent("quarantine.delete_success");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(state.items.refetch).toHaveBeenCalledOnce();
  });

  it("surfaces the server message when the deletion fails", async () => {
    state.remove.mutateAsync.mockRejectedValue(new Error("Suppression refusée"));
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.delete" }));
    const confirm = screen.getByRole("alertdialog", { name: "quarantine.confirm_delete" });
    fireEvent.click(within(confirm).getByRole("button", { name: "quarantine.delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Suppression refusée");
    expect(state.items.refetch).not.toHaveBeenCalled();
  });

  it("falls back to the delivery failure key when the deletion rejection is not an Error", async () => {
    state.remove.mutateAsync.mockRejectedValue("nope");
    setItems([item()]);
    render(<QuarantineRoute />);

    openPreview();
    fireEvent.click(screen.getByRole("button", { name: "quarantine.delete" }));
    const confirm = screen.getByRole("alertdialog", { name: "quarantine.confirm_delete" });
    fireEvent.click(within(confirm).getByRole("button", { name: "quarantine.delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("quarantine.errors.delivery_failed");
  });
});
