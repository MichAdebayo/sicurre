import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Bell,
  Search,
  Cpu,
  ShieldAlert,
  AlertTriangle,
  Globe,
  Inbox,
  X,
  Check,
} from "lucide-react";
import { SidebarPage } from "./sidebar";
import {
  useThreatLogs,
  useCloudflareList,
  useDomainShieldStatus,
  useQuarantineItems,
} from "../../lib/api";

interface TopBarProps {
  onSearch?: (query: string) => void;
  userName?: string;
  userRole?: string;
  onPageChange?: (page: SidebarPage) => void;
}

export function TopBar({
  onSearch,
  userName = "SA",
  userRole = "owner",
  onPageChange,
}: TopBarProps) {
  const { t, i18n } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [activeFilter, setActiveFilter] = useState<"All" | "Critical" | "Domain" | "System">("All");
  const [readIds, setReadIds] = useState<string[]>([]);

  // Load real-time workspace data to build dynamic actionable notifications
  const { data: threats } = useThreatLogs();
  const { data: domains } = useCloudflareList();
  const { data: quarantineItems } = useQuarantineItems();

  const activeDomain = domains && domains.length > 0
    ? (domains.find((d) => d.status === "active")?.zone_name || domains[0].zone_name)
    : "";

  const { data: shieldStatus } = useDomainShieldStatus(activeDomain || "", !!activeDomain);

  // Auto-close popover on click-away
  useEffect(() => {
    if (!isOpen) return;
    const handleClose = () => setIsOpen(false);
    window.addEventListener("click", handleClose);
    return () => window.removeEventListener("click", handleClose);
  }, [isOpen]);

  // Construct dynamic actionable list
  const notificationsList: {
    id: string;
    title: string;
    desc: string;
    time: string;
    badge: string;
    category: "Critical" | "Domain" | "System";
    page: SidebarPage;
    unread: boolean;
  }[] = [];

  // 1. Phishing alerts
  const activePhishing = threats?.filter(t => t.verdict === "phishing" && t.status === "active") || [];
  if (activePhishing.length > 0) {
    const latest = activePhishing[0];
    notificationsList.push({
      id: "phish_blocked_" + latest.id,
      title: i18n.language === "fr" ? "Email de phishing bloqué" : "Phishing email blocked",
      desc: `${latest.sender} · ${latest.subject}`,
      time: "just now",
      badge: "Threat log",
      category: "Critical" as const,
      page: "threats" as const,
      unread: true,
    });
  }

  // 2. Dark Web leak simulation (Vinse breach alert matches user domain context)
  if (activeDomain) {
    notificationsList.push({
      id: "breach_detected",
      title: i18n.language === "fr" ? `Fuite détectée · ${activeDomain}` : `Breach detected · ${activeDomain}`,
      desc: `${userName.toLowerCase().replace(/\s+/g, "")}@${activeDomain} found in "DataCombo2026"`,
      time: "4h ago",
      badge: "Dark web",
      category: "Critical" as const,
      page: "alerts" as const,
      unread: true,
    });
  }

  // 3. SSL Expiry Alert
  if (shieldStatus && shieldStatus.ssl.valid && shieldStatus.ssl.days_remaining < 30) {
    notificationsList.push({
      id: "ssl_expiring",
      title: i18n.language === "fr" ? "Certificat SSL expirant bientôt" : "SSL certificate expiring soon",
      desc: `${activeDomain} certificate expires in ${shieldStatus.ssl.days_remaining} days`,
      time: "13h ago",
      badge: "Domain shield",
      category: "Domain" as const,
      page: "domain-shield" as const,
      unread: true,
    });
  }

  // 4. DMARC policy warning
  if (shieldStatus && (!shieldStatus.dmarc.valid || shieldStatus.dmarc.policy === "none")) {
    notificationsList.push({
      id: "dmarc_none",
      title: i18n.language === "fr" ? 'Politique DMARC définie sur "none"' : 'DMARC policy is set to "none"',
      desc: `Anyone can spoof @${activeDomain} — change policy`,
      time: "Yesterday",
      badge: "Domain shield",
      category: "Domain" as const,
      page: "domain-shield" as const,
      unread: true,
    });
  }

  // 5. Quarantine waiting emails
  if (quarantineItems && quarantineItems.length > 0) {
    notificationsList.push({
      id: "quarantine_held",
      title: i18n.language === "fr" ? `${quarantineItems.length} emails en quarantaine` : `${quarantineItems.length} emails waiting in quarantine`,
      desc: `Held from: ${quarantineItems.map(i => i.sender.split("@")[0]).slice(0, 2).join(", ")}...`,
      time: "14h ago",
      badge: "Quarantine",
      category: "System" as const,
      page: "quarantine" as const,
      unread: true,
    });
  }

  // 6. Generic system notification fallback
  if (notificationsList.length === 0) {
    notificationsList.push({
      id: "system_ok",
      title: "All perimeters protected",
      desc: "No active threats, SSL and domain settings optimal.",
      time: "just now",
      badge: "System",
      category: "System" as const,
      page: "dashboard" as const,
      unread: false,
    });
  }

  // Filter list
  const filteredNotifs = notificationsList.filter((n) => {
    if (activeFilter === "All") return true;
    return n.category === activeFilter;
  });

  const unreadCount = notificationsList.filter(n => n.unread && !readIds.includes(n.id)).length;

  const markAllRead = (e: React.MouseEvent) => {
    e.stopPropagation();
    setReadIds(notificationsList.map(n => n.id));
  };

  const getCategoryIconContainer = (badge: string) => {
    let bg = "bg-red-500/10";
    let icon = <ShieldAlert className="w-4 h-4 text-red-400" />;
    if (badge === "Threat log") {
      bg = "bg-red-500/10";
      icon = <ShieldAlert className="w-4 h-4 text-red-400" />;
    } else if (badge === "Dark web") {
      bg = "bg-purple-500/10";
      icon = <AlertTriangle className="w-4 h-4 text-purple-400" />;
    } else if (badge === "Domain shield") {
      bg = "bg-amber-500/10";
      icon = <Globe className="w-4 h-4 text-amber-400" />;
    } else if (badge === "Quarantine") {
      bg = "bg-blue-500/10";
      icon = <Inbox className="w-4 h-4 text-blue-400" />;
    } else {
      bg = "bg-neutral-500/10";
      icon = <Cpu className="w-4 h-4 text-neutral-400" />;
    }
    return (
      <div className={`p-2 rounded-xl shrink-0 ${bg}`}>
        {icon}
      </div>
    );
  };

  const getBadgeStyle = (badge: string) => {
    if (badge === "Threat log") return "bg-red-500/10 text-red-400 border border-red-500/20";
    if (badge === "Dark web") return "bg-purple-500/10 text-purple-400 border border-purple-500/20";
    if (badge === "Domain shield") return "bg-amber-500/10 text-amber-400 border border-amber-500/20";
    return "bg-blue-500/10 text-blue-400 border border-blue-500/20";
  };

  return (
    <header className="h-14 bg-transparent px-6 flex items-center justify-between shrink-0 relative z-40">
      {/* Search */}
      <div className="relative w-80">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant/30" />
        <input
          type="text"
          placeholder={i18n.language === "fr" ? "Rechercher des paramètres de sécurité..." : "Search security parameters..."}
          onChange={(e) => onSearch?.(e.target.value)}
          className="w-full pl-9 pr-4 py-2 bg-white/70 backdrop-blur-md border border-border-subtle rounded-lg text-[13px] text-on-surface placeholder:text-on-surface-variant/35 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all shadow-sm"
        />
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4 relative">
        {/* System Status (Visible ONLY to platform administrators) */}
        {userRole === "admin" && (
          <div className="flex items-center gap-2 pr-2 border-r border-border-subtle/50">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-safe" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-safe" />
            </span>
            <span className="text-[9px] font-bold text-on-surface-variant/50 tracking-[0.12em] uppercase flex items-center gap-1">
              <Cpu className="w-3 h-3" />
              {i18n.language === "fr" ? "Système Actif" : "System Operational"}
            </span>
          </div>
        )}

        {/* Notifications Icon Button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          className="relative p-2 rounded-lg text-on-surface-variant/60 hover:bg-white hover:text-on-surface hover:shadow-sm border border-transparent hover:border-border-subtle transition-all cursor-pointer bg-white/50 backdrop-blur-sm"
        >
          <Bell className="w-[18px] h-[18px] stroke-[1.5]" />
          {unreadCount > 0 && (
            <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-error rounded-full ring-2 ring-white" />
          )}
        </button>

        {/* Notifications Floating Dropdown Overlay */}
        {isOpen && (
          <div
            onClick={(e) => e.stopPropagation()}
            className="absolute right-0 top-11 w-96 bg-[#171717] border border-neutral-800 rounded-2xl shadow-2xl p-4 text-white z-50 animate-in fade-in slide-in-from-top-1 duration-150 font-sans"
          >
            {/* Popover Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-neutral-800/80">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm">Notifications</span>
                {unreadCount > 0 && (
                  <span className="text-[10px] font-bold bg-error/15 text-error px-2 py-0.5 rounded-full">
                    {unreadCount} unread
                  </span>
                )}
              </div>
              <button
                onClick={markAllRead}
                className="text-[11px] font-semibold text-primary hover:text-primary-hover transition-colors cursor-pointer"
              >
                Mark all read
              </button>
            </div>

            {/* Filter Buttons */}
            <div className="flex gap-1.5 py-3">
              {(["All", "Critical", "Domain", "System"] as const).map((filter) => {
                const isActive = activeFilter === filter;
                return (
                  <button
                    key={filter}
                    onClick={() => setActiveFilter(filter)}
                    className={`px-3 py-1 rounded-lg text-[11px] font-semibold border transition-all cursor-pointer ${
                      isActive
                        ? "bg-neutral-800 text-white border-neutral-700 shadow-sm"
                        : "bg-transparent text-neutral-400 hover:text-neutral-200 border-transparent"
                    }`}
                  >
                    {filter}
                  </button>
                );
              })}
            </div>

            {/* Notification items list */}
            <div className="space-y-1.5 max-h-[340px] overflow-y-auto pt-1 select-none pr-1">
              {filteredNotifs.length === 0 ? (
                <div className="text-center py-8 text-xs text-neutral-500">
                  No notifications matching filter
                </div>
              ) : (
                filteredNotifs.map((notif) => {
                  const isUnread = notif.unread && !readIds.includes(notif.id);
                  return (
                    <div
                      key={notif.id}
                      onClick={() => {
                        if (onPageChange) {
                          onPageChange(notif.page);
                        }
                        setIsOpen(false);
                      }}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-neutral-800/50 transition-colors cursor-pointer border border-transparent hover:border-neutral-800"
                    >
                      {/* Icon */}
                      {getCategoryIconContainer(notif.badge)}

                      {/* Content */}
                      <div className="flex-1 min-w-0 space-y-0.5">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="font-bold text-xs text-neutral-100 truncate block">
                            {notif.title}
                          </span>
                          <span className="text-[10px] text-neutral-500 font-mono shrink-0">
                            {notif.time}
                          </span>
                        </div>
                        <p className="text-[11px] text-neutral-400 leading-normal truncate">
                          {notif.desc}
                        </p>
                        <div className="flex items-center justify-between pt-1">
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${getBadgeStyle(notif.badge)}`}>
                            {notif.badge}
                          </span>
                          {isUnread && (
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
