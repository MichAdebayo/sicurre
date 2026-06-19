import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import LandingRoute from "./routes/landing";
import LoginRoute from "./routes/login";
import DashboardRoute from "./routes/dashboard";
import ThreatsRoute from "./routes/threats";
import LogsRoute from "./routes/logs";
import SettingsRoute from "./routes/settings";
import SupportRoute from "./routes/support";
import MentionsLegalesRoute from "./routes/mentions-legales";
import ConfidentialiteRoute from "./routes/confidentialite";
import ContactRoute from "./routes/contact";
import { AppShell } from "./components/common/app-shell";
import { SidebarPage } from "./components/common/sidebar";

const getInitialLoginState = () => {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("session_token");
  if (token) {
    localStorage.setItem("sicurre_session_token", token);
    localStorage.setItem("sicurre_user_name", params.get("username") || "Utilisateur Google");
    // Clean query parameters from address bar
    window.history.replaceState({}, document.title, window.location.pathname);
    return true;
  }
  return !!localStorage.getItem("sicurre_session_token");
};

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(getInitialLoginState);
  const [viewState, setViewState] = useState<"landing" | "login" | "signup" | "mentions-legales" | "confidentialite" | "contact">("landing");
  const [activePage, setActivePage] = useState<SidebarPage>("dashboard");

  // Handle successful login
  const handleLoginSuccess = () => {
    setIsLoggedIn(true);
  };

  // Handle logout
  const handleLogout = () => {
    localStorage.removeItem("sicurre_session_token");
    localStorage.removeItem("sicurre_user_name");
    setIsLoggedIn(false);
    setViewState("landing");
  };

  if (!isLoggedIn) {
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
        <LoginRoute onLoginSuccess={handleLoginSuccess} />
      </div>
    );
  }

  return (
    <AppShell
      currentPage={activePage}
      onPageChange={setActivePage}
      onLogout={handleLogout}
      userName={localStorage.getItem("sicurre_user_name") || "Administrateur"}
    >
      <AnimatePresence mode="wait">
        {activePage === "dashboard" && <DashboardRoute key="dashboard" />}
        {activePage === "threats" && <ThreatsRoute key="threats" />}
        {activePage === "logs" && <LogsRoute key="logs" />}
        {activePage === "settings" && <SettingsRoute key="settings" />}
        {activePage === "support" && <SupportRoute key="support" />}
      </AnimatePresence>
    </AppShell>
  );
}
