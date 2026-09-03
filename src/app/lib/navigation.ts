import type { SidebarPage } from "../components/common/sidebar";

export const sidebarPagePaths: Record<SidebarPage, string> = {
  dashboard: "/app/dashboard",
  threats: "/app/threats",
  quarantine: "/app/quarantine",
  alerts: "/app/alerts",
  "domain-shield": "/app/domain-shield",
  logs: "/admin",
  "admin-operations": "/admin/operations",
  "admin-incidents": "/admin/incidents",
  "admin-integrations": "/admin/integrations",
  "admin-reviews": "/admin/reviews",
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

export function isAdminPage(page: SidebarPage | null): boolean {
  return page === "logs" || page === "admin-operations"
    || page === "admin-incidents" || page === "admin-integrations" || page === "admin-reviews";
}

export function resolveAuthorizedPage(
  requested: SidebarPage | null,
  options: { isPlatformAdmin: boolean; onboardingRequired: boolean },
): SidebarPage {
  if (requested && isAdminPage(requested) && options.isPlatformAdmin) return requested;
  if (requested === "support") return "support";
  if (options.onboardingRequired) return "settings";
  return requested && !isAdminPage(requested) ? requested : "dashboard";
}
