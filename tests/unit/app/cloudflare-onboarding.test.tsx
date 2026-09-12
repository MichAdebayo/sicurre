// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CloudflareIntegrator } from "../../../src/app/components/common/cloudflare-integrator";

const mocks = vi.hoisted(() => ({
  preview: vi.fn(),
  verify: vi.fn(),
  setup: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
  motion: { div: "div" },
}));

vi.mock("../../../src/app/lib/api", () => ({
  useCloudflareStatus: () => ({ data: { status: "not_configured" }, isLoading: false, refetch: vi.fn() }),
  usePreviewCloudflareDomain: () => ({ mutateAsync: mocks.preview, isPending: false }),
  useVerifyCloudflareToken: () => ({ mutateAsync: mocks.verify, isPending: false }),
  useSetupCloudflare: () => ({ mutateAsync: mocks.setup, isPending: false }),
  useTeardownCloudflare: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const connectable = {
  zone_name: "sicurre.com",
  resolvable: true,
  on_cloudflare: true,
  mail_provider: "cloudflare",
  plan: { spf: "modify", dmarc: "add", dkim_present: false },
};

function typeDomain(domain: string) {
  fireEvent.change(screen.getByLabelText("cloudflare.domain"), { target: { value: domain } });
}

beforeEach(() => {
  mocks.preview.mockReset();
  mocks.verify.mockReset();
  mocks.setup.mockReset();
});

afterEach(cleanup);

describe("Cloudflare onboarding", () => {
  it("asks for the domain only, and reads it without a token", async () => {
    mocks.preview.mockResolvedValue(connectable);
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);

    expect(screen.queryByLabelText("cloudflare.api_token")).not.toBeInTheDocument();
    typeDomain("Sicurre.com");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.check_domain" }));

    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith({ zone_name: "sicurre.com" }));
    expect(mocks.verify).not.toHaveBeenCalled();
    expect(await screen.findByText("cloudflare.preview_on_cloudflare")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.plan_modify")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.preview_source")).toBeInTheDocument();
    // No consent is collected from a public read: the checkboxes come with the token step.
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("offers the pre-filled token link only once the domain can be connected", async () => {
    mocks.preview.mockResolvedValue(connectable);
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    typeDomain("sicurre.com");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.check_domain" }));

    const link = await screen.findByRole("link", { name: /cloudflare.token_help_open/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("href")).toContain("permissionGroupKeys");
    expect(screen.getByLabelText("cloudflare.api_token")).toBeInTheDocument();
    expect(screen.getByText("cloudflare.step_token_not")).toBeInTheDocument();
  });

  it("stops when the domain's DNS is not on Cloudflare", async () => {
    mocks.preview.mockResolvedValue({ ...connectable, on_cloudflare: false, nameservers: ["ns1.ovh.net"] });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    typeDomain("elsewhere.fr");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.check_domain" }));

    expect(await screen.findByText("cloudflare.preview_not_on_cloudflare")).toBeInTheDocument();
    expect(screen.queryByLabelText("cloudflare.api_token")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /token_help_open/ })).not.toBeInTheDocument();
  });

  it("stops when another provider already receives the mail", async () => {
    mocks.preview.mockResolvedValue({ ...connectable, mail_provider: "other", mx_hosts: ["aspmx.l.google.com"] });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    typeDomain("sicurre.com");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.check_domain" }));

    expect(await screen.findByText("cloudflare.preview_mail_other")).toBeInTheDocument();
    expect(screen.queryByLabelText("cloudflare.api_token")).not.toBeInTheDocument();
  });

  it("verifies the token, shows the consent plan, then connects with the choices made", async () => {
    mocks.preview.mockResolvedValue(connectable);
    mocks.verify.mockResolvedValue({ valid: true, zone_id: "z1", plan: { spf: "modify", dmarc: "add", dkim_present: false } });
    mocks.setup.mockResolvedValue({ integration_id: "i1", status: "provisioning" });
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    typeDomain("sicurre.com");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.check_domain" }));
    await screen.findByLabelText("cloudflare.api_token");

    fireEvent.change(screen.getByLabelText("cloudflare.api_token"), { target: { value: "cf-token" } });
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.verify_token" }));
    await waitFor(() =>
      expect(mocks.verify).toHaveBeenCalledWith({ cf_api_token: "cf-token", zone_name: "sicurre.com" }),
    );
    expect(mocks.setup).not.toHaveBeenCalled();

    const boxes = await screen.findAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    fireEvent.click(boxes[1]); // decline the DMARC write
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.integrate" }));
    await waitFor(() =>
      expect(mocks.setup).toHaveBeenCalledWith(
        expect.objectContaining({ cf_api_token: "cf-token", zone_name: "sicurre.com", fix_spf: true, fix_dmarc: false }),
      ),
    );
  });

  it("changing the domain discards the preview, the token and the plan", async () => {
    mocks.preview.mockResolvedValue(connectable);
    render(<CloudflareIntegrator userEmail="owner@sicurre.com" />);
    typeDomain("sicurre.com");
    fireEvent.click(screen.getByRole("button", { name: "cloudflare.check_domain" }));
    await screen.findByLabelText("cloudflare.api_token");

    fireEvent.click(screen.getByRole("button", { name: "cloudflare.change_domain" }));
    expect(screen.queryByLabelText("cloudflare.api_token")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "cloudflare.check_domain" })).toBeInTheDocument();
  });
});
