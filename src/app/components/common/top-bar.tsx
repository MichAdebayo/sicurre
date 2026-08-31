import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Bell,
  Cpu,
  Globe,
  Inbox,
  ArrowRight,
  CheckCircle2,
} from "lucide-react";
import { SidebarPage } from "./sidebar";
import {
  useAlertHistory,
  useAdminRuntimeHealth,
  useMarkAlertRead,
  useMarkDomainAlertsRead,
} from "../../lib/api";
import { useActiveDomain } from "../../contexts/active-domain";

interface TopBarProps {
  userName?: string;
  userRole?: string;
  administration?: boolean;
  onboardingRequired?: boolean;
  onPageChange?: (page: SidebarPage) => void;
}

export function TopBar({
  userName = "SA",
  administration = false,
  onboardingRequired = false,
  onPageChange,
}: TopBarProps) {
  const { t, i18n } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const runtimeHealth = useAdminRuntimeHealth(administration);
  const { activeDomain } = useActiveDomain();
  const { data: alertHistory } = useAlertHistory(administration ? "" : activeDomain);
  const markAlertReadMutation = useMarkAlertRead(activeDomain);
  const markReadMutation = useMarkDomainAlertsRead(activeDomain);

  const timeSince = (dateStr: string) => {
    if (!dateStr) return t("topbar.now");
    const now = new Date();
    const diff = now.getTime() - new Date(dateStr).getTime();
    if (isNaN(diff) || diff < 0) return t("topbar.now");
    
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return t("topbar.less_than_minute");
    if (mins < 60) return t("topbar.minutes_ago", { count: mins });
    const hours = Math.floor(mins / 60);
    if (hours < 24) return t("topbar.hours_ago", { count: hours });
    return new Date(dateStr).toLocaleDateString(i18n.language === "fr" ? "fr-FR" : "en-US", { day: "numeric", month: "short" });
  };

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
    category: "Critical" | "Domain" | "System";
    page?: SidebarPage;
    unread: boolean;
  }[] = [];

  if (onboardingRequired && !administration) {
    notificationsList.push({
      id: "onboarding_cloudflare_required",
      title: t("topbar.connect_cloudflare"),
      desc: t("topbar.connect_cloudflare_desc"),
      time: t("topbar.now"),
      category: "Domain" as const,
      page: "settings" as const,
      unread: true,
    });
  }

  const recentAlertHistory = !onboardingRequired
    ? (alertHistory || []).slice(0, 4).map((alert) => ({
        id: `alert_history_${alert.id}`,
        title: alert.title,
        desc: alert.message,
        time: timeSince(alert.created_at),
        category: alert.event_type === "domain_shield" ? "Domain" as const : "System" as const,
        page: alert.action_page as SidebarPage | undefined,
        unread: !alert.is_read,
      }))
    : [];
  notificationsList.push(...recentAlertHistory);

  // Capped list of notifications (display most recent 4)
  const cappedNotifs = notificationsList.slice(0, 4);

  const unreadCount = notificationsList.filter((item) => item.unread).length;

  const markAllRead = (e: React.MouseEvent) => {
    e.stopPropagation();
    markReadMutation.mutate();
  };

  const getCategoryIconContainer = (category: "Critical" | "Domain" | "System") => {
    const domain = category === "Domain";
    const bg = domain ? "bg-warning-bg" : "bg-primary/10";
    const icon = domain
        ? <Globe className="w-4 h-4 text-warning" />
        : <Inbox className="w-4 h-4 text-primary" />;
    return (
      <div className={`p-2 rounded-lg shrink-0 ${bg}`}>
        {icon}
      </div>
    );
  };

  return (
    <header className="h-14 min-w-0 flex-1 bg-transparent px-0 flex items-center justify-between shrink-0 relative z-40">
      {/* Title Placeholder / Brand Space to balance the header layout */}
      <div className="truncate font-display font-semibold text-sm text-on-surface-variant opacity-80">
        {!administration && activeDomain
          ? activeDomain
          : t("topbar.console_name")}
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4 relative">
        {/* System Status (Visible ONLY to platform administrators) */}
        {administration && (
          <div className="flex items-center gap-2 pr-2 border-r border-border-subtle/50">
            <span className="relative flex h-2 w-2">
              {runtimeHealth.data?.status === "ok" && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-safe" />
              )}
              <span className={`relative inline-flex rounded-full h-2 w-2 ${
                runtimeHealth.data?.status === "down"
                  ? "bg-error"
                  : runtimeHealth.data?.status === "degraded"
                  ? "bg-warning"
                  : runtimeHealth.data?.status === "unknown"
                  ? "bg-on-surface-variant"
                  : "bg-safe"
              }`} />
            </span>
            <span className="text-[9px] font-bold text-on-surface-variant/80 uppercase flex items-center gap-1">
              <Cpu className="w-3 h-3 text-primary" />
              {runtimeHealth.data?.status === "down"
                ? t("topbar.runtime_incident")
                : runtimeHealth.data?.status === "degraded"
                ? t("topbar.runtime_degraded")
                : runtimeHealth.isLoading
                ? t("topbar.checking")
                : t("topbar.system_operational")}
            </span>
          </div>
        )}

        {/* Notifications Icon Button */}
        {!administration && <button
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          className="relative rounded-lg border border-border-subtle bg-surface-lowest/80 p-2 text-on-surface-variant transition-[background-color,border-color,transform] duration-200 hover:border-primary/35 hover:bg-primary-fixed hover:text-primary active:scale-[0.98] dark:bg-surface-low dark:hover:bg-primary-container dark:hover:text-on-primary-container"
          aria-label={t("topbar.open_notifications")}
        >
          <Bell className="w-[22px] h-[22px] stroke-[1.5]" />
          {unreadCount > 0 && (
            <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-error rounded-full ring-2 ring-surface-lowest dark:ring-surface-low" />
          )}
        </button>}

        {/* Notifications Floating Dropdown Overlay */}
        {!administration && isOpen && (
          <div
            onClick={(e) => e.stopPropagation()}
            className="absolute right-0 top-11 z-50 w-[min(24rem,calc(100vw-2rem))] rounded-lg border border-border-subtle bg-surface-lowest p-4 text-on-surface shadow-xl shadow-primary/10 animate-in fade-in slide-in-from-top-1 duration-150 font-sans dark:bg-surface-low"
          >
            {/* Popover Header */}
            <div className="flex items-center justify-between pb-3.5 border-b border-border-subtle">
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm text-on-surface">{t("topbar.notifications")}</span>
                {unreadCount > 0 && (
                  <span className="text-[10px] font-bold bg-error/10 text-error px-2 py-0.5 rounded-full">
                    {t("topbar.unread", { count: unreadCount })}
                  </span>
                )}
              </div>
              <button
                onClick={markAllRead}
                className="text-[11px] font-bold text-primary hover:text-navy-dark transition-colors cursor-pointer"
              >
                {t("topbar.mark_all_read")}
              </button>
            </div>

            {/* Notification items list */}
            <div className="space-y-1.5 max-h-[340px] overflow-y-auto pt-3 select-none pr-1">
              {cappedNotifs.length === 0 ? (
                <div className="py-8 text-center">
                  <CheckCircle2 className="mx-auto mb-2 h-7 w-7 text-safe/60" />
                  <p className="text-xs font-semibold text-on-surface">
                    {t("topbar.no_active_alerts")}
                  </p>
                  <p className="mt-1 text-[11px] text-on-surface-variant">
                    {t("topbar.no_active_alerts_desc")}
                  </p>
                </div>
              ) : (
                cappedNotifs.map((notif) => {
                  const isUnread = notif.unread;
                  return (
                    <div
                      key={notif.id}
                      onClick={() => {
                        if (notif.id.startsWith("alert_history_")) {
                          markAlertReadMutation.mutate(notif.id.replace("alert_history_", ""));
                        }
                        if (notif.page && onPageChange) {
                          onPageChange(notif.page);
                        }
                        setIsOpen(false);
                      }}
                      className={`flex items-start gap-3 p-2.5 rounded-lg border border-transparent transition-colors ${notif.page ? "cursor-pointer hover:border-border-subtle hover:bg-surface-low" : "cursor-default"}`}
                    >
                      {/* Icon */}
                      {getCategoryIconContainer(notif.category)}

                      {/* Content */}
                      <div className="flex-1 min-w-0 space-y-0.5">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="block truncate text-sm font-semibold text-on-surface">
                            {notif.title}
                          </span>
                          <span className="shrink-0 text-xs text-on-surface-variant/70">
                            {notif.time}
                          </span>
                        </div>
                        <p className="text-[13px] text-on-surface-variant leading-5 line-clamp-2">
                          {notif.desc}
                        </p>
                        {isUnread && <span className="mt-1 block h-1.5 w-1.5 rounded-full bg-primary" />}
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
                    ? t("topbar.open_setup")
                    : t("topbar.view_all_alerts")}
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
