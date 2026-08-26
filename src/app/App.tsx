import { lazy, Suspense, useEffect, useState } from "react";
import { AppShell } from "./components/common/app-shell";
import { SidebarPage } from "./components/common/sidebar";
import {
  clearStoredSession,
  seedStoredSession,
  useCurrentSession,
  useLogout,
} from "./lib/api";
import {
  getSidebarPageFromPath,
  resolveAuthorizedPage,
  sidebarPagePaths,
} from "./lib/navigation";
import { useTranslation } from "react-i18next";

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

// Verification returns here with ?verified=1. When the session cookie set on
// the verify-email response is lost in transit (an edge challenge on
// /api/auth/* will do it), the user arrives authenticated-in-name-only, so
// send them to the sign-in form with a confirmation rather than the marketing
// page, where the only visible control is a Turnstile checkbox that submits
// nothing.
const consumeEmailVerifiedFlag = (): boolean => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("verified") !== "1") return false;
  params.delete("verified");
  const query = params.toString();
  window.history.replaceState(
    {},
    document.title,
    `${window.location.pathname}${query ? `?${query}` : ""}`,
  );
  return true;
};

const emailJustVerified = consumeEmailVerifiedFlag();

const getInitialViewState = (): ViewState => {
  if (emailJustVerified) {
    sessionStorage.setItem("sicurre_view_state", "login");
    return "login";
  }
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
  const { t } = useTranslation();
  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-surface-low text-on-surface">
      <div className="text-sm font-semibold">{t("common.loading")}</div>
    </div>
  );
}

function PageRouteFallback() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-48 items-center justify-center text-sm font-semibold text-on-surface-variant">
      {t("common.loading")}
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
  const [activePage, setActivePage] = useState<SidebarPage>(
    () => getSidebarPageFromPath(window.location.pathname) ?? "dashboard",
  );
  const [settingsTab, setSettingsTab] = useState<string | undefined>();
  const sessionQuery = useCurrentSession(sessionLookupEnabled);
  const logoutMutation = useLogout();
  const session = sessionQuery.data;

  const setAuthenticatedPage = (page: SidebarPage, replace = false) => {
    const nextPath = sidebarPagePaths[page];
    if (window.location.pathname !== nextPath) {
      const method = replace ? "replaceState" : "pushState";
      window.history[method]({ sicurrePage: page }, "", nextPath);
    }
    setActivePage(page);
  };

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
      const requested = getSidebarPageFromPath(window.location.pathname);
      setAuthenticatedPage(resolveAuthorizedPage(requested, {
        isPlatformAdmin: session.is_platform_admin,
        onboardingRequired: session.onboarding_required,
      }), true);
    }
  }, [session]);

  useEffect(() => {
    if (session?.onboarding_required && activePage !== "settings") {
      setAuthenticatedPage("settings", true);
    }
  }, [session?.onboarding_required, activePage]);

  useEffect(() => {
    const handlePopState = () => {
      const pathView = getViewStateFromPath();
      if (pathView) {
        sessionStorage.setItem("sicurre_view_state", pathView);
        setViewStateState(pathView);
        return;
      }
      const page = getSidebarPageFromPath(window.location.pathname);
      if (page && session) {
        setActivePage(resolveAuthorizedPage(page, {
          isPlatformAdmin: session.is_platform_admin,
          onboardingRequired: session.onboarding_required,
        }));
      }
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [session]);

  useEffect(() => {
    if (session && !session.is_platform_admin && activePage === "logs") {
      setAuthenticatedPage("dashboard", true);
    }
  }, [session, activePage]);

  const handleLoginSuccess = () => {
    window.history.replaceState({}, document.title, sidebarPagePaths.dashboard);
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
        emailJustVerified={emailJustVerified}
      />
    );
  }

  const handleGoToSettings = (tab?: string) => {
    if (tab) {
      setSettingsTab(tab);
    }
    setAuthenticatedPage("settings");
  };

  return (
    <AppShell
      currentPage={activePage}
      onPageChange={(page) => {
        if (page !== "settings") setSettingsTab(undefined);
        if (session.is_platform_admin && page !== "logs" && page !== "settings" && page !== "support") {
          return;
        }
        setAuthenticatedPage(page);
      }}
      onLogout={handleLogout}
      userName={session.display_name}
      userEmail={session.email}
      userRole={session.is_platform_admin ? "admin" : session.role}
      onboardingRequired={session.onboarding_required}
    >
      <Suspense fallback={<PageRouteFallback />}>
          {activePage === "dashboard" && !session.is_platform_admin && <DashboardRoute session={session} onGoToSettings={handleGoToSettings} />}
          {activePage === "threats" && !session.is_platform_admin && (
            <ThreatsRoute />
          )}
          {activePage === "quarantine" && !session.is_platform_admin && <QuarantineRoute />}
          {activePage === "alerts" && !session.is_platform_admin && <AlertsRoute />}
          {activePage === "domain-shield" && !session.is_platform_admin && <DomainShieldRoute session={session} />}
          {activePage === "logs" && session.is_platform_admin && <LogsRoute />}
          {activePage === "settings" && <SettingsRoute session={session} initialTab={settingsTab} />}
          {activePage === "support" && <SupportRoute session={session} />}
      </Suspense>
    </AppShell>
  );
}
