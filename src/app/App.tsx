import { lazy, Suspense, useEffect, useRef, useState } from "react";
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
  isAdminPage,
  resolveAuthorizedPage,
  sidebarPagePaths,
} from "./lib/navigation";
import { useTranslation } from "react-i18next";
import { parseVerificationCallback } from "./lib/email-verification";
import { applyTheme, getStoredTheme } from "./lib/theme";
import { ActiveDomainProvider } from "./contexts/active-domain";
import { buildDocumentTitle, type DocumentTitleView } from "./lib/document-title";
import { PageLoading } from "./components/common/page-loading";
import { DomainPageBoundary } from "./components/common/domain-page-boundary";

const pageLoaders = {
  dashboard: () => import("./routes/dashboard"),
  threats: () => import("./routes/threats"),
  logs: () => import("./routes/logs"),
  "admin-operations": () => import("./routes/admin-operations"),
  "admin-incidents": () => import("./routes/admin-incidents"),
  "admin-integrations": () => import("./routes/admin-integrations"),
  "admin-reviews": () => import("./routes/admin-reviews"),
  settings: () => import("./routes/settings"),
  support: () => import("./routes/support"),
  quarantine: () => import("./routes/quarantine"),
  alerts: () => import("./routes/alerts"),
  "domain-shield": () => import("./routes/domain-shield"),
};

const LandingRoute = lazy(() => import("./routes/landing"));
const LoginRoute = lazy(() => import("./routes/login"));
const VerifyEmailRoute = lazy(() => import("./routes/verify-email"));
const DashboardRoute = lazy(pageLoaders.dashboard);
const ThreatsRoute = lazy(pageLoaders.threats);
const LogsRoute = lazy(pageLoaders.logs);
const AdminOperationsRoute = lazy(pageLoaders["admin-operations"]);
const AdminIncidentsRoute = lazy(pageLoaders["admin-incidents"]);
const AdminIntegrationsRoute = lazy(pageLoaders["admin-integrations"]);
const AdminReviewsRoute = lazy(pageLoaders["admin-reviews"]);
const SettingsRoute = lazy(pageLoaders.settings);
const SupportRoute = lazy(pageLoaders.support);
const QuarantineRoute = lazy(pageLoaders.quarantine);
const AlertsRoute = lazy(pageLoaders.alerts);
const DomainShieldRoute = lazy(pageLoaders["domain-shield"]);
const MentionsLegalesRoute = lazy(() => import("./routes/mentions-legales"));
const ConfidentialiteRoute = lazy(() => import("./routes/confidentialite"));
const ContactRoute = lazy(() => import("./routes/contact"));
const CGURoute = lazy(() => import("./routes/cgu"));

type ViewState = "landing" | "login" | "signup" | "verify-email" | "cgu" | "mentions-legales" | "confidentialite" | "contact";

const publicViewPaths: Record<ViewState, string> = {
  landing: "/",
  login: "/login",
  signup: "/signup",
  "verify-email": "/verify-email",
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

const consumeVerificationCallback = () => {
  const callback = parseVerificationCallback(window.location.search);
  if (callback.status === "none") return callback;
  const params = new URLSearchParams(window.location.search);
  params.delete("verified");
  params.delete("error");
  const query = params.toString();
  window.history.replaceState(
    {},
    document.title,
    `${window.location.pathname}${query ? `?${query}` : ""}`,
  );
  return callback;
};

const verificationCallback = consumeVerificationCallback();

const getInitialViewState = (): ViewState => {
  if (verificationCallback.status !== "none") {
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
    <div role="status" className="min-h-screen w-full flex items-center justify-center bg-surface-low text-on-surface">
      <div className="text-sm font-semibold">{t("common.loading")}</div>
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
  const { t, i18n } = useTranslation();
  const [hasStoredSession, setHasStoredSession] = useState(getInitialLoginState);
  const [sessionLookupEnabled, setSessionLookupEnabled] = useState(verificationCallback.status === "none");
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
  const requestedAfterLogin = useRef(getSidebarPageFromPath(window.location.pathname));
  const isVerificationEntry = viewState === "verify-email";
  const sessionQuery = useCurrentSession(sessionLookupEnabled && !isVerificationEntry);
  const logoutMutation = useLogout();
  const session = isVerificationEntry || !sessionLookupEnabled ? undefined : sessionQuery.data;
  const administration = isAdminPage(activePage) && Boolean(session?.is_platform_admin);

  useEffect(() => {
    if (!sessionQuery.isLoading || !getSidebarPageFromPath(window.location.pathname)) return;
    // Fetch code alongside session validation, without rendering protected content.
    void pageLoaders[activePage]().catch(() => {
      // A failed speculative fetch must not interrupt authentication.
    });
  }, [activePage, sessionQuery.isLoading]);

  const titleView: DocumentTitleView = session && hasStoredSession
    ? activePage
    : viewState;

  useEffect(() => {
    document.title = buildDocumentTitle(titleView, t);
  }, [titleView, i18n.language, t]);

  const setAuthenticatedPage = (page: SidebarPage, replace = false) => {
    const nextPath = sidebarPagePaths[page];
    if (window.location.pathname !== nextPath) {
      const method = replace ? "replaceState" : "pushState";
      window.history[method]({ sicurrePage: page }, "", nextPath);
    }
    setActivePage(page);
  };

  useEffect(() => {
    // Single source of truth: the same helper the rail toggle and the
    // Préférences select write through.
    applyTheme(getStoredTheme());
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
      const requested = getSidebarPageFromPath(window.location.pathname) ?? requestedAfterLogin.current;
      setAuthenticatedPage(resolveAuthorizedPage(requested, {
        isPlatformAdmin: session.is_platform_admin,
        onboardingRequired: session.onboarding_required,
      }), true);
      requestedAfterLogin.current = null;
    }
  }, [session]);

  useEffect(() => {
    if (!session) return;
    const authorized = resolveAuthorizedPage(activePage, {
      isPlatformAdmin: session.is_platform_admin,
      onboardingRequired: session.onboarding_required,
    });
    if (authorized !== activePage) setAuthenticatedPage(authorized, true);
  }, [session?.onboarding_required, session?.is_platform_admin, activePage]);

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
        setAuthenticatedPage(resolveAuthorizedPage(page, {
          isPlatformAdmin: session.is_platform_admin,
          onboardingRequired: session.onboarding_required,
        }), true);
      }
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [session]);

  const handleLoginSuccess = () => {
    const requested = requestedAfterLogin.current ?? "dashboard";
    window.history.replaceState({}, document.title, sidebarPagePaths[requested]);
    sessionStorage.removeItem("sicurre_view_state");
    setSessionLookupEnabled(true);
    setHasStoredSession(true);
    setActivePage(requested);
  };

  const handleLogout = async () => {
    requestedAfterLogin.current = null;
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

  if (isVerificationEntry) {
    return <VerifyEmailRoute onNavigateToLogin={() => setViewState("login")} />;
  }

  // Background checks must not unmount a public form or its verification notice.
  if ((sessionQuery.isLoading && !sessionQuery.isFetched) || (sessionLookupEnabled && session && !hasStoredSession)) {
    return <RouteFallback />;
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
        emailJustVerified={verificationCallback.status === "verified"}
        emailVerificationError={
          verificationCallback.status === "error" ? verificationCallback.reason : undefined
        }
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
    <ActiveDomainProvider key={session.workspace_id} workspaceId={session.workspace_id}>
    <AppShell
      currentPage={activePage}
      onPageChange={(page) => {
        if (page !== "settings") setSettingsTab(undefined);
        setAuthenticatedPage(resolveAuthorizedPage(page, {
          isPlatformAdmin: session.is_platform_admin,
          onboardingRequired: session.onboarding_required,
        }));
      }}
      onLogout={handleLogout}
      userName={session.display_name}
      userEmail={session.email}
      userRole={session.role}
      administration={administration}
      onboardingRequired={session.onboarding_required}
      workspaceName={session.workspace_name}
      workspaceId={session.workspace_id}
      threatCount={session.threat_count}
      hasIntegration={session.has_cloudflare_integration}
    >
      <Suspense fallback={<PageLoading />}>
        {!isAdminPage(activePage) && !["settings", "support"].includes(activePage) ? (
          <DomainPageBoundary>
            {activePage === "dashboard" && <DashboardRoute session={session} onGoToSettings={handleGoToSettings} />}
            {activePage === "threats" && <ThreatsRoute />}
            {activePage === "quarantine" && <QuarantineRoute />}
            {activePage === "alerts" && <AlertsRoute />}
            {activePage === "domain-shield" && <DomainShieldRoute session={session} />}
          </DomainPageBoundary>
        ) : (
          <>
            {activePage === "logs" && session.is_platform_admin && <LogsRoute />}
            {activePage === "admin-operations" && session.is_platform_admin && <AdminOperationsRoute />}
            {activePage === "admin-incidents" && session.is_platform_admin && <AdminIncidentsRoute />}
            {activePage === "admin-integrations" && session.is_platform_admin && <AdminIntegrationsRoute />}
            {activePage === "admin-reviews" && session.is_platform_admin && <AdminReviewsRoute />}
            {activePage === "settings" && <SettingsRoute session={session} initialTab={settingsTab} />}
            {activePage === "support" && <SupportRoute session={session} />}
          </>
        )}
      </Suspense>
    </AppShell>
    </ActiveDomainProvider>
  );
}
