import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  LayoutDashboard,
  FileText,
  Mail,
  Database,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight
} from "lucide-react";

const MotionDiv = motion.div as any;

export interface NavbarProps {
  activeTab: "dashboard" | "threats" | "smail" | "datasets" | "settings";
  setActiveTab: (tab: "dashboard" | "threats" | "smail" | "datasets" | "settings") => void;
  onLogout: () => void;
}

export function Navbar({ activeTab, setActiveTab, onLogout }: NavbarProps) {
  const { t } = useTranslation();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const navItems = [
    { id: "dashboard" as const, label: t("common.dashboard"), icon: <LayoutDashboard className="w-5 h-5" /> },
    { id: "threats" as const, label: t("common.threat_log"), icon: <FileText className="w-5 h-5" /> },
    { id: "smail" as const, label: t("common.smail_simulator"), icon: <Mail className="w-5 h-5" /> },
    { id: "datasets" as const, label: t("common.datasets"), icon: <Database className="w-5 h-5" /> },
    { id: "settings" as const, label: t("common.settings"), icon: <Settings className="w-5 h-5" /> }
  ];

  return (
    <aside
      className={`bg-[#0B0F19] border-r border-slate-800 flex flex-col justify-between shrink-0 transition-all duration-300 relative ${
        isCollapsed ? "w-20" : "w-64"
      }`}
    >
      {/* Collapse Toggle Button */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute top-6 -right-3 w-6 h-6 bg-slate-900 border border-slate-700 text-slate-400 hover:text-white rounded-full flex items-center justify-center cursor-pointer transition-colors z-20"
      >
        {isCollapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
      </button>

      <div className="p-4 flex-1">
        {/* Brand / Logo */}
        <div className={`flex items-center gap-3 mb-8 px-2 ${isCollapsed ? "justify-center" : ""}`}>
          <div className="w-8 h-8 bg-primary/20 rounded-lg flex items-center justify-center border border-primary/30 shrink-0">
            <ShieldAlert className="w-5 h-5 text-primary" />
          </div>
          {!isCollapsed && (
            <span className="text-lg font-display font-bold text-white tracking-tight">Sicurre</span>
          )}
        </div>

        {/* Navigation Links */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                title={isCollapsed ? item.label : undefined}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 cursor-pointer relative ${
                  isActive
                    ? "text-white bg-primary/20 border border-primary/20"
                    : "text-slate-400 hover:text-white hover:bg-slate-800/40 border border-transparent"
                } ${isCollapsed ? "justify-center" : ""}`}
              >
                {isActive && !isCollapsed && (
                  <MotionDiv
                    layoutId="sidebar-active-line"
                    className="absolute left-0 w-1 h-5 bg-primary rounded-r"
                  />
                )}
                <span className="stroke-[1.5] shrink-0">{item.icon}</span>
                {!isCollapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer / User Stats */}
      <div className="p-4 border-t border-slate-800 space-y-4">
        <div className={`flex items-center gap-3 ${isCollapsed ? "justify-center" : ""}`}>
          <div className="w-8 h-8 bg-slate-800 rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0">
            A
          </div>
          {!isCollapsed && (
            <div className="truncate">
              <p className="text-[10px] text-slate-500">{t("sidebar.connected_as")}</p>
              <p className="text-xs font-semibold text-white truncate max-w-[130px]">
                {localStorage.getItem("sicurre_user_name") || "Admin"}
              </p>
            </div>
          )}
        </div>

        <button
          onClick={onLogout}
          title={isCollapsed ? t("common.logout") : undefined}
          className={`w-full flex items-center gap-2 px-3 py-2 bg-slate-900 hover:bg-red-950/30 border border-slate-800 text-slate-300 hover:text-red-400 rounded-lg text-xs font-medium transition-all cursor-pointer ${
            isCollapsed ? "justify-center" : ""
          }`}
        >
          <LogOut className="w-4 h-4 shrink-0" />
          {!isCollapsed && <span>{t("common.logout")}</span>}
        </button>
      </div>
    </aside>
  );
}
