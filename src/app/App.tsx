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
import CGURoute from "./routes/cgu";
import { AppShell } from "./components/common/app-shell";
import { SidebarPage } from "./components/common/sidebar";
import {
  clearStoredSession,
  seedStoredSession,
  useCurrentSession,
  useLogout,
} from "./lib/api";

type ViewState = "landing" | "login" | "signup" | "cgu" | "mentions-legales" | "confidentialite" | "contact";

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

const getInitialViewState = (): ViewState => {
  const saved = sessionStorage.getItem("sicurre_view_state");
  if (saved && ["landing", "login", "signup", "cgu", "mentions-legales", "confidentialite", "contact"].includes(saved)) {
    return saved as ViewState;
  }
  return "landing";
};

export default function App() {
  const [hasStoredSession, setHasStoredSession] = useState(getInitialLoginState);
  const [viewState, setViewStateState] = useState<ViewState>(getInitialViewState);

  const setViewState = (view: ViewState) => {
    sessionStorage.setItem("sicurre_view_state", view);
    setViewStateState(view);
  };
  const [activePage, setActivePage] = useState<SidebarPage>("dashboard");
  const [settingsTab, setSettingsTab] = useState<string | undefined>();
  const sessionQuery = useCurrentSession(true);
  const logoutMutation = useLogout();
  const session = sessionQuery.data;

  useEffect(() => {
    const savedTheme = localStorage.getItem("sicurre_theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", savedTheme === "dark" || (!savedTheme && prefersDark));
  }, []);

  useEffect(() => {
    if (sessionQuery.isError) {
      clearStoredSession();
      if (hasStoredSession) {
        setHasStoredSession(false);
        setViewState("login");
      }
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
    if (viewState === "cgu") {
      return <CGURoute onBack={() => setViewState("landing")} />;
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
      <LoginRoute
        onLoginSuccess={handleLoginSuccess}
        initialMode={viewState === "signup" ? "signup" : "login"}
        onNavigateToLanding={() => setViewState("landing")}
      />
    );
  }

  const handleGoToSettings = (tab?: string) => {
    if (tab) {
      setSettingsTab(tab);
    }
    setActivePage("settings");
  };

  return (
    <AppShell
      currentPage={activePage}
      onPageChange={(page) => {
        if (page !== "settings") setSettingsTab(undefined);
        setActivePage(page);
      }}
      onLogout={handleLogout}
      userName={session.display_name}
      userEmail={session.email}
      userRole={session.is_platform_admin ? "admin" : session.role}
      onboardingRequired={session.onboarding_required}
    >
      <AnimatePresence mode="wait">
        {activePage === "dashboard" && <DashboardRoute key="dashboard" session={session} onGoToSettings={handleGoToSettings} />}
        {activePage === "threats" && <ThreatsRoute key="threats" session={session} />}
        {activePage === "quarantine" && <QuarantineRoute key="quarantine" />}
        {activePage === "alerts" && <AlertsRoute key="alerts" />}
        {activePage === "domain-shield" && <DomainShieldRoute key="domain-shield" session={session} />}
        {activePage === "logs" && session.is_platform_admin && <LogsRoute key="logs" />}
        {activePage === "settings" && <SettingsRoute key="settings" session={session} initialTab={settingsTab} />}
        {activePage === "support" && <SupportRoute key="support" session={session} />}
      </AnimatePresence>
    </AppShell>
  );
}
