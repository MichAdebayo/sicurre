import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Bell,
  Cpu,
  ShieldAlert,
  Globe,
  Inbox,
  ArrowRight,
  CheckCircle2,
} from "lucide-react";
import { SidebarPage } from "./sidebar";
import {
  useThreatLogs,
  useCloudflareList,
  useDomainShieldStatus,
  useQuarantineItems,
  useAlertHistory,
} from "../../lib/api";

interface TopBarProps {
  userName?: string;
  userRole?: string;
  onboardingRequired?: boolean;
  onPageChange?: (page: SidebarPage) => void;
}

export function TopBar({
  userName = "SA",
  userRole = "owner",
  onboardingRequired = false,
  onPageChange,
}: TopBarProps) {
  const { t, i18n } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  // Persistent notification read IDs using localStorage
  const [readIds, setReadIds] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem("sicurre_read_notif_ids");
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem("sicurre_read_notif_ids", JSON.stringify(readIds));
    } catch (e) {
      console.error(e);
    }
  }, [readIds]);

  const timeSince = (dateStr: string) => {
    if (!dateStr) return i18n.language === "fr" ? "maintenant" : "now";
    const now = new Date();
    const diff = now.getTime() - new Date(dateStr).getTime();
    if (isNaN(diff) || diff < 0) return i18n.language === "fr" ? "maintenant" : "now";
    
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return i18n.language === "fr" ? "< 1 min" : "< 1m";
    if (mins < 60) return i18n.language === "fr" ? `il y a ${mins} min` : `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return i18n.language === "fr" ? `il y a ${hours} h` : `${hours}h ago`;
    return new Date(dateStr).toLocaleDateString(i18n.language === "fr" ? "fr-FR" : "en-US", { day: "numeric", month: "short" });
  };

  // Load real-time workspace data to build dynamic actionable notifications
  const { data: threats } = useThreatLogs();
  const { data: domains } = useCloudflareList();
  const { data: quarantineItems } = useQuarantineItems();
  const { data: alertHistory } = useAlertHistory();

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

  if (onboardingRequired && userRole !== "admin") {
    notificationsList.push({
      id: "onboarding_cloudflare_required",
      title: i18n.language === "fr" ? "Connectez Cloudflare" : "Connect Cloudflare",
      desc: i18n.language === "fr"
        ? "Ajoutez votre token pour activer le routage email."
        : "Add your token to enable email routing.",
      time: i18n.language === "fr" ? "maintenant" : "now",
      badge: "Setup",
      category: "Domain" as const,
      page: "settings" as const,
      unread: true,
    });
  }

  const recentAlertHistory = !onboardingRequired
    ? (alertHistory || []).slice(0, 3).map((alert) => ({
        id: `alert_history_${alert.id}`,
        title: alert.title,
        desc: alert.message,
        time: timeSince(alert.created_at),
        badge: i18n.language === "fr" ? "Alertes" : "Alerts",
        category: "System" as const,
        page: "alerts" as const,
        unread: true,
      }))
    : [];
  notificationsList.push(...recentAlertHistory);

  // 1. Phishing alerts
  const activePhishing = threats?.filter(t => t.verdict === "phishing" && t.status === "active") || [];
  if (!onboardingRequired && activePhishing.length > 0) {
    const latest = activePhishing[0];
    notificationsList.push({
      id: "phish_blocked_" + latest.id,
      title: i18n.language === "fr" ? "Email de phishing bloqué" : "Phishing email blocked",
      desc: `${latest.sender} · ${latest.subject}`,
      time: timeSince(latest.received_at),
      badge: "Threat log",
      category: "Critical" as const,
      page: "threats" as const,
      unread: true,
    });
  }

  // 2. SSL Expiry Alert
  if (!onboardingRequired && shieldStatus && shieldStatus.ssl.valid && shieldStatus.ssl.days_remaining < 30) {
    notificationsList.push({
      id: "ssl_expiring",
      title: i18n.language === "fr" ? "Certificat SSL expirant bientôt" : "SSL certificate expiring soon",
      desc: i18n.language === "fr"
        ? `${activeDomain} expire dans ${shieldStatus.ssl.days_remaining} jours`
        : `${activeDomain} certificate expires in ${shieldStatus.ssl.days_remaining} days`,
      time: shieldStatus.updated_at ? timeSince(shieldStatus.updated_at) : "",
      badge: "Domain shield",
      category: "Domain" as const,
      page: "domain-shield" as const,
      unread: true,
    });
  }

  // 3. DMARC policy warning
  if (!onboardingRequired && shieldStatus && (!shieldStatus.dmarc.valid || shieldStatus.dmarc.policy === "none")) {
    notificationsList.push({
      id: "dmarc_none",
      title: i18n.language === "fr" ? 'Politique DMARC définie sur "none"' : 'DMARC policy is set to "none"',
      desc: i18n.language === "fr"
        ? `@${activeDomain} peut être usurpé. Modifiez la politique.`
        : `@${activeDomain} can be spoofed. Change the policy.`,
      time: shieldStatus.updated_at ? timeSince(shieldStatus.updated_at) : "",
      badge: "Domain shield",
      category: "Domain" as const,
      page: "domain-shield" as const,
      unread: true,
    });
  }

  // 4. Quarantine waiting emails
  if (!onboardingRequired && quarantineItems && quarantineItems.length > 0) {
    notificationsList.push({
      id: "quarantine_held",
      title: i18n.language === "fr" ? `${quarantineItems.length} emails en quarantaine` : `${quarantineItems.length} emails waiting in quarantine`,
      desc: i18n.language === "fr"
        ? `Expéditeurs: ${quarantineItems.map(i => i.sender.split("@")[0]).slice(0, 2).join(", ")}`
        : `Held from: ${quarantineItems.map(i => i.sender.split("@")[0]).slice(0, 2).join(", ")}`,
      time: quarantineItems && quarantineItems.length > 0 ? timeSince(quarantineItems[0].created_at) : i18n.language === "fr" ? "il y a 14 h" : "14h ago",
      badge: "Quarantine",
      category: "System" as const,
      page: "quarantine" as const,
      unread: true,
    });
  }

  // Capped list of notifications (display most recent 4)
  const cappedNotifs = notificationsList.slice(0, 4);

  const unreadCount = notificationsList.filter(n => n.unread && !readIds.includes(n.id)).length;

  const markAllRead = (e: React.MouseEvent) => {
    e.stopPropagation();
    setReadIds(notificationsList.map(n => n.id));
  };

  const getCategoryIconContainer = (badge: string) => {
    let bg = "bg-error/10";
    let icon = <ShieldAlert className="w-4 h-4 text-error" />;
    if (badge === "Threat log") {
      bg = "bg-error/10";
      icon = <ShieldAlert className="w-4 h-4 text-error" />;
    } else if (badge === "Domain shield") {
      bg = "bg-amber-500/10";
      icon = <Globe className="w-4 h-4 text-amber-700" />;
    } else if (badge === "Quarantine") {
      bg = "bg-primary/10";
      icon = <Inbox className="w-4 h-4 text-primary" />;
    } else if (badge === "Setup") {
      bg = "bg-primary/10";
      icon = <Globe className="w-4 h-4 text-primary" />;
    } else if (badge === "Alertes" || badge === "Alerts") {
      bg = "bg-primary/10";
      icon = <Bell className="w-4 h-4 text-primary" />;
    } else {
      bg = "bg-surface-low";
      icon = <Cpu className="w-4 h-4 text-on-surface-variant" />;
    }
    return (
      <div className={`p-2 rounded-lg shrink-0 ${bg}`}>
        {icon}
      </div>
    );
  };

  const getBadgeStyle = (badge: string) => {
    if (badge === "Threat log") return "bg-error/10 text-error border border-error/20";
    if (badge === "Domain shield") return "bg-amber-500/10 text-amber-700 border border-amber-500/20";
    if (badge === "Setup") return "bg-primary/10 text-primary border border-primary/20";
    if (badge === "Alertes" || badge === "Alerts") return "bg-primary/10 text-primary border border-primary/20";
    return "bg-primary/10 text-primary border border-primary/20";
  };

  return (
    <header className="h-14 bg-transparent px-0 flex items-center justify-between shrink-0 relative z-40">
      {/* Title Placeholder / Brand Space to balance the header layout */}
      <div className="font-display font-semibold text-sm text-on-surface-variant opacity-80">
        {activeDomain ? `${activeDomain} Workspace` : "Sicurre Console"}
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
            <span className="text-[9px] font-bold text-on-surface-variant/80 uppercase flex items-center gap-1">
              <Cpu className="w-3 h-3 text-primary" />
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
          className="relative rounded-lg border border-border-subtle bg-surface-lowest/80 p-2 text-on-surface-variant transition-[background-color,border-color,transform] duration-200 hover:border-primary/35 hover:bg-primary-fixed hover:text-primary active:scale-[0.98] dark:bg-surface-low dark:hover:bg-primary-container dark:hover:text-on-primary-container"
          aria-label={i18n.language === "fr" ? "Ouvrir les notifications" : "Open notifications"}
        >
          <Bell className="w-[22px] h-[22px] stroke-[1.5]" />
          {unreadCount > 0 && (
            <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-error rounded-full ring-2 ring-surface-lowest dark:ring-surface-low" />
          )}
        </button>

        {/* Notifications Floating Dropdown Overlay */}
        {isOpen && (
          <div
            onClick={(e) => e.stopPropagation()}
            className="absolute right-0 top-11 z-50 w-[min(24rem,calc(100vw-2rem))] rounded-lg border border-border-subtle bg-surface-lowest p-4 text-on-surface shadow-xl shadow-primary/10 animate-in fade-in slide-in-from-top-1 duration-150 font-sans dark:bg-surface-low"
          >
            {/* Popover Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-border-subtle">
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm text-on-surface">Notifications</span>
                {unreadCount > 0 && (
                  <span className="text-[10px] font-bold bg-error/10 text-error px-2 py-0.5 rounded-full">
                    {unreadCount} {i18n.language === "fr" ? "non lues" : "unread"}
                  </span>
                )}
              </div>
              <button
                onClick={markAllRead}
                className="text-[11px] font-bold text-primary hover:text-navy-dark transition-colors cursor-pointer"
              >
                {i18n.language === "fr" ? "Tout marquer lu" : "Mark all read"}
              </button>
            </div>

            {/* Notification items list */}
            <div className="space-y-1.5 max-h-[340px] overflow-y-auto pt-3 select-none pr-1">
              {cappedNotifs.length === 0 ? (
                <div className="py-8 text-center">
                  <CheckCircle2 className="mx-auto mb-2 h-7 w-7 text-safe/60" />
                  <p className="text-xs font-semibold text-on-surface">
                    {i18n.language === "fr" ? "Aucune alerte active" : "No active alerts"}
                  </p>
                  <p className="mt-1 text-[11px] text-on-surface-variant">
                    {i18n.language === "fr" ? "Les nouvelles alertes apparaîtront ici." : "New alerts will appear here."}
                  </p>
                </div>
              ) : (
                cappedNotifs.map((notif) => {
                  const isUnread = notif.unread && !readIds.includes(notif.id);
                  return (
                    <div
                      key={notif.id}
                      onClick={() => {
                        setReadIds((prev) => [...prev, notif.id]);
                        if (onPageChange) {
                          onPageChange(notif.page);
                        }
                        setIsOpen(false);
                      }}
                      className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-surface-low transition-colors cursor-pointer border border-transparent hover:border-border-subtle"
                    >
                      {/* Icon */}
                      {getCategoryIconContainer(notif.badge)}

                      {/* Content */}
                      <div className="flex-1 min-w-0 space-y-0.5">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="font-bold text-xs text-on-surface truncate block">
                            {notif.title}
                          </span>
                          <span className="text-[10px] text-on-surface-variant/70 font-mono shrink-0">
                            {notif.time}
                          </span>
                        </div>
                        <p className="text-[11px] text-on-surface-variant leading-normal truncate">
                          {notif.desc}
                        </p>
                        <div className="flex items-center justify-between pt-1">
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${getBadgeStyle(notif.badge)}`}>
                            {notif.badge}
                          </span>
                          {isUnread && (
                            <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* View All Footer Link */}
            <div className="pt-3 mt-2 border-t border-border-subtle flex justify-center">
              <button
                onClick={() => {
                  if (onPageChange) onPageChange(onboardingRequired ? "settings" : "alerts");
                  setIsOpen(false);
                }}
                className="text-xs font-bold text-primary hover:text-navy-dark hover:underline cursor-pointer flex items-center gap-1.5 py-1"
              >
                <span>
                  {onboardingRequired
                    ? i18n.language === "fr" ? "Ouvrir la configuration" : "Open setup"
                    : i18n.language === "fr" ? "Voir toutes les alertes" : "View all alerts"}
                </span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
