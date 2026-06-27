import { useEffect, useState } from "react";
import { AnimatePresence } from "framer-motion";
import LandingRoute from "./routes/landing";
import LoginRoute from "./routes/login";
import DashboardRoute from "./routes/dashboard";
import ThreatsRoute from "./routes/threats";
import LogsRoute from "./routes/logs";
import SettingsRoute from "./routes/settings";
import SupportRoute from "./routes/support";
import QuarantineRoute from "./routes/quarantine";
import AlertsRoute from "./routes/alerts";
import DomainShieldRoute from "./routes/domain-shield";
import MentionsLegalesRoute from "./routes/mentions-legales";
import ConfidentialiteRoute from "./routes/confidentialite";
import ContactRoute from "./routes/contact";
import { AppShell } from "./components/common/app-shell";
import { SidebarPage } from "./components/common/sidebar";
import {
  clearStoredSession,
  seedStoredSession,
  useCurrentSession,
  useLogout,
} from "./lib/api";

const getInitialLoginState = () => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("auth_provider") || params.get("email") || params.get("username")) {
    seedStoredSession({
      displayName: params.get("username") || "Utilisateur Google",
      email: params.get("email") || undefined,
      role: params.get("role") || undefined,
      authProvider: (params.get("auth_provider") as "password" | "google" | null) || "password",
    });
    window.history.replaceState({}, document.title, window.location.pathname);
    return false;
  }
  return false;
};

export default function App() {
  const [hasStoredSession, setHasStoredSession] = useState(getInitialLoginState);
  const [viewState, setViewState] = useState<"landing" | "login" | "signup" | "mentions-legales" | "confidentialite" | "contact">("landing");
  const [activePage, setActivePage] = useState<SidebarPage>("dashboard");
  const sessionQuery = useCurrentSession(true);
  const logoutMutation = useLogout();
  const session = sessionQuery.data;

  useEffect(() => {
    if (sessionQuery.isError) {
      clearStoredSession();
      setHasStoredSession(false);
      setViewState("login");
      setActivePage("dashboard");
    }
  }, [sessionQuery.isError]);

  useEffect(() => {
    if (session) {
      setHasStoredSession(true);
    }
  }, [session]);

  useEffect(() => {
    if (session?.onboarding_required && activePage !== "settings") {
      setActivePage("settings");
    }
  }, [session?.onboarding_required, activePage]);

  useEffect(() => {
    if (session && !session.is_platform_admin && activePage === "logs") {
      setActivePage("dashboard");
    }
  }, [session, activePage]);

  const handleLoginSuccess = () => {
    setHasStoredSession(true);
    setActivePage("dashboard");
  };

  const handleLogout = async () => {
    try {
      await logoutMutation.mutateAsync();
    } catch {
      clearStoredSession();
    }
    setHasStoredSession(false);
    setViewState("landing");
    setActivePage("dashboard");
  };

  if (sessionQuery.isLoading) {
    return (
      <div className="min-h-screen w-screen flex items-center justify-center bg-surface-low text-on-surface">
        <div className="text-sm font-semibold">Chargement de votre session…</div>
      </div>
    );
  }

  if (!hasStoredSession || !session) {
    if (viewState === "landing") {
      return (
        <LandingRoute
          onNavigateToLogin={() => setViewState("login")}
          onNavigateToSignUp={() => setViewState("signup")}
          onNavigateToMentionsLegales={() => setViewState("mentions-legales")}
          onNavigateToConfidentialite={() => setViewState("confidentialite")}
          onNavigateToContact={() => setViewState("contact")}
        />
      );
    }
    if (viewState === "mentions-legales") {
      return <MentionsLegalesRoute onBack={() => setViewState("landing")} />;
    }
    if (viewState === "confidentialite") {
      return <ConfidentialiteRoute onBack={() => setViewState("landing")} />;
    }
    if (viewState === "contact") {
      return <ContactRoute onBack={() => setViewState("landing")} />;
    }
    return (
      <div className="relative bg-surface-low">
        {/* Back to landing link on login screen */}
        <button
          onClick={() => setViewState("landing")}
          className="absolute top-6 left-6 text-xs text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer z-20 font-semibold bg-surface-lowest hover:bg-surface-low px-4 py-2 rounded-lg border border-border-subtle shadow-sm"
        >
          &larr; Retour à l'accueil
        </button>
        <LoginRoute onLoginSuccess={handleLoginSuccess} initialMode={viewState === "signup" ? "signup" : "login"} />
      </div>
    );
  }

  return (
    <AppShell
      currentPage={activePage}
      onPageChange={setActivePage}
      onLogout={handleLogout}
      userName={session.display_name}
      userEmail={session.email}
      userRole={session.is_platform_admin ? "admin" : session.role}
    >
      <AnimatePresence mode="wait">
        {activePage === "dashboard" && <DashboardRoute key="dashboard" session={session} onGoToSettings={() => setActivePage("settings")} />}
        {activePage === "threats" && <ThreatsRoute key="threats" session={session} />}
        {activePage === "quarantine" && <QuarantineRoute key="quarantine" />}
        {activePage === "alerts" && <AlertsRoute key="alerts" />}
        {activePage === "domain-shield" && <DomainShieldRoute key="domain-shield" />}
        {activePage === "logs" && session.is_platform_admin && <LogsRoute key="logs" />}
        {activePage === "settings" && <SettingsRoute key="settings" session={session} />}
        {activePage === "support" && <SupportRoute key="support" />}
      </AnimatePresence>
    </AppShell>
  );
}
