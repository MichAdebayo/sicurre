import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldAlert, Eye, EyeOff } from "lucide-react";
import { motion } from "framer-motion";
import { loginSchema, signUpSchema } from "../lib/schemas";

const MotionDiv = motion.div as any;

interface LoginRouteProps {
  onLoginSuccess: () => void;
}

export default function LoginRoute({ onLoginSuccess }: LoginRouteProps) {
  const { t } = useTranslation();
  const [isSignUp, setIsSignUp] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState("");

  const handleAuth = (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");

    if (isSignUp) {
      // Validate Sign Up Zod Schema
      const validation = signUpSchema.safeParse({ name, email, password });
      if (!validation.success) {
        setAuthError(validation.error.errors[0].message);
        return;
      }
      
      // Save details dynamically into localStorage to simulate signup/registration database
      localStorage.setItem(`sicurre_user_name`, name);
      localStorage.setItem(`sicurre_user_email_${email}`, email);
      localStorage.setItem(`sicurre_user_password_${email}`, password);
      
      // Login immediately on successful Sign Up
      localStorage.setItem("sicurre_session_token", "mock-token-registered-12345");
      localStorage.setItem("sicurre_user_name", name);
      onLoginSuccess();
    } else {
      // Validate Login Zod Schema
      const validation = loginSchema.safeParse({ email, password });
      if (!validation.success) {
        setAuthError(validation.error.errors[0].message);
        return;
      }

      // Check default mock admin
      if (email === "admin@sicurre.fr" && password === "sicurre2026") {
        localStorage.setItem("sicurre_session_token", "mock-token-12345");
        localStorage.setItem("sicurre_user_name", "Administrateur Sicurre");
        onLoginSuccess();
      } else {
        // Check dynamically registered user in localStorage
        const storedEmail = localStorage.getItem(`sicurre_user_email_${email}`);
        const storedPassword = localStorage.getItem(`sicurre_user_password_${email}`);
        const storedName = localStorage.getItem(`sicurre_user_name`) || "Utilisateur enregistré";
        
        if (storedEmail === email && storedPassword === password) {
          localStorage.setItem("sicurre_session_token", "mock-token-registered-12345");
          localStorage.setItem("sicurre_user_name", storedName);
          onLoginSuccess();
        } else {
          setAuthError(t("login.error_invalid"));
        }
      }
    }
  };

  const handleGoogleLogin = () => {
    // Redirect to backend Google OAuth login route as specified in canonical openapi.yaml
    window.location.href = "/auth/login/google";
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0B0F19] relative overflow-hidden">
      {/* Subtle geometric neon lines backdrop */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f293710_1px,transparent_1px),linear-gradient(to_bottom,#1f293710_1px,transparent_1px)] bg-[size:4rem_4rem]"></div>
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[120px] pointer-events-none"></div>

      <MotionDiv
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="w-full max-w-md p-8 bg-[#111827]/90 border border-slate-800 rounded-2xl shadow-2xl relative z-10 backdrop-blur-md"
      >
        <div className="flex flex-col items-center mb-6">
          <div className="w-12 h-12 bg-primary/20 rounded-xl flex items-center justify-center border border-primary/30 mb-3">
            <ShieldAlert className="w-6 h-6 text-primary" />
          </div>
          <h1 className="text-3xl font-display font-bold text-white tracking-tight">Sicurre</h1>
          <p className="text-sm text-slate-400 mt-1">
            {isSignUp ? "Créer un compte professionnel" : t("login.subtitle")}
          </p>
        </div>

        <form onSubmit={handleAuth} className="space-y-4">
          {isSignUp && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                Nom complet
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex. Jean Dupont"
                className="w-full px-4 py-3 bg-slate-900 border border-slate-700 text-white rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary text-sm transition-all"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              {t("login.email_label")}
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nom@entreprise.fr"
              className="w-full px-4 py-3 bg-slate-900 border border-slate-700 text-white rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary text-sm transition-all"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              {t("login.password_label")}
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-4 py-3 bg-slate-900 border border-slate-700 text-white rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary text-sm transition-all pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-3.5 text-slate-400 hover:text-white transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {authError && (
            <div className="p-3 bg-red-950/40 border border-red-800 text-red-400 text-xs rounded-lg">
              {authError}
            </div>
          )}

          <button
            type="submit"
            className="w-full py-3 bg-accent hover:bg-accent-dark text-slate-950 font-semibold rounded-lg shadow-lg hover:shadow-accent/20 active:scale-[0.98] transition-all text-sm mt-2 cursor-pointer"
          >
            {isSignUp ? "S'inscrire" : t("login.button")}
          </button>
        </form>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-800"></div>
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-[#111827] px-2 text-slate-400">Ou continuer avec</span>
          </div>
        </div>

        {/* Google Authentication Button */}
        <button
          onClick={handleGoogleLogin}
          className="w-full flex items-center justify-center gap-2.5 py-3 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 hover:text-white font-semibold rounded-lg text-sm active:scale-[0.98] transition-all cursor-pointer"
        >
          <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
            <path d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.113-5.136 4.113-3.055 0-5.5-2.474-5.5-5.5s2.445-5.5 5.5-5.5c1.35 0 2.61.491 3.593 1.341l3.073-3.073C18.665 3.861 15.639 3 12.24 3 6.58 3 2 7.58 2 13.24s4.58 10.24 10.24 10.24c5.795 0 10.24-4.11 10.24-10.24 0-.568-.061-1.122-.172-1.664l-10.068-.291z"/>
          </svg>
          <span>Google Workspace</span>
        </button>

        <div className="text-center mt-6">
          <button
            onClick={() => {
              setIsSignUp(!isSignUp);
              setAuthError("");
            }}
            className="text-xs text-primary hover:text-primary-dark font-medium transition-colors cursor-pointer"
          >
            {isSignUp ? "Déjà un compte ? Se connecter" : "Pas encore de compte ? S'inscrire"}
          </button>
        </div>
      </MotionDiv>
    </div>
  );
}
