// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CloudflareIntegrator } from "../../../src/app/components/common/cloudflare-integrator";

const state = vi.hoisted(() => ({
  status: { data: undefined as unknown, isLoading: false, refetch: vi.fn() },
  preview: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  verify: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  setup: { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() },
  teardown: { mutateAsync: vi.fn(), isPending: false, isError: false, error: null as unknown, reset: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "hosts" in options ? `${key}:${options.hosts}` : key,
  }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
  motion: { div: "div" },
}));

vi.mock("../../../src/app/lib/api", () => ({
  useCloudflareStatus: () => state.status,
  usePreviewCloudflareDomain: () => state.preview,
  useVerifyCloudflareToken: () => state.verify,
  useSetupCloudflare: () => state.setup,
  useTeardownCloudflare: () => state.teardown,
}));

const connectable = {
  zone_name: "sicurre.com",
  resolvable: true,
  on_cloudflare: true,
  mail_provider: "cloudflare",
  plan: { spf: "modify", dmarc: "add", dkim_present: false },
};

const active = {
  id: "int-1",
  status: "active",
  zone_name: "sicurre.com",
  destination_email: "owner@sicurre.com",
  worker_name: "sicurre-gateway",
};

function typeDomain(domain: string) {
  fireEvent.change(screen.getByLabelText("cloudflare.domain"), { target: { value: domain } });
}

async function previewDomain(domain = "sicurre.com") {
  typeDomain(domain);
  fireEvent.click(screen.getByRole("button", { name: "cloudflare.check_domain" }));
  await waitFor(() => expect(state.preview.mutateAsync).toHaveBeenCalled());
}

async function reachTokenStep() {
  state.preview.mutateAsync.mockResolvedValue(connectable);
  await previewDomain();
  await screen.findByLabelText("cloudflare.api_token");
  fireEvent.change(screen.getByLabelText("cloudflare.api_token"), { target: { value: "cf-token" } });
}

async function reachPlan() {
  await reachTokenStep();
  state.verify.mutateAsync.mockResolvedValue({ valid: true, zone_id: "z1", plan: { spf: "keep", dmarc: "modify", dkim_present: true } });
  fireEvent.click(screen.getByRole("button", { name: "cloudflare.verify_token" }));
  await screen.findByRole("button", { name: "cloudflare.integrate" });
}

beforeEach(() => {
  state.status = { data: { status: "not_configured" }, isLoading: false, refetch: vi.fn() };
  state.preview = { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() };
  state.verify = { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() };
  state.setup = { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() };
  state.teardown = { mutateAsync: vi.fn(), isPending: false, isError: false, error: null, reset: vi.fn() };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Cloudflare integrator first load", () => {
  it("shows a skeleton until the status is known", () => {
    state.status = { data: undefined, isLoading: true, refetch: vi.fn() };
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    expect(screen.queryByText("cloudflare.step_domain_title")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("treats a missing status as not configured", () => {
    state.status = { data: undefined, isLoading: false, refetch: vi.fn() };
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    expect(screen.getByText("cloudflare.step_domain_title")).toBeInTheDocument();
  });
});

describe("Cloudflare domain preview", () => {
  it("ignores a blank domain and shows the pending label while checking", () => {
    state.preview.isPending = true;
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    expect(screen.getByRole("button", { name: "cloudflare.checking" })).toBeDisabled();
    expect(state.preview.mutateAsync).not.toHaveBeenCalled();
  });

  it("says when the domain does not resolve at all", async () => {
    state.preview.mutateAsync.mockResolvedValue({ ...connectable, resolvable: false });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await previewDomain("ghost.example");

    expect(await screen.findByRole("alert")).toHaveTextContent("cloudflare.preview_unresolvable");
    expect(screen.queryByLabelText("cloudflare.api_token")).not.toBeInTheDocument();
    expect(screen.getByLabelText("cloudflare.domain")).toBeDisabled();
  });

  it("describes a zone without mail and a DKIM key already published", async () => {
    state.preview.mutateAsync.mockResolvedValue({
      ...connectable, mail_provider: "none", plan: { spf: "add", dmarc: "keep", dkim_present: true },
    });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await previewDomain();

    expect(await screen.findByText("cloudflare.preview_mail_none")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.preview_dkim_present")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.plan_add")).toBeInTheDocument();
    expect(screen.getAllByText("cloudflare.plan_keep").length).toBeGreaterThanOrEqual(1);
  });

  it("names the other provider's hosts when the mail lives elsewhere", async () => {
    state.preview.mutateAsync.mockResolvedValue({ ...connectable, mail_provider: "other", mx_hosts: ["mx1.ovh.net", "mx2.ovh.net"] });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await previewDomain();
    expect(await screen.findByText("cloudflare.preview_mail_other:mx1.ovh.net, mx2.ovh.net")).toBeInTheDocument();
  });

  it.each([
    ["Domain already receives mail through another provider", "domain_shield.cloudflare_mail_provider_conflict"],
    ["Token lacks Zone Settings:Edit", "domain_shield.cloudflare_zone_settings_permission_error"],
    ["dns_records write forbidden", "domain_shield.cloudflare_dns_permission_error"],
    ["Cloudflare DNS update failed", "domain_shield.cloudflare_dns_permission_error"],
    ["workers/scripts PUT 403", "domain_shield.cloudflare_worker_permission_error"],
    ["email/routing/rules 403", "domain_shield.cloudflare_routing_permission_error"],
    ["email/routing/addresses 403", "domain_shield.cloudflare_address_permission_error"],
    ["Authentication error (10000)", "domain_shield.cloudflare_scope_error"],
    ["Zone not found for this token", "cloudflare.errors.zone_not_found"],
    ["Token verification failed", "cloudflare.errors.invalid_token"],
    ["Rate limited, retry later", "Rate limited, retry later"],
  ])("maps the preview failure %j to %s", async (message, expected) => {
    state.preview.mutateAsync.mockRejectedValue(new Error(message));
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await previewDomain();
    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
  });

  it("falls back to a generic message when the failure carries none", async () => {
    state.preview.mutateAsync.mockRejectedValue({});
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await previewDomain();
    expect(await screen.findByRole("alert")).toHaveTextContent("domain_shield.cloudflare_unknown_error");

    // Typing again clears the error.
    typeDomain("other.com");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Cloudflare token verification", () => {
  it("shows the token in clear on demand and lists the required permissions", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachTokenStep();

    const token = screen.getByLabelText("cloudflare.api_token");
    expect(token).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.show_token" }));
    expect(token).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.hide_token" }));
    expect(token).toHaveAttribute("type", "password");

    const toggle = screen.getByRole("button", { name: "cloudflare.token_help_toggle" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(screen.getByText("cloudflare.token_help_grants")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").filter((item) => item.textContent?.includes("› Edit")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.token_help_toggle_hide" }));
    expect(screen.queryByText("cloudflare.token_help_grants")).not.toBeInTheDocument();
  });

  it("names an invalid token and moves focus to the message", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachTokenStep();
    state.verify.mutateAsync.mockResolvedValueOnce({ valid: false, error: "Token invalid for zone" });

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.verify_token" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("cloudflare.errors.invalid_token");
    expect(alert).toHaveFocus();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    // Editing the token clears the error.
    fireEvent.change(screen.getByLabelText("cloudflare.api_token"), { target: { value: "cf-token-2" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("falls back to the generic wording when the API gives no reason", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachTokenStep();
    state.verify.mutateAsync.mockResolvedValueOnce({ valid: false });

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.verify_token" }));
    // The fallback copy goes through the error formatter too; with a
    // key-echoing t() it reads as a token failure, which is what a customer
    // would be told.
    expect(await screen.findByRole("alert")).toHaveTextContent("cloudflare.errors.invalid_token");
  });

  it("reports a thrown verification failure", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachTokenStep();
    state.verify.mutateAsync.mockRejectedValueOnce(new Error("Zone not found"));

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.verify_token" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cloudflare.errors.zone_not_found");
  });

  it("keeps the verify step when a valid answer carries no plan", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachTokenStep();
    state.verify.mutateAsync.mockResolvedValueOnce({ valid: true, zone_id: "z1" });

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.verify_token" }));
    await waitFor(() => expect(state.verify.mutateAsync).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "cloudflare.verify_token" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "cloudflare.integrate" })).not.toBeInTheDocument();
  });

  it("shows the pending labels of the verify and setup mutations", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachPlan();
    expect(screen.getByText("cloudflare.plan_title")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.plan_gateway")).toBeInTheDocument();

    state.verify.isPending = true;
    fireEvent.change(screen.getByLabelText("cloudflare.api_token"), { target: { value: "cf-token-3" } });
    expect(screen.getByRole("button", { name: "cloudflare.checking" })).toBeDisabled();
  });
});

describe("Cloudflare provisioning progress", () => {
  it("marks the running stage as failed and offers a way back to the form", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachPlan();
    state.setup.mutateAsync.mockRejectedValueOnce(new Error("workers/scripts forbidden"));

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.integrate" }));
    expect(await screen.findByText("cloudflare.progress_title")).toBeInTheDocument();
    expect(await screen.findByText("domain_shield.cloudflare_worker_permission_error")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.back_to_setup" }));
    expect(screen.getByText("cloudflare.step_domain_title")).toBeInTheDocument();
  });

  it("uses the generic stage failure when the error has no message", async () => {
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    await reachPlan();
    state.setup.mutateAsync.mockRejectedValueOnce(new Error(""));

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.integrate" }));
    expect(await screen.findByText("cloudflare.stage_failed")).toBeInTheDocument();
  });

  it("switches to the checklist when the backend is already provisioning and polls the status", () => {
    vi.useFakeTimers();
    const refetch = vi.fn();
    state.status = { data: { ...active, status: "provisioning" }, isLoading: false, refetch };
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    expect(screen.getByText("cloudflare.progress_title")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.stage_routing")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "cloudflare.back_to_setup" })).not.toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(3000); });
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("dismisses the checklist 1.5 s after the status turns active and tells the parent once", () => {
    vi.useFakeTimers();
    const onSuccess = vi.fn();
    state.status = { data: { ...active, status: "provisioning" }, isLoading: false, refetch: vi.fn() };
    const { rerender } = render(<CloudflareIntegrator userEmail="owner@sicurre.com" onSuccess={onSuccess} />);

    state.status = { data: active, isLoading: false, refetch: vi.fn() };
    rerender(<CloudflareIntegrator userEmail="owner@sicurre.com" onSuccess={onSuccess} />);
    expect(screen.getByText("cloudflare.progress_title")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "cloudflare.back_to_setup" })).not.toBeInTheDocument();

    // A parent render with a fresh callback must not restart the timer.
    act(() => { vi.advanceTimersByTime(1000); });
    const replacement = vi.fn();
    rerender(<CloudflareIntegrator userEmail="owner@sicurre.com" onSuccess={replacement} />);
    expect(screen.getByText("cloudflare.progress_title")).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(500); });
    expect(replacement).toHaveBeenCalledTimes(1);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(screen.queryByText("cloudflare.progress_title")).not.toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(5000); });
    expect(replacement).toHaveBeenCalledTimes(1);
  });

  it("shows the Cloudflare error on the routing stage when provisioning fails", () => {
    state.status = { data: { ...active, status: "provisioning" }, isLoading: false, refetch: vi.fn() };
    const { rerender } = render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    state.status = { data: { ...active, status: "error", error_message: "email/routing/rules denied" }, isLoading: false, refetch: vi.fn() };
    rerender(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    expect(screen.getByText("domain_shield.cloudflare_routing_permission_error")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "cloudflare.back_to_setup" })).toBeInTheDocument();
  });

  it("falls back to the final failure wording when the error carries no message", () => {
    state.status = { data: { ...active, status: "provisioning" }, isLoading: false, refetch: vi.fn() };
    const { rerender } = render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    state.status = { data: { ...active, status: "error" }, isLoading: false, refetch: vi.fn() };
    rerender(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    expect(screen.getByText("cloudflare.final_setup_failed")).toBeInTheDocument();
  });
});

describe("Cloudflare connected state", () => {
  it("shows the zone, the destination and the worker, and hides the teardown until asked", () => {
    state.status = { data: active, isLoading: false, refetch: vi.fn() };
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    expect(screen.getByText("sicurre.com")).toBeInTheDocument();
    expect(screen.getByText("owner@sicurre.com")).toBeInTheDocument();
    expect(screen.getByText("Worker: sicurre-gateway")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.status_active")).toBeInTheDocument();
    expect(screen.queryByText("cloudflare.disable_desc")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.disable" }));
    expect(screen.getByText("cloudflare.disable_desc")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByText("cloudflare.disable_desc")).not.toBeInTheDocument();
  });

  it("tears the integration down and refreshes the status", async () => {
    const refetch = vi.fn();
    state.status = { data: active, isLoading: false, refetch };
    state.teardown.mutateAsync.mockResolvedValue({ status: "removed", dmarc_reporting_withdrawn: true });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.disable" }));
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.confirm_disable" }));

    await waitFor(() => expect(state.teardown.mutateAsync).toHaveBeenCalledWith({ integration_id: "int-1" }));
    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("cloudflare.disable_desc")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.disable" }));
    expect(screen.queryByText("cloudflare.dmarc_withdrawal_failed")).not.toBeInTheDocument();
  });

  it("warns when the DMARC reporting address could not be withdrawn", async () => {
    state.status = { data: active, isLoading: false, refetch: vi.fn() };
    state.teardown.mutateAsync.mockResolvedValue({ status: "removed", dmarc_reporting_withdrawn: false });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.disable" }));
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.confirm_disable" }));
    await waitFor(() => expect(screen.queryByText("cloudflare.disable_desc")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.disable" }));
    expect(screen.getByText("cloudflare.dmarc_withdrawal_failed")).toBeInTheDocument();
  });

  it("keeps the panel open and shows the mutation error when teardown fails", async () => {
    state.status = { data: active, isLoading: false, refetch: vi.fn() };
    state.teardown = { ...state.teardown, isError: true, error: new Error("Worker delete failed") };
    state.teardown.mutateAsync.mockRejectedValue(new Error("Worker delete failed"));
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.disable" }));
    expect(screen.getByText("Worker delete failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.confirm_disable" }));
    await waitFor(() => expect(state.teardown.mutateAsync).toHaveBeenCalledTimes(1));
    expect(screen.getByText("cloudflare.disable_desc")).toBeInTheDocument();
  });

  it("cannot tear down an integration without an id and waits while one is pending", () => {
    state.status = { data: { ...active, id: undefined }, isLoading: false, refetch: vi.fn() };
    const { rerender } = render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.disable" }));
    expect(screen.getByRole("button", { name: "cloudflare.confirm_disable" })).toBeDisabled();

    state.status = { data: active, isLoading: false, refetch: vi.fn() };
    state.teardown = { ...state.teardown, isPending: true };
    rerender(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    expect(screen.getByRole("button", { name: "cloudflare.confirm_disable" })).toBeDisabled();
  });
});

describe("Cloudflare pending verification state", () => {
  it("asks for the destination address to be confirmed and refreshes on demand", () => {
    const refetch = vi.fn();
    state.status = { data: { ...active, status: "pending_verification" }, isLoading: false, refetch };
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    expect(screen.getByText("cloudflare.verify_email")).toBeInTheDocument();
    expect(screen.getByText("owner@sicurre.com")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.status_pending")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.refresh_status" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("lets the customer cancel and delete the pending integration", async () => {
    state.status = { data: { ...active, status: "pending_verification" }, isLoading: false, refetch: vi.fn() };
    state.teardown.mutateAsync.mockResolvedValue({ status: "removed", dmarc_reporting_withdrawn: true });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.cancel_and_delete" }));
    fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByText("cloudflare.disable_desc")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.cancel_and_delete" }));
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.delete" }));
    await waitFor(() => expect(state.teardown.mutateAsync).toHaveBeenCalledWith({ integration_id: "int-1" }));
  });
});

describe("Cloudflare error state", () => {
  it("explains the failure and retries the setup with the stored zone", async () => {
    const refetch = vi.fn().mockResolvedValue({});
    state.status = { data: { ...active, status: "error", error_message: "dns_records forbidden" }, isLoading: false, refetch };
    state.setup.mutateAsync.mockResolvedValue({ integration_id: "int-1", status: "provisioning" });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    expect(screen.getByText("cloudflare.provisioning_failed")).toBeInTheDocument();
    expect(screen.getByText("domain_shield.cloudflare_dns_permission_error")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.check_permissions")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    await waitFor(() => expect(state.setup.mutateAsync).toHaveBeenCalledWith({
      zone_name: "sicurre.com",
      destination_email: "owner@sicurre.com",
    }));
    expect(await screen.findByText("cloudflare.progress_title")).toBeInTheDocument();
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("refreshes the status when the retry fails again", async () => {
    const refetch = vi.fn().mockResolvedValue({});
    state.status = { data: { ...active, status: "error", error_message: null }, isLoading: false, refetch };
    state.setup.mutateAsync.mockRejectedValue(new Error("still broken"));
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    expect(screen.getByText("domain_shield.cloudflare_unknown_error")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    expect(screen.getByText("cloudflare.provisioning_failed")).toBeInTheDocument();
  });

  it("does nothing on retry when the stored integration lacks a zone", () => {
    state.status = { data: { status: "error", error_message: "x" }, isLoading: false, refetch: vi.fn() };
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    expect(state.setup.mutateAsync).not.toHaveBeenCalled();
  });

  it("shows the pending state on the retry button", () => {
    state.status = { data: { ...active, status: "error" }, isLoading: false, refetch: vi.fn() };
    state.setup.isPending = true;
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    expect(within(screen.getByRole("button", { name: "common.retry" })).getByText("common.retry")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "common.retry" })).toBeDisabled();
  });
});
