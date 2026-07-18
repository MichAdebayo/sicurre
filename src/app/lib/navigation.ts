import type { SidebarPage } from "../components/common/sidebar";

export const sidebarPagePaths: Record<SidebarPage, string> = {
  dashboard: "/app/dashboard",
  threats: "/app/threats",
  quarantine: "/app/quarantine",
  alerts: "/app/alerts",
  "domain-shield": "/app/domain-shield",
  logs: "/admin",
  settings: "/app/settings",
  support: "/app/support",
};

const pathPages = new Map(
  Object.entries(sidebarPagePaths).map(([page, path]) => [path, page as SidebarPage]),
);

export function getSidebarPageFromPath(pathname: string): SidebarPage | null {
  const normalized = pathname.replace(/\/$/, "") || "/";
  return pathPages.get(normalized) ?? null;
}

export function resolveAuthorizedPage(
  requested: SidebarPage | null,
  options: { isPlatformAdmin: boolean; onboardingRequired: boolean },
): SidebarPage {
  if (options.isPlatformAdmin) {
    return requested && ["logs", "settings", "support"].includes(requested)
      ? requested
      : "logs";
  }
  if (options.onboardingRequired) return "settings";
  return requested && requested !== "logs" ? requested : "dashboard";
}
