import { Bell, Search, Cpu } from "lucide-react";

interface TopBarProps {
  notificationCount?: number;
  onSearch?: (query: string) => void;
  systemStatus?: "operational" | "alert" | "degraded";
  userName?: string;
  userRole?: string;
}

export function TopBar({
  notificationCount = 3,
  onSearch,
  systemStatus = "operational",
  userName = "SA",
  userRole = "owner",
}: TopBarProps) {
  const roleLabel =
    userRole === "admin"
      ? "Sicurre Admin"
      : userRole === "owner"
      ? "Workspace Owner"
      : "Workspace User";

  return (
    <header className="h-14 border-b border-border-subtle bg-white px-6 flex items-center justify-between shrink-0">
      {/* Search */}
      <div className="relative w-80">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant/30" />
        <input
          type="text"
          placeholder="Rechercher des paramètres de sécurité..."
          onChange={(e) => onSearch?.(e.target.value)}
          className="w-full pl-9 pr-4 py-2 bg-surface-low border border-border-subtle rounded-lg text-[13px] text-on-surface placeholder:text-on-surface-variant/35 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all"
        />
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4">
        {/* System Status */}
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                systemStatus === "operational" ? "bg-safe" : "bg-error"
              }`}
            />
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                systemStatus === "operational" ? "bg-safe" : "bg-error"
              }`}
            />
          </span>
          <span className="text-[9px] font-bold text-on-surface-variant/50 tracking-[0.12em] uppercase flex items-center gap-1">
            <Cpu className="w-3 h-3" />
            {systemStatus === "operational" ? "Système Actif" : "Alerte Système"}
          </span>
        </div>

        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-on-surface-variant/60 hover:bg-surface-low hover:text-on-surface transition-all cursor-pointer">
          <Bell className="w-[18px] h-[18px] stroke-[1.5]" />
          {notificationCount > 0 && (
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-error rounded-full ring-2 ring-white" />
          )}
        </button>

        {/* Divider */}
        <div className="h-5 w-px bg-border-subtle" />

        {/* User */}
        <div className="flex items-center gap-2.5">
          <div className="text-right hidden sm:block">
            <div className="text-[9px] font-bold text-primary/70 uppercase tracking-[0.12em]">
              {roleLabel}
            </div>
            <div className="text-[9px] text-on-surface-variant/50 uppercase tracking-wider">
              Session Active
            </div>
          </div>
          <div className="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center font-display font-bold text-[11px]">
            {userName.substring(0, 2).toUpperCase()}
          </div>
        </div>
      </div>
    </header>
  );
}
