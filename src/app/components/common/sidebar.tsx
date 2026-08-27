import { useEffect, useState, type ComponentType } from "react";
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
  ChevronsLeft,
  ChevronsRight,
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

const COLLAPSED_KEY = "sicurre_rail_collapsed";

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
  /** Desktop rail only. The mobile drawer is already a transient overlay. */
  collapsible?: boolean;
  className?: string;
}

interface RailButtonProps {
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
  label: string;
  collapsed: boolean;
  active?: boolean;
  disabled?: boolean;
  title?: string;
  onClick: () => void;
  trailing?: React.ReactNode;
  tone?: "default" | "danger";
}

/**
 * One rail row. Collapsed, the label is removed from the flow but kept as the
 * button's accessible name, so screen readers and tooltips still announce it.
 */
function RailButton({
  icon: Icon,
  label,
  collapsed,
  active = false,
  disabled = false,
  title,
  onClick,
  trailing,
  tone = "default",
}: RailButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled}
      aria-label={collapsed ? label : undefined}
      title={title ?? (collapsed ? label : undefined)}
      className={clsx(
        "flex w-full items-center rounded-lg py-3 text-[14px] font-semibold transition-colors duration-150 select-none",
        collapsed ? "justify-center px-0" : "gap-2.5 px-3.5",
        disabled
          ? "cursor-not-allowed text-on-surface-variant/35 opacity-70"
          : active
            ? "bg-primary text-on-primary shadow-sm shadow-primary/20"
            : tone === "danger"
              ? "cursor-pointer text-on-surface-variant hover:bg-error/5 hover:text-error"
              : "cursor-pointer text-on-surface-variant hover:bg-surface-low hover:text-on-surface",
      )}
    >
      <Icon className="h-[18px] w-[18px] shrink-0 stroke-[1.5]" aria-hidden="true" />
      {!collapsed && <span className="flex-1 truncate text-left">{label}</span>}
      {!collapsed && trailing}
    </button>
  );
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
  collapsible = false,
  className,
}: SidebarProps) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();

  const [collapsed, setCollapsed] = useState(
    () => collapsible && localStorage.getItem(COLLAPSED_KEY) === "1",
  );

  useEffect(() => {
    if (collapsible) localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed, collapsible]);

  const isOnboardingLocked = onboardingRequired && userRole !== "admin";
  // Platform admins have no mailbox of their own, so the workspace card would
  // be describing something they do not have.
  const isCustomerWorkspace = userRole !== "admin";
  const isProtected = hasIntegration && !onboardingRequired;
  const statusLabel = isProtected
    ? t("sidebar.status_protected")
    : t("sidebar.status_setup_required");

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
  const mainNav = userRole === "admin" ? adminNav : baseNav;

  const bottomNav = [
    { id: "support", label: t("sidebar.nav_support"), icon: HelpCircle },
  ] as const;

  return (
    <aside
      className={clsx(
        "h-screen shrink-0 border-r border-border-subtle bg-surface-lowest flex flex-col motion-safe:transition-[width] motion-safe:duration-200 dark:bg-surface-low",
        collapsed ? "w-[72px]" : "w-[240px]",
        className,
      )}
    >
      {/* Brand */}
      <div className={clsx("pt-5 pb-4", collapsed ? "px-0" : "px-4")}>
        <div className={clsx("flex items-center", collapsed ? "justify-center" : "gap-2.5")}>
          <img src={sicurreLogo} alt="Sicurre" className="h-9 w-9 shrink-0" />
          {!collapsed && (
            <span className="font-display text-xl font-bold leading-none text-on-surface">
              Sicurre
            </span>
          )}
        </div>
      </div>

      {/* Workspace context — which tenant am I in, and is it protected.
          Visible on every page, so the answer never depends on the top bar.
          Collapsed, it reduces to the status dot with the detail in a tooltip. */}
      {isCustomerWorkspace && workspaceName && (
        <div className={clsx("pb-4", collapsed ? "px-0" : "px-4")}>
          {collapsed ? (
            <div
              className="mx-auto grid h-9 w-9 place-items-center rounded-lg bg-surface-low/60"
              title={`${workspaceName} — ${statusLabel}`}
            >
              <span className="sr-only">{`${workspaceName} — ${statusLabel}`}</span>
              <span
                aria-hidden="true"
                className={clsx(
                  "h-2.5 w-2.5 rounded-full",
                  isProtected ? "bg-safe" : "bg-warning",
                )}
              />
            </div>
          ) : (
            <div className="rounded-xl border border-border-subtle bg-surface-low/60 px-3.5 py-3">
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={clsx(
                    "h-2 w-2 shrink-0 rounded-full",
                    isProtected ? "bg-safe" : "bg-warning",
                  )}
                />
                <span
                  className="truncate text-[13px] font-bold text-on-surface"
                  title={workspaceName}
                >
                  {workspaceName}
                </span>
              </div>
              <p
                className={clsx(
                  "mt-1.5 text-[11px] font-semibold",
                  isProtected ? "text-safe" : "text-warning",
                )}
              >
                {statusLabel}
              </p>
              {typeof threatCount === "number" && (
                <p className="mt-1 text-[11px] font-medium text-on-surface-variant tabular-nums">
                  {t("sidebar.emails_analysed", { count: threatCount })}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Main Navigation */}
      <nav
        className={clsx(
          "flex-1 space-y-1 overflow-y-auto overflow-x-hidden py-5",
          collapsed ? "px-3" : "px-3",
        )}
      >
        {mainNav.map((item) => {
          const isSettings = item.id === "settings";
          const isLocked = isOnboardingLocked && !isSettings;
          return (
            <RailButton
              key={item.id}
              icon={item.icon}
              label={item.label}
              collapsed={collapsed}
              active={currentPage === item.id}
              disabled={isLocked}
              title={isLocked ? t("sidebar.locked_hint") : undefined}
              onClick={() => {
                if (isLocked) return;
                onPageChange(item.id as SidebarPage);
              }}
              trailing={isLocked ? <LockKeyhole className="h-3.5 w-3.5 shrink-0" /> : undefined}
            />
          );
        })}
      </nav>

      {/* Bottom Section */}
      <div className="space-y-3 px-3 pb-4 pt-3">
        {bottomNav.map((item) => (
          <RailButton
            key={item.id}
            icon={item.icon}
            label={item.label}
            collapsed={collapsed}
            active={currentPage === item.id}
            onClick={() => onPageChange(item.id as SidebarPage)}
          />
        ))}

        {/* Emergency Lockdown */}
        {onLockdown && (
          <button
            type="button"
            onClick={onLockdown}
            aria-label={collapsed ? t("sidebar.lockdown") : undefined}
            title={collapsed ? t("sidebar.lockdown") : undefined}
            className={clsx(
              "flex w-full cursor-pointer items-center justify-center rounded-lg bg-error py-3 text-[14px] font-semibold text-on-error transition-all active:scale-[0.97] hover:bg-on-error-container",
              collapsed ? "px-0" : "gap-2 px-3.5",
            )}
          >
            <Zap className="h-4 w-4 shrink-0" aria-hidden="true" />
            {!collapsed && <span>{t("sidebar.lockdown")}</span>}
          </button>
        )}

        {/* Theme */}
        <button
          type="button"
          role="switch"
          aria-checked={theme === "dark"}
          aria-label={collapsed ? t("sidebar.dark_mode") : undefined}
          title={collapsed ? t("sidebar.dark_mode") : undefined}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className={clsx(
            "flex w-full cursor-pointer items-center rounded-lg py-3 text-[14px] font-semibold text-on-surface-variant transition-colors hover:bg-surface-low hover:text-on-surface",
            collapsed ? "justify-center px-0" : "gap-3 px-3.5",
          )}
        >
          {theme === "dark" ? (
            <Moon className="h-[18px] w-[18px] shrink-0 stroke-[1.5]" aria-hidden="true" />
          ) : (
            <Sun className="h-[18px] w-[18px] shrink-0 stroke-[1.5]" aria-hidden="true" />
          )}
          {!collapsed && (
            <>
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
                    "h-4 w-4 rounded-full bg-surface-lowest motion-safe:transition-transform",
                    theme === "dark" && "translate-x-4",
                  )}
                />
              </span>
            </>
          )}
        </button>

        <div className="space-y-1 border-t border-border-subtle pt-3">
          <RailButton
            icon={LogOut}
            label={t("common.logout")}
            collapsed={collapsed}
            tone="danger"
            onClick={onLogout}
          />

          {collapsible && (
            <RailButton
              icon={collapsed ? ChevronsRight : ChevronsLeft}
              label={collapsed ? t("sidebar.expand_rail") : t("sidebar.collapse_rail")}
              collapsed={collapsed}
              onClick={() => setCollapsed((value) => !value)}
            />
          )}
        </div>
      </div>
    </aside>
  );
}
