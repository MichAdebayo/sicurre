import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  Activity,
  History,
  Settings,
  HelpCircle,
  LogOut,
  Zap,
  Inbox,
  Bell,
  Shield,
  LockKeyhole,
  Moon,
  Sun,
} from "lucide-react";
import sicurreLogo from "../../assets/sicurre.svg";
import { useTheme } from "../../lib/theme";

// Supported pages in the sidebar navigation
export type SidebarPage =
  | "dashboard"
  | "threats"
  | "quarantine"
  | "alerts"
  | "domain-shield"
  | "logs"
  | "settings"
  | "support";

interface SidebarProps {
  currentPage: SidebarPage;
  onPageChange: (page: SidebarPage) => void;
  onLogout: () => void;
  onLockdown?: () => void;
  userRole?: string;
  onboardingRequired?: boolean;
  workspaceName?: string;
  threatCount?: number;
  hasIntegration?: boolean;
  className?: string;
}

export function Sidebar({
  currentPage,
  onPageChange,
  onLogout,
  onLockdown,
  userRole = "owner",
  onboardingRequired = false,
  workspaceName,
  threatCount,
  hasIntegration = false,
  className,
}: SidebarProps) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  const isOnboardingLocked = onboardingRequired && userRole !== "admin";
  // Platform admins have no mailbox of their own, so the workspace card would
  // be describing something they do not have.
  const isCustomerWorkspace = userRole !== "admin";
  const isProtected = hasIntegration && !onboardingRequired;

  const baseNav = [
    { id: "dashboard", label: t("sidebar.nav_dashboard"), icon: LayoutDashboard },
    { id: "threats", label: t("sidebar.nav_threats"), icon: Activity },
    { id: "quarantine", label: t("sidebar.nav_quarantine"), icon: Inbox },
    { id: "alerts", label: t("sidebar.nav_alerts"), icon: Bell },
    { id: "domain-shield", label: t("sidebar.nav_domain_shield"), icon: Shield },
    { id: "settings", label: t("sidebar.nav_settings"), icon: Settings },
  ] as const;

  const adminNav = [
    { id: "logs", label: t("sidebar.nav_admin_console"), icon: History },
    baseNav[5],
  ] as const;

  // Platform admins operate the service and do not own a customer mailbox.
  const mainNav = userRole === "admin"
    ? adminNav
    : baseNav;

  const bottomNav = [
    { id: "support", label: t("sidebar.nav_support"), icon: HelpCircle },
  ] as const;

  return (
    <aside
      className={clsx(
        "w-[240px] h-screen border-r border-border-subtle bg-surface-lowest flex flex-col shrink-0 dark:bg-surface-low",
        className,
      )}
    >
      {/* Logo */}
      <div className="px-4 pt-5 pb-4">
        <div className="flex items-center gap-2.5">
          <img src={sicurreLogo} alt="Sicurre" className="h-9 w-9 shrink-0" />
          <span className="font-display text-xl font-bold leading-none text-on-surface">
            Sicurre
          </span>
        </div>
      </div>

      {/* Workspace context — which tenant am I in, and is it protected.
          Visible on every page, so the answer never depends on the top bar. */}
      {isCustomerWorkspace && workspaceName && (
        <div className="px-4 pb-4">
          <div className="rounded-xl border border-border-subtle bg-surface-low/60 px-3.5 py-3">
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={clsx(
                  "h-2 w-2 shrink-0 rounded-full",
                  isProtected ? "bg-safe" : "bg-warning",
                )}
              />
              <span className="truncate text-[13px] font-bold text-on-surface" title={workspaceName}>
                {workspaceName}
              </span>
            </div>
            <p
              className={clsx(
                "mt-1.5 text-[11px] font-semibold",
                isProtected ? "text-safe" : "text-warning",
              )}
            >
              {isProtected ? t("sidebar.status_protected") : t("sidebar.status_setup_required")}
            </p>
            {typeof threatCount === "number" && (
              <p className="mt-1 text-[11px] font-medium text-on-surface-variant tabular-nums">
                {t("sidebar.emails_analysed", { count: threatCount })}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-5 space-y-1 overflow-y-auto">
        {mainNav.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;
          const isSettings = item.id === "settings";
          const isLocked = isOnboardingLocked && !isSettings;
          return (
            <button
              key={item.id}
              onClick={() => {
                if (isLocked) return;
                onPageChange(item.id as SidebarPage);
              }}
              disabled={isLocked}
              title={isLocked ? "Connectez Cloudflare pour déverrouiller cette page" : undefined}
              aria-disabled={isLocked}
              className={clsx(
                "w-full flex items-center gap-2.5 px-3.5 py-3 text-[14px] font-semibold rounded-lg transition-all duration-150 select-none",
                isLocked
                  ? "cursor-not-allowed text-on-surface-variant/35 opacity-70"
                  : isActive
                  ? "bg-primary text-on-primary shadow-sm shadow-primary/20"
                  : "cursor-pointer text-on-surface-variant hover:bg-surface-low hover:text-on-surface",
              )}
            >
              <Icon className="w-[18px] h-[18px] shrink-0 stroke-[1.5]" />
              <span className="flex-1 truncate text-left">{item.label}</span>
              {isLocked && <LockKeyhole className="h-3.5 w-3.5 shrink-0" />}
            </button>
          );
        })}
      </nav>

      {/* Bottom Section */}
      <div className="px-3 pb-4 space-y-3 pt-3">
        {/* Support Link */}
        {bottomNav.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id as SidebarPage)}
              className={clsx(
                "w-full flex items-center gap-3 px-3.5 py-3 text-[14px] font-semibold rounded-lg transition-all cursor-pointer select-none",
                isActive
                  ? "bg-primary text-on-primary shadow-sm shadow-primary/20"
                  : "text-on-surface-variant hover:bg-surface-low hover:text-on-surface",
              )}
            >
              <Icon className="w-[18px] h-[18px] stroke-[1.5]" />
              <span>{item.label}</span>
            </button>
          );
        })}

        {/* Emergency Lockdown */}
        {onLockdown && (
          <button
            onClick={onLockdown}
            className="w-full flex items-center justify-center gap-2 px-3.5 py-3 bg-error text-on-error hover:bg-on-error-container font-semibold rounded-lg transition-all active:scale-[0.97] cursor-pointer text-[14px]"
          >
            <Zap className="w-4 h-4" />
            <span>{t("sidebar.lockdown")}</span>
          </button>
        )}

        <button
          type="button"
          role="switch"
          aria-checked={theme === "dark"}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-3.5 py-3 text-[14px] font-semibold text-on-surface-variant transition-colors hover:bg-surface-low hover:text-on-surface"
        >
          {theme === "dark"
            ? <Moon className="h-[18px] w-[18px] stroke-[1.5]" aria-hidden="true" />
            : <Sun className="h-[18px] w-[18px] stroke-[1.5]" aria-hidden="true" />}
          <span className="flex-1 text-left">{t("sidebar.dark_mode")}</span>
          <span
            aria-hidden="true"
            className={clsx(
              "flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors",
              theme === "dark" ? "bg-primary" : "bg-surface-highest",
            )}
          >
            <span
              className={clsx(
                "h-4 w-4 rounded-full bg-surface-lowest transition-transform",
                theme === "dark" && "translate-x-4",
              )}
            />
          </span>
        </button>

        <div className="border-t border-border-subtle pt-3">
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-3.5 py-3 text-[14px] font-semibold text-on-surface-variant transition-colors hover:bg-error/5 hover:text-error"
          >
            <LogOut className="h-[18px] w-[18px] stroke-[1.5]" />
            <span>{t("common.logout")}</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
