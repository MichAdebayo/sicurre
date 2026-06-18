import { clsx } from "clsx";
import {
  LayoutDashboard,
  ShieldAlert,
  History,
  Settings,
  HelpCircle,
  LogOut,
  Zap,
} from "lucide-react";
import sicurreLogo from "../../assets/sicurre.svg";

export type SidebarPage = "dashboard" | "threats" | "logs" | "settings" | "support";

interface SidebarProps {
  currentPage: SidebarPage;
  onPageChange: (page: SidebarPage) => void;
  onLogout: () => void;
  onLockdown?: () => void;
  userName?: string;
  userEmail?: string;
  className?: string;
}

export function Sidebar({
  currentPage,
  onPageChange,
  onLogout,
  onLockdown,
  userName = "Admin",
  userEmail = "admin@sicurre.fr",
  className,
}: SidebarProps) {
  const mainNav = [
    { id: "dashboard", label: "Overview", icon: LayoutDashboard },
    { id: "threats", label: "Threat Intel", icon: ShieldAlert },
    { id: "logs", label: "Audit Logs", icon: History },
    { id: "settings", label: "Settings", icon: Settings },
  ] as const;

  const bottomNav = [
    { id: "support", label: "Support", icon: HelpCircle },
  ] as const;

  return (
    <aside
      className={clsx(
        "w-[240px] h-screen border-r border-border-subtle bg-white flex flex-col shrink-0",
        className,
      )}
    >
      {/* Logo */}
      <div className="px-5 py-5 border-b border-border-subtle">
        <div className="flex items-center gap-3">
          <img src={sicurreLogo} alt="Sicurre" className="w-16 h-16" />
          <div className="flex flex-col">
            <span className="font-display font-bold text-3xl text-on-surface leading-tight tracking-tight">
              Sicurre
            </span>
            <span className="text-[9px] font-bold text-primary/60 uppercase tracking-[0.15em]">
              Shield Active
            </span>
          </div>
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-5 space-y-0.5 overflow-y-auto">
        {mainNav.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id)}
              className={clsx(
                "w-full flex items-center gap-3 px-3.5 py-2.5 text-[13px] font-semibold rounded-lg transition-all duration-150 cursor-pointer select-none",
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
      </nav>

      {/* Bottom Section */}
      <div className="px-3 pb-4 space-y-3 border-t border-border-subtle pt-3">
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
            <span>Emergency Lockdown</span>
          </button>
        )}

        {/* User Profile */}
        <div className="flex items-center justify-between p-2.5 rounded-xl bg-surface-low/50 border border-border-subtle/50">
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
            title="Se déconnecter"
            className="p-1.5 rounded-md text-on-surface-variant/50 hover:bg-surface-container hover:text-error transition-colors cursor-pointer"
          >
            <LogOut className="w-4 h-4 stroke-[1.5]" />
          </button>
        </div>
      </div>
    </aside>
  );
}
