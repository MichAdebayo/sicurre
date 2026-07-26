import React, { useState } from "react";
import { Menu, X } from "lucide-react";
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
  onboardingRequired?: boolean;
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
  onboardingRequired = false,
}: AppShellProps) {
  const { t } = useTranslation();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const changePage = (page: SidebarPage) => {
    onPageChange(page);
    setMobileNavigationOpen(false);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-on-surface">
      <Sidebar
        currentPage={currentPage}
        onPageChange={changePage}
        onLogout={onLogout}
        onLockdown={onLockdown}
        userName={userName}
        userEmail={userEmail}
        userRole={userRole}
        onboardingRequired={onboardingRequired}
        className="hidden md:flex"
      />

      {mobileNavigationOpen && (
        <div className="fixed inset-0 z-[60] md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/55"
            aria-label={t("common.close_navigation")}
            onClick={() => setMobileNavigationOpen(false)}
          />
          <Sidebar
            currentPage={currentPage}
            onPageChange={changePage}
            onLogout={onLogout}
            onLockdown={onLockdown}
            userName={userName}
            userEmail={userEmail}
            userRole={userRole}
            onboardingRequired={onboardingRequired}
            className="relative z-10 flex shadow-2xl"
          />
          <button
            type="button"
            onClick={() => setMobileNavigationOpen(false)}
            className="absolute right-4 top-4 z-20 grid h-11 w-11 place-items-center rounded-lg bg-surface-lowest text-on-surface shadow-lg"
            aria-label={t("common.close_navigation")}
          >
            <X className="h-5 w-5" />
          </button>
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
              onboardingRequired={onboardingRequired}
              onPageChange={changePage}
            />
          </div>

          {/* Page Content */}
          <main className="app-readable flex-1 overflow-y-auto px-4 pb-6 pt-5 md:pl-8 md:pr-12 md:pt-8">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
