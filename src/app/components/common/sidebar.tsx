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
} from "lucide-react";
import sicurreLogo from "../../assets/sicurre.svg";

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
  userName?: string;
  userEmail?: string;
  userRole?: string;
  onboardingRequired?: boolean;
  className?: string;
}

export function Sidebar({
  currentPage,
  onPageChange,
  onLogout,
  onLockdown,
  userName = "Utilisateur",
  userEmail = "",
  userRole = "owner",
  onboardingRequired = false,
  className,
}: SidebarProps) {
  const { t } = useTranslation();
  const isOnboardingLocked = onboardingRequired && userRole !== "admin";

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
      <div className="px-5 py-5">
        <div className="flex items-center gap-3">
          <img src={sicurreLogo} alt="Sicurre" className="w-16 h-16" />
          <div className="flex flex-col">
            <span className="font-display font-bold text-3xl text-on-surface leading-tight">
              Sicurre
            </span>
          </div>
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-5 space-y-0.5 overflow-y-auto">
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
                "w-full flex items-center gap-3 px-3.5 py-2.5 text-[13px] font-semibold rounded-lg transition-all duration-150 select-none",
                isLocked
                  ? "cursor-not-allowed text-on-surface-variant/35 opacity-70"
                  : isActive
                  ? "bg-primary text-on-primary shadow-sm shadow-primary/20"
                  : "cursor-pointer text-on-surface-variant hover:bg-surface-low hover:text-on-surface",
              )}
            >
              <Icon className="w-[18px] h-[18px] stroke-[1.5]" />
              <span className="flex-1 text-left">{item.label}</span>
              {isLocked && <LockKeyhole className="h-3.5 w-3.5" />}
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
                "w-full flex items-center gap-3 px-3.5 py-2.5 text-[13px] font-semibold rounded-lg transition-all cursor-pointer select-none",
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
            className="w-full flex items-center justify-center gap-2 px-3.5 py-2.5 bg-error text-on-error hover:bg-on-error-container font-semibold rounded-lg transition-all active:scale-[0.97] cursor-pointer text-[13px]"
          >
            <Zap className="w-4 h-4" />
            <span>{t("sidebar.lockdown")}</span>
          </button>
        )}

        {/* User Profile */}
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-surface-low/70 border border-border-subtle/50 dark:bg-surface">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-primary/[0.08] text-primary flex items-center justify-center font-display font-bold text-[12px] shrink-0">
              {userName.substring(0, 2).toUpperCase()}
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-[13px] font-bold text-on-surface truncate leading-tight">
                {userName}
              </span>
              <span className="text-[10px] text-on-surface-variant/60 truncate leading-tight">
                {userEmail}
              </span>
            </div>
          </div>
          <button
            onClick={onLogout}
            title={t("common.logout")}
            className="p-1.5 rounded-md text-on-surface-variant/50 hover:bg-surface-container hover:text-error transition-colors cursor-pointer"
          >
            <LogOut className="w-4 h-4 stroke-[1.5]" />
          </button>
        </div>
      </div>
    </aside>
  );
}
