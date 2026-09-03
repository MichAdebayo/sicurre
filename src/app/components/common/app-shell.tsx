import React, { useState } from "react";
import { Menu } from "lucide-react";
import { Sidebar, type SidebarPage } from "./sidebar";
import { TopBar } from "./top-bar";
import { AlertBanner } from "./alert-banner";
import { useTranslation } from "react-i18next";

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
  administration?: boolean;
  onboardingRequired?: boolean;
  workspaceName?: string;
  workspaceId?: string;
  threatCount?: number;
  hasIntegration?: boolean;
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
  administration = false,
  onboardingRequired = false,
  workspaceName,
  workspaceId,
  threatCount,
  hasIntegration = false,
}: AppShellProps) {
  const { t } = useTranslation();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const changePage = (page: SidebarPage) => {
    onPageChange(page);
    setMobileNavigationOpen(false);
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-on-surface">
      <Sidebar
        currentPage={currentPage}
        onPageChange={changePage}
        onLogout={onLogout}
        onLockdown={onLockdown}
        userRole={userRole}
        administration={administration}
        onboardingRequired={onboardingRequired}
        workspaceName={workspaceName}
        workspaceId={workspaceId}
        userName={userName}
        threatCount={threatCount}
        hasIntegration={hasIntegration}
        collapsible
        className="hidden md:flex"
      />

      {mobileNavigationOpen && (
        <div className="fixed inset-0 z-[60] md:hidden">
          <div
            className="absolute inset-0 bg-black/55"
            aria-hidden="true"
            onClick={() => setMobileNavigationOpen(false)}
          />
          <Sidebar
            currentPage={currentPage}
            onPageChange={changePage}
            onLogout={onLogout}
            onLockdown={onLockdown}
            userRole={userRole}
            administration={administration}
            onboardingRequired={onboardingRequired}
            workspaceName={workspaceName}
            workspaceId={workspaceId}
            userName={userName}
            threatCount={threatCount}
            hasIntegration={hasIntegration}
            onClose={() => setMobileNavigationOpen(false)}
            className="relative z-10 flex shadow-2xl"
          />
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Alert Banner */}
        {alertMessage && (
          <AlertBanner message={alertMessage} type={alertType} />
        )}

        {/* Balanced Content Wrapper */}
        <div className="w-full flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Top Bar */}
          <div className="flex items-center gap-2 px-4 md:px-8">
            <button
              type="button"
              onClick={() => setMobileNavigationOpen(true)}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-low hover:text-on-surface md:hidden"
              aria-label={t("common.open_navigation")}
              aria-expanded={mobileNavigationOpen}
            >
              <Menu className="h-5 w-5" />
            </button>
            <TopBar
              userName={userName}
              userRole={userRole}
              administration={administration}
              onboardingRequired={onboardingRequired}
              onPageChange={changePage}
            />
          </div>

          {/* Page Content */}
          <main key={administration ? currentPage : "workspace"} className="app-readable flex-1 overflow-x-hidden overflow-y-auto px-4 pb-6 pt-5 md:pl-8 md:pr-12 md:pt-8">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
