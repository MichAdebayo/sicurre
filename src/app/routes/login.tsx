import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Mail, Lock, User, ArrowRight } from "lucide-react";
import { motion } from "framer-motion";
import sicurreLogo from "../assets/sicurre.svg";
import { loginSchema, signUpSchema } from "../lib/schemas";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";

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
      const validation = signUpSchema.safeParse({ name, email, password });
      if (!validation.success) {
        setAuthError(validation.error.errors[0].message);
        return;
      }
      localStorage.setItem("sicurre_user_name", name);
      localStorage.setItem(`sicurre_user_email_${email}`, email);
      localStorage.setItem(`sicurre_user_password_${email}`, password);
      localStorage.setItem("sicurre_session_token", "mock-token-registered-12345");
      onLoginSuccess();
    } else {
      const validation = loginSchema.safeParse({ email, password });
      if (!validation.success) {
        setAuthError(validation.error.errors[0].message);
        return;
      }
      if (email === "admin@sicurre.fr" && password === "sicurre2026") {
        localStorage.setItem("sicurre_session_token", "mock-token-12345");
        localStorage.setItem("sicurre_user_name", "Michael");
        onLoginSuccess();
      } else if (email === "demo@sicurre.fr" && password === "demo2026") {
        localStorage.setItem("sicurre_session_token", "mock-token-demo");
        localStorage.setItem("sicurre_user_name", "Michael-viewer");
        onLoginSuccess();
      } else {
        const storedEmail = localStorage.getItem(`sicurre_user_email_${email}`);
        const storedPassword = localStorage.getItem(`sicurre_user_password_${email}`);
        const storedName = localStorage.getItem("sicurre_user_name") || "Utilisateur";
        if (storedEmail === email && storedPassword === password) {
          localStorage.setItem("sicurre_session_token", "mock-token-registered-12345");
          localStorage.setItem("sicurre_user_name", storedName);
          onLoginSuccess();
        } else {
          setAuthError(t("login.error_invalid") || "Identifiants incorrects.");
        }
      }
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = "/auth/login/google";
  };

  return (
    <div className="login-container min-h-screen w-screen flex flex-col items-center justify-center bg-black relative overflow-hidden px-6 select-none">
      {/* CSS overrides to style labels matching the Resend login screenshot */}
      <style>{`
        .login-container label {
          color: #94a3b8 !important;
          text-transform: none !important;
          font-size: 13px !important;
          font-weight: 500 !important;
          letter-spacing: normal !important;
          margin-bottom: 2px !important;
        }
      `}</style>

      {/* ── Background Premium Metallic Waves (Resend Aesthetic) ── */}
      {/* Top Right Wave */}
      <div className="absolute top-0 right-0 w-[55%] h-[65%] select-none pointer-events-none opacity-40 z-0">
        <svg className="w-full h-full" viewBox="0 0 600 600" fill="none" preserveAspectRatio="none">
          <defs>
            <linearGradient id="silk-grad-1" x1="100%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.12" />
              <stop offset="40%" stopColor="#475569" stopOpacity="0.04" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0.9" />
            </linearGradient>
            <linearGradient id="silk-grad-2" x1="100%" y1="0%" x2="30%" y2="80%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0.95" />
            </linearGradient>
          </defs>
          <path d="M250 0 C380 180, 200 380, 600 480 L600 0 Z" fill="url(#silk-grad-1)" />
          <path d="M380 0 C450 140, 320 280, 600 380 L600 0 Z" fill="url(#silk-grad-2)" opacity="0.6" />
        </svg>
      </div>

      {/* Bottom Left Wave */}
      <div className="absolute bottom-0 left-0 w-[50%] h-[60%] select-none pointer-events-none opacity-35 z-0">
        <svg className="w-full h-full" viewBox="0 0 600 600" fill="none" preserveAspectRatio="none">
          <defs>
            <linearGradient id="silk-grad-3" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.1" />
              <stop offset="50%" stopColor="#475569" stopOpacity="0.03" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0.9" />
            </linearGradient>
          </defs>
          <path d="M0 200 C180 320, 250 480, 350 600 L0 600 Z" fill="url(#silk-grad-3)" />
        </svg>
      </div>

      {/* ── Content Layout ── */}
      <MotionDiv
        initial={{ opacity: 0, scale: 0.99, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="w-full max-w-[400px] relative z-10 flex flex-col items-center"
      >
        {/* Logo */}
        <img src={sicurreLogo} alt="Sicurre" className="w-12 h-12 mb-4 select-none pointer-events-none" />

        {/* Brand Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <h1 className="font-display font-bold text-2xl text-white tracking-tight">
            {isSignUp ? "Créer un compte" : "Connexion à Sicurre"}
          </h1>
          <p className="text-[13px] text-slate-400 mt-2.5">
            {isSignUp ? "Vous avez déjà un compte ? " : "Vous n'avez pas de compte ? "}
            <button
              onClick={() => { setIsSignUp(!isSignUp); setAuthError(""); }}
              className="text-white hover:underline font-semibold cursor-pointer ml-1"
            >
              {isSignUp ? "Se connecter" : "S'inscrire"}
            </button>
          </p>
        </div>

        {/* Form Container (No card border/wrapper, sitting directly on background) */}
        <div className="w-full space-y-5">
          {/* Google SSO Dark Button */}
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-2.5 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 text-white rounded-lg text-sm font-semibold transition-all cursor-pointer shadow-sm"
          >
            <svg className="w-4 h-4 text-white" viewBox="0 0 24 24">
              <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.56c2.08-1.92 3.28-4.74 3.28-8.1z" />
              <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.77c-.98.66-2.23 1.06-3.72 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            <span>Se connecter avec Google</span>
          </button>

          {/* Divider */}
          <div className="relative flex items-center justify-center my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-white/10" />
            </div>
            <span className="relative bg-black px-4 text-xs text-slate-500 font-medium">
              ou
            </span>
          </div>

          {/* Core Credentials Form */}
          <form onSubmit={handleAuth} className="space-y-4">
            {isSignUp && (
              <Input
                label="Nom complet"
                type="text"
                id="name"
                placeholder="Jean Dupont"
                value={name}
                onChange={(e) => setName(e.target.value)}
                icon={<User className="w-4 h-4 text-white/40" />}
                className="!bg-slate-950/60 !border-white/10 !text-white !placeholder:text-white/20 focus:!border-white/25 focus:!ring-white/5"
                required
              />
            )}

            <Input
              label="Adresse e-mail"
              type="email"
              id="email"
              placeholder="alan.turing@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              icon={<Mail className="w-4 h-4 text-white/40" />}
              className="!bg-slate-950/60 !border-white/10 !text-white !placeholder:text-white/20 focus:!border-white/25 focus:!ring-white/5"
              required
            />

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label htmlFor="password">
                  Mot de passe
                </label>
                {!isSignUp && (
                  <button type="button" className="text-[12px] text-slate-400 font-medium hover:text-white transition-colors cursor-pointer">
                    Mot de passe oublié ?
                  </button>
                )}
              </div>
              <Input
                type={showPassword ? "text" : "password"}
                id="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                icon={<Lock className="w-4 h-4 text-white/40" />}
                className="!bg-slate-950/60 !border-white/10 !text-white !placeholder:text-white/20 focus:!border-white/25 focus:!ring-white/5"
                suffix={
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="text-white/40 hover:text-white transition-colors cursor-pointer mr-0.5"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                }
                required
              />
            </div>

            {authError && (
              <div className="p-3 bg-red-950/20 border border-red-900/30 text-red-400 text-sm rounded-lg font-medium">
                {authError}
              </div>
            )}

            <Button type="submit" fullWidth className="mt-2 flex items-center justify-center gap-2 !py-2.5 bg-white hover:bg-slate-100 text-black font-semibold rounded-lg transition-colors cursor-pointer shadow-md">
              <span>{isSignUp ? "Créer mon compte" : "Se connecter"}</span>
              <ArrowRight className="w-4 h-4" />
            </Button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-slate-500 mt-10 leading-relaxed">
          En vous connectant, vous acceptez nos{" "}
          <a href="#" className="text-white hover:underline">Conditions d'utilisation</a>{" "}
          et notre{" "}
          <a href="#" className="text-white hover:underline">Politique de confidentialité</a>.
        </p>
      </MotionDiv>
    </div>
  );
}
