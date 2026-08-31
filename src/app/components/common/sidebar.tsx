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
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from "lucide-react";
import sicurreLogo from "../../assets/sicurre.svg";
import { useTheme } from "../../lib/theme";
import { useActiveDomain } from "../../contexts/active-domain";
import { useKPIStats } from "../../lib/api";

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
  administration?: boolean;
  onboardingRequired?: boolean;
  workspaceName?: string;
  workspaceId?: string;
  userName?: string;
  threatCount?: number;
  hasIntegration?: boolean;
  /** Desktop rail only. The mobile drawer is already a transient overlay. */
  collapsible?: boolean;
  onClose?: () => void;
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
            ? "bg-navy-dark text-on-primary shadow-sm shadow-primary/20"
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
  administration = false,
  onboardingRequired = false,
  workspaceName,
  workspaceId = "",
  userName,
  collapsible = false,
  onClose,
  className,
}: SidebarProps) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  const { domains, activeDomain, activeIntegration, setActiveDomain, isLoading, isError } = useActiveDomain();
  const domainUnavailable = isLoading || isError;
  const { data: domainKpis } = useKPIStats(workspaceId, administration ? "" : activeDomain);

  const [collapsed, setCollapsed] = useState(
    () => collapsible && localStorage.getItem(COLLAPSED_KEY) === "1",
  );

  useEffect(() => {
    if (collapsible) localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed, collapsible]);

  const isOnboardingLocked = onboardingRequired && !administration;
  const isCustomerWorkspace = !administration;
  const isProtected = activeIntegration?.status === "active" && !onboardingRequired;
  const statusLabel = isLoading ? t("common.loading") : isError ? t("common.domains_load_error") : isProtected
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
    { ...baseNav[0], label: t("sidebar.back_to_workspace") },
    baseNav[5],
  ] as const;

  const mainNav = administration ? adminNav : baseNav;

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
      <div className={clsx("pt-5 pb-6", collapsed ? "px-2" : "px-4")}>
        <div className={clsx("flex", collapsed ? "flex-col items-center gap-2" : "items-center justify-between gap-2.5")}>
          <div className={clsx("flex items-center", collapsed ? "justify-center" : "gap-2.5")}>
            <img src={sicurreLogo} alt="Sicurre" className="h-9 w-9 shrink-0" />
            {!collapsed && (
              <span className="font-display text-xl font-bold leading-none text-on-surface">
                Sicurre
              </span>
            )}
          </div>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-low hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              aria-label={t("common.close_navigation")}
              title={t("common.close_navigation")}
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          ) : collapsible ? (
            <button
              type="button"
              onClick={() => setCollapsed((value) => !value)}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-low hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              aria-label={collapsed ? t("sidebar.expand_rail") : t("sidebar.collapse_rail")}
              title={collapsed ? t("sidebar.expand_rail") : t("sidebar.collapse_rail")}
            >
              {collapsed ? (
                <PanelLeftOpen className="h-[18px] w-[18px]" aria-hidden="true" />
              ) : (
                <PanelLeftClose className="h-[18px] w-[18px]" aria-hidden="true" />
              )}
            </button>
          ) : null}
        </div>
      </div>

      {/* Workspace context — which tenant am I in, and is it protected.
          Visible on every page, so the answer never depends on the top bar.
          Collapsed, it reduces to the status dot with the detail in a tooltip. */}
      {isCustomerWorkspace && workspaceName && (
        <div className={clsx("pb-5", collapsed ? "px-0" : "px-4")}>
          {collapsed ? (
            <div
              className="mx-auto grid h-9 w-9 place-items-center rounded-lg bg-surface-low/60"
              title={`${userName || workspaceName}: ${activeDomain || statusLabel}`}
            >
              <span className="sr-only">{`${userName || workspaceName}: ${activeDomain || statusLabel}`}</span>
              <span
                aria-hidden="true"
                className={clsx(
                  "h-2.5 w-2.5 rounded-full motion-safe:animate-pulse",
                  domainUnavailable ? "bg-on-surface-variant" : isProtected ? "bg-safe" : "bg-warning",
                )}
              />
            </div>
          ) : (
            <div className="rounded-xl border border-border-subtle bg-surface-low/60 px-3.5 py-3">
              <div className="flex items-center gap-2">
                <span
                  className="truncate text-[13px] font-bold text-on-surface"
                  title={userName || workspaceName}
                >
                  {userName || workspaceName}
                </span>
              </div>
              {domainUnavailable ? (
                <p className="mt-2 text-xs text-on-surface-variant" role={isLoading ? "status" : undefined}>
                  {statusLabel}
                </p>
              ) : domains.length > 1 ? (
                <select
                  value={activeDomain}
                  onChange={(event) => setActiveDomain(event.target.value)}
                  className="mt-2 w-full rounded-md border border-border-subtle bg-surface-lowest px-2 py-1.5 text-xs font-semibold text-on-surface focus:border-primary focus:outline-none"
                  aria-label={t("sidebar.active_domain")}
                >
                  {domains.map((domain) => (
                    <option key={domain.id || domain.zone_name} value={domain.zone_name}>
                      {domain.zone_name}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="mt-2 truncate text-xs font-semibold text-on-surface">
                  {activeDomain || t("sidebar.no_domain")}
                </p>
              )}
              {!domainUnavailable && <p className="mt-1.5 flex items-center gap-1.5 text-[11px] font-medium text-on-surface-variant tabular-nums">
                <span className="relative flex h-2 w-2 shrink-0" aria-hidden="true">
                  <span
                    className={clsx(
                      "absolute inline-flex h-full w-full rounded-full opacity-70 motion-safe:animate-ping",
                      isProtected ? "bg-safe" : "bg-warning",
                    )}
                  />
                  <span
                    className={clsx(
                      "relative inline-flex h-2 w-2 rounded-full",
                      isProtected ? "bg-safe" : "bg-warning",
                    )}
                  />
                </span>
                <span className={isProtected ? "text-safe" : "text-warning"}>{statusLabel}</span>
                {domainKpis && ` · ${t("sidebar.emails_analysed", { count: domainKpis.raw_records_count })}`}
              </p>}
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
      <div className="space-y-1 border-t border-border-subtle px-3 pb-4 pt-3">
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

        <RailButton
          icon={LogOut}
          label={t("common.logout")}
          collapsed={collapsed}
          tone="danger"
          onClick={onLogout}
        />
      </div>
    </aside>
  );
}
