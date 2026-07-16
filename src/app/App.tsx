import { lazy, Suspense, useEffect, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { AppShell } from "./components/common/app-shell";
import { SidebarPage } from "./components/common/sidebar";
import {
  clearStoredSession,
  seedStoredSession,
  useCurrentSession,
  useLogout,
} from "./lib/api";

const LandingRoute = lazy(() => import("./routes/landing"));
const LoginRoute = lazy(() => import("./routes/login"));
const DashboardRoute = lazy(() => import("./routes/dashboard"));
const ThreatsRoute = lazy(() => import("./routes/threats"));
const LogsRoute = lazy(() => import("./routes/logs"));
const SettingsRoute = lazy(() => import("./routes/settings"));
const SupportRoute = lazy(() => import("./routes/support"));
const QuarantineRoute = lazy(() => import("./routes/quarantine"));
const AlertsRoute = lazy(() => import("./routes/alerts"));
const DomainShieldRoute = lazy(() => import("./routes/domain-shield"));
const MentionsLegalesRoute = lazy(() => import("./routes/mentions-legales"));
const ConfidentialiteRoute = lazy(() => import("./routes/confidentialite"));
const ContactRoute = lazy(() => import("./routes/contact"));
const CGURoute = lazy(() => import("./routes/cgu"));

type ViewState = "landing" | "login" | "signup" | "cgu" | "mentions-legales" | "confidentialite" | "contact";

const publicViewPaths: Record<ViewState, string> = {
  landing: "/",
  login: "/login",
  signup: "/signup",
  cgu: "/cgu",
  "mentions-legales": "/mentions-legales",
  confidentialite: "/confidentialite",
  contact: "/contact",
};

const publicPathViews = new Map<string, ViewState>(
  Object.entries(publicViewPaths).map(([view, path]) => [path, view as ViewState]),
);

const isPublicViewState = (value: string | null): value is ViewState =>
  Boolean(value && value in publicViewPaths);

const getViewStateFromPath = (): ViewState | null => {
  const normalizedPath = window.location.pathname.replace(/\/$/, "") || "/";
  return publicPathViews.get(normalizedPath) ?? null;
};

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
  const pathView = getViewStateFromPath();
  if (pathView) {
    sessionStorage.setItem("sicurre_view_state", pathView);
    return pathView;
  }
  const saved = sessionStorage.getItem("sicurre_view_state");
  if (isPublicViewState(saved)) {
    return saved;
  }
  return "landing";
};

function RouteFallback() {
  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-surface-low text-on-surface">
      <div className="text-sm font-semibold">Chargement…</div>
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <AppContent />
    </Suspense>
  );
}

function AppContent() {
  const [hasStoredSession, setHasStoredSession] = useState(getInitialLoginState);
  const [sessionLookupEnabled, setSessionLookupEnabled] = useState(true);
  const [viewState, setViewStateState] = useState<ViewState>(getInitialViewState);

  const setViewState = (view: ViewState) => {
    sessionStorage.setItem("sicurre_view_state", view);
    const nextPath = publicViewPaths[view];
    if (window.location.pathname !== nextPath) {
      window.history.pushState({ sicurreViewState: view }, "", nextPath);
    }
    setViewStateState(view);
  };
  const [activePage, setActivePage] = useState<SidebarPage>("dashboard");
  const [settingsTab, setSettingsTab] = useState<string | undefined>();
  const sessionQuery = useCurrentSession(sessionLookupEnabled);
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
      if (session.is_platform_admin) {
        setActivePage("logs");
      }
    }
  }, [session]);

  useEffect(() => {
    if (session?.onboarding_required && activePage !== "settings") {
      setActivePage("settings");
    }
  }, [session?.onboarding_required, activePage]);

  useEffect(() => {
    const handlePopState = () => {
      const pathView = getViewStateFromPath();
      if (pathView) {
        sessionStorage.setItem("sicurre_view_state", pathView);
        setViewStateState(pathView);
      }
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (session && !session.is_platform_admin && activePage === "logs") {
      setActivePage("dashboard");
    }
  }, [session, activePage]);

  const handleLoginSuccess = () => {
    window.history.replaceState({}, document.title, "/");
    sessionStorage.removeItem("sicurre_view_state");
    setSessionLookupEnabled(true);
    setHasStoredSession(true);
    setActivePage("dashboard");
  };

  const handleLogout = async () => {
    setSessionLookupEnabled(false);
    setHasStoredSession(false);
    clearStoredSession();
    setViewState("landing");
    setActivePage("dashboard");
    try {
      await logoutMutation.mutateAsync();
    } catch {
      // The local session remains closed even if remote revocation is unavailable.
    }
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
        if (session.is_platform_admin && page !== "logs" && page !== "settings" && page !== "support") {
          return;
        }
        setActivePage(page);
      }}
      onLogout={handleLogout}
      userName={session.display_name}
      userEmail={session.email}
      userRole={session.is_platform_admin ? "admin" : session.role}
      onboardingRequired={session.onboarding_required}
    >
      <AnimatePresence mode="wait">
        {activePage === "dashboard" && !session.is_platform_admin && <DashboardRoute key="dashboard" session={session} onGoToSettings={handleGoToSettings} />}
        {activePage === "threats" && !session.is_platform_admin && (
          <ThreatsRoute key="threats" onOpenQuarantine={() => setActivePage("quarantine")} />
        )}
        {activePage === "quarantine" && !session.is_platform_admin && <QuarantineRoute key="quarantine" />}
        {activePage === "alerts" && !session.is_platform_admin && <AlertsRoute key="alerts" />}
        {activePage === "domain-shield" && !session.is_platform_admin && <DomainShieldRoute key="domain-shield" session={session} />}
        {activePage === "logs" && session.is_platform_admin && <LogsRoute key="logs" />}
        {activePage === "settings" && <SettingsRoute key="settings" session={session} initialTab={settingsTab} />}
        {activePage === "support" && <SupportRoute key="support" session={session} />}
      </AnimatePresence>
    </AppShell>
  );
}
