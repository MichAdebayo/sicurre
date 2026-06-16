import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import LandingRoute from "./routes/landing";
import LoginRoute from "./routes/login";
import DashboardRoute from "./routes/dashboard";
import JournalRoute from "./routes/journal";
import SmailRoute from "./routes/smail";
import DatasetsRoute from "./routes/datasets";
import SettingsRoute from "./routes/settings";
import { Layout } from "./components/common/layout";

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
  const [viewState, setViewState] = useState<"landing" | "login" | "signup">("landing");
  const [activeTab, setActiveTab] = useState<"dashboard" | "threats" | "smail" | "datasets" | "settings">("dashboard");

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
        />
      );
    }
    return (
      <div className="relative">
        {/* Back to landing link on login screen */}
        <button
          onClick={() => setViewState("landing")}
          className="absolute top-6 left-6 text-xs text-slate-400 hover:text-white transition-colors cursor-pointer z-20 font-medium bg-slate-900/40 px-3.5 py-2 rounded-lg border border-slate-800"
        >
          &larr; Retour à l'accueil
        </button>
        <LoginRoute onLoginSuccess={handleLoginSuccess} />
      </div>
    );
  }

  return (
    <Layout
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      onLogout={handleLogout}
    >
      <AnimatePresence mode="wait">
        {activeTab === "dashboard" && <DashboardRoute key="dashboard" />}
        {activeTab === "threats" && <JournalRoute key="threats" />}
        {activeTab === "smail" && <SmailRoute key="smail" />}
        {activeTab === "datasets" && <DatasetsRoute key="datasets" />}
        {activeTab === "settings" && <SettingsRoute key="settings" />}
      </AnimatePresence>
    </Layout>
  );
}
