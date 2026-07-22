// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SettingsRoute from "../../../src/app/routes/settings";

const mocks = vi.hoisted(() => ({
  retrySetup: vi.fn(),
  refetchDomains: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn() },
  }),
}));

vi.mock("../../../src/app/components/common/cloudflare-integrator", () => ({
  CloudflareIntegrator: () => <div>Cloudflare wizard</div>,
}));

vi.mock("../../../src/app/lib/api", () => ({
  getStoredAuthProvider: () => "password",
  useChangePassword: () => ({ mutateAsync: vi.fn() }),
  useUpdateProfile: () => ({ mutateAsync: vi.fn() }),
  useCloudflareList: () => ({
    data: [{
      id: "integration-1",
      status: "error",
      zone_name: "vinse.app",
      destination_email: "michael@vinse.app",
    }],
    isLoading: false,
    refetch: mocks.refetchDomains,
  }),
  useSetupCloudflare: () => ({ mutateAsync: mocks.retrySetup, isPending: false }),
  useTeardownCloudflare: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useWorkspaceCloudflareToken: () => ({ data: { configured: true }, refetch: vi.fn() }),
  useSaveWorkspaceCloudflareToken: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteWorkspaceCloudflareToken: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

beforeEach(() => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("connected domain recovery", () => {
  it("retries a failed existing domain from its table row", async () => {
    mocks.retrySetup.mockResolvedValue({ status: "provisioning" });
    render(
      <SettingsRoute
        initialTab="domains"
        session={{
          id: "user-1",
          email: "michael@vinse.app",
          display_name: "Michael Adebayo",
          role: "owner",
          workspace_id: "workspace-1",
          workspace_name: "vinse.app Workspace",
          is_platform_admin: false,
          has_cloudflare_integration: false,
          threat_count: 0,
          onboarding_required: true,
        }}
      />,
    );

    expect(screen.getByText(/Relancez la configuration de vinse\.app/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Réessayer la configuration de vinse\.app/ })).toBeInTheDocument();
    expect(screen.getByText("settings.add_another_domain")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Réessayer la configuration de vinse\.app/ }));

    await waitFor(() => expect(mocks.retrySetup).toHaveBeenCalledWith({
      zone_name: "vinse.app",
      destination_email: "michael@vinse.app",
    }));
    expect(mocks.refetchDomains).toHaveBeenCalled();
  });
});
