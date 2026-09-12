// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SupportRoute from "../../../src/app/routes/support";
import type { AuthSession } from "../../../src/app/lib/api";

const mocks = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  state: { isPending: false },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { ticket?: string }) => (options?.ticket ? `${key}:${options.ticket}` : key),
  }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: { div: "div", span: "span" },
}));

vi.mock("../../../src/app/lib/api", () => ({
  useCreateSupportRequest: () => ({ mutateAsync: mocks.mutateAsync, isPending: mocks.state.isPending }),
}));

const session: AuthSession = {
  id: "u1",
  email: "jean@entreprise.com",
  display_name: "Jean Dupont",
  role: "owner",
  workspace_id: "w1",
  workspace_name: "Entreprise",
  is_platform_admin: false,
  has_cloudflare_integration: true,
  threat_count: 0,
  onboarding_required: false,
  sla_latency_ms: 2000,
};

function fields() {
  return {
    name: screen.getByPlaceholderText("support.full_name_placeholder") as HTMLInputElement,
    email: screen.getByPlaceholderText("jean@entreprise.com") as HTMLInputElement,
    category: screen.getByRole("combobox") as HTMLSelectElement,
    message: screen.getByPlaceholderText("support.message_placeholder") as HTMLTextAreaElement,
    submit: screen.getByRole("button", { name: "support.submit" }),
  };
}

function fillForm({ name = "Jean Dupont", email = "jean@entreprise.com", message = "Le SPF est refusé" } = {}) {
  const form = fields();
  fireEvent.change(form.name, { target: { value: name } });
  fireEvent.change(form.email, { target: { value: email } });
  fireEvent.change(form.message, { target: { value: message } });
  return form;
}

beforeEach(() => {
  mocks.mutateAsync.mockReset();
  mocks.state.isPending = false;
});

afterEach(cleanup);

describe("Support page", () => {
  it("titles the page and offers the direct contact card", () => {
    render(<SupportRoute />);
    expect(screen.getByRole("heading", { level: 1, name: "support.title" })).toBeInTheDocument();
    expect(screen.getByText("support.subtitle")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "support.form_title" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "support.direct_contact" })).toBeInTheDocument();
    expect(screen.getByText("support.direct_contact_desc")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("starts empty without a session and lists the five categories with DNS preselected", () => {
    render(<SupportRoute />);
    const form = fields();
    expect(form.name.value).toBe("");
    expect(form.email.value).toBe("");
    expect(form.category.value).toBe("dns");
    expect(within(form.category).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "support.category_incident",
      "support.category_dns",
      "support.category_billing",
      "support.category_feedback",
      "support.category_other",
    ]);
  });

  it("prefills the requester from the signed-in session", () => {
    render(<SupportRoute session={session} />);
    const form = fields();
    expect(form.name.value).toBe("Jean Dupont");
    expect(form.email.value).toBe("jean@entreprise.com");
  });

  it("sends the trimmed request with the chosen category and confirms with the short ticket id", async () => {
    mocks.mutateAsync.mockResolvedValue({ id: "abcdef12-3456-7890", status: "open", created_at: "2026-09-12T10:00:00Z" });
    render(<SupportRoute />);
    const form = fillForm({ name: "  Jean Dupont ", email: " jean@entreprise.com ", message: "  Le SPF est refusé  " });
    fireEvent.change(form.category, { target: { value: "billing" } });
    fireEvent.click(form.submit);

    await waitFor(() =>
      expect(mocks.mutateAsync).toHaveBeenCalledWith({
        requester_name: "Jean Dupont",
        requester_email: "jean@entreprise.com",
        category: "billing",
        message: "Le SPF est refusé",
      }),
    );
    expect(await screen.findByRole("heading", { level: 3, name: "support.recorded" })).toBeInTheDocument();
    expect(screen.getByText("support.recorded_detail:abcdef12")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "support.submit" })).not.toBeInTheDocument();
  });

  it("lets the user send another request from the confirmation, with the message cleared", async () => {
    mocks.mutateAsync.mockResolvedValue({ id: "ticket-1", status: "open", created_at: "" });
    render(<SupportRoute session={session} />);
    fillForm({ message: "Première demande" });
    fireEvent.click(fields().submit);
    await screen.findByRole("heading", { level: 3, name: "support.recorded" });

    fireEvent.click(screen.getByRole("button", { name: "support.send_another" }));
    const form = fields();
    expect(form.message.value).toBe("");
    expect(form.name.value).toBe("Jean Dupont");
    expect(form.email.value).toBe("jean@entreprise.com");
  });

  it("does not send when a field is blank", () => {
    render(<SupportRoute />);
    const form = fields().submit.closest("form")!;
    fireEvent.submit(form);
    fillForm({ message: "   " });
    fireEvent.submit(form);
    fillForm({ name: " " });
    fireEvent.submit(form);
    fillForm({ email: "" });
    fireEvent.submit(form);
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("shows the server error in an alert and keeps the form so the user can retry", async () => {
    mocks.mutateAsync.mockRejectedValue(new Error("Service indisponible"));
    render(<SupportRoute />);
    const form = fillForm();
    fireEvent.click(form.submit);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Service indisponible");
    expect(screen.getByRole("button", { name: "support.submit" })).toBeInTheDocument();
    expect(fields().message.value).toBe("Le SPF est refusé");

    fireEvent.click(within(alert).getByRole("button", { name: "Fermer la notification" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("falls back to the generic error message when the failure is not an Error", async () => {
    mocks.mutateAsync.mockRejectedValue("nope");
    render(<SupportRoute />);
    fireEvent.click(fillForm().submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("support.submit_error");
  });

  it("disables the submit button while the request is pending", () => {
    mocks.state.isPending = true;
    render(<SupportRoute />);
    expect(screen.getByRole("button", { name: "support.submit" })).toBeDisabled();
  });
});
