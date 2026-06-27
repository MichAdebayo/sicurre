import React from "react";
import { Sidebar, type SidebarPage } from "./sidebar";
import { TopBar } from "./top-bar";
import { AlertBanner } from "./alert-banner";

interface AppShellProps {
  children: React.ReactNode;
  currentPage: SidebarPage;
  onPageChange: (page: SidebarPage) => void;
  onLogout: () => void;
  onLockdown?: () => void;
  alertMessage?: string;
  alertType?: "warning" | "critical";
  userName?: string;
  userEmail?: string;
  userRole?: string;
}

export function AppShell({
  children,
  currentPage,
  onPageChange,
  onLogout,
  onLockdown,
  alertMessage,
  alertType = "warning",
  userName,
  userEmail,
  userRole,
}: AppShellProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#f6f7f9]">
      {/* Sidebar */}
      <Sidebar
        currentPage={currentPage}
        onPageChange={onPageChange}
        onLogout={onLogout}
        onLockdown={onLockdown}
        userName={userName}
        userEmail={userEmail}
        userRole={userRole}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Alert Banner */}
        {alertMessage && (
          <AlertBanner message={alertMessage} type={alertType} />
        )}

        {/* Top Bar */}
        <TopBar userName={userName} userRole={userRole} onPageChange={onPageChange} />

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto px-8 py-6 max-w-[1200px] w-full">
          {children}
        </main>
      </div>
    </div>
  );
}
