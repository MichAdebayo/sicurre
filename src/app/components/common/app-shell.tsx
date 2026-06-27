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

        {/* Balanced Content Wrapper */}
        <div className="w-full flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Top Bar */}
          <div className="px-8">
            <TopBar userName={userName} userRole={userRole} onPageChange={onPageChange} />
          </div>

          {/* Page Content */}
          <main className="flex-1 overflow-y-auto pt-8 pb-6 pl-8 pr-12">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
