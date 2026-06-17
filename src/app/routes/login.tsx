import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Mail, Lock, User, Info, ArrowRight } from "lucide-react";
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
          setAuthError(t("login.error_invalid") || "Identifiants invalides.");
        }
      }
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = "/auth/login/google";
  };

  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-[#f8f9fc] relative overflow-hidden px-6">
      {/* Subtle ambient background */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,56,164,0.015)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,56,164,0.015)_1px,transparent_1px)] bg-[size:3rem_3rem]" />
      <div className="absolute top-[-25%] right-[-15%] w-[600px] h-[600px] bg-primary/[0.03] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-25%] left-[-15%] w-[500px] h-[500px] bg-primary/[0.02] rounded-full blur-[100px] pointer-events-none" />

      <MotionDiv
        initial={{ opacity: 0, scale: 0.98, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-[420px] relative z-10"
      >
        {/* Main Card */}
        <div className="bg-white rounded-2xl border border-border-subtle shadow-xl shadow-on-surface/[0.04] p-8">
          {/* Brand Identity Header */}
          <div className="flex flex-col items-center text-center mb-8">
            <div className="p-3 bg-primary/[0.06] border border-primary/15 rounded-xl mb-4">
              <img src={sicurreLogo} alt="Sicurre" className="w-12 h-12" />
            </div>
            <h1 className="font-display font-bold text-3xl text-on-surface tracking-tight">
              Sicurre
            </h1>
            <p className="text-sm text-on-surface-variant mt-1.5">
              {isSignUp ? "Créez votre compte de protection e-mail" : "Protection sécurisée pour l'entreprise moderne"}
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleAuth} className="space-y-4">
            {isSignUp && (
              <Input
                label="Nom complet"
                type="text"
                id="name"
                placeholder="Ex. Jean Dupont"
                value={name}
                onChange={(e) => setName(e.target.value)}
                icon={<User className="w-4.5 h-4.5" />}
                required
              />
            )}

            <Input
              label="Adresse e-mail"
              type="email"
              id="email"
              placeholder="nom@entreprise.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              icon={<Mail className="w-4.5 h-4.5" />}
              required
            />

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label htmlFor="password" className="text-label-caps text-on-surface-variant font-semibold">
                  Mot de passe
                </label>
                {!isSignUp && (
                  <button type="button" className="text-[12px] text-primary font-semibold hover:text-navy-dark transition-colors cursor-pointer">
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
                icon={<Lock className="w-4.5 h-4.5" />}
                suffix={
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="text-on-surface-variant/60 hover:text-on-surface transition-colors cursor-pointer"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                }
                required
              />
            </div>

            {authError && (
              <div className="p-3 bg-error/[0.06] border border-error/15 text-error text-sm rounded-lg font-medium">
                {authError}
              </div>
            )}

            <Button type="submit" fullWidth className="mt-2 flex items-center justify-center gap-2 !py-3">
              <span>{isSignUp ? "Créer mon compte" : "Se connecter"}</span>
              <ArrowRight className="w-4 h-4" />
            </Button>
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border-subtle" />
            </div>
            <div className="relative flex justify-center text-[11px] uppercase">
              <span className="bg-white px-3.5 text-on-surface-variant/50 font-semibold tracking-wider">
                Ou
              </span>
            </div>
          </div>

          {/* Google SSO */}
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 py-2.5 bg-white hover:bg-surface-low border border-border-subtle text-on-surface rounded-lg text-sm font-semibold transition-all duration-150 cursor-pointer"
          >
            <svg className="w-4.5 h-4.5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.56c2.08-1.92 3.28-4.74 3.28-8.1z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.77c-.98.66-2.23 1.06-3.72 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            <span>Se connecter avec Google Workspace</span>
          </button>

          {/* Mode Switch */}
          <div className="text-center mt-6">
            <button
              onClick={() => { setIsSignUp(!isSignUp); setAuthError(""); }}
              className="text-sm text-primary hover:text-navy-dark font-semibold transition-colors cursor-pointer"
            >
              {isSignUp ? "Déjà un compte ? Connectez-vous" : "Pas encore inscrit ? Créez un compte"}
            </button>
          </div>
        </div>

        {/* Security Tip */}
        <div className="mt-5 p-4 bg-white/80 backdrop-blur-sm border border-border-subtle rounded-xl flex items-start gap-3 shadow-sm">
          <div className="p-1 bg-primary/[0.06] rounded-md mt-0.5">
            <Info className="w-4 h-4 text-primary" />
          </div>
          <div className="text-[13px] text-on-surface-variant leading-relaxed">
            <span className="font-bold text-on-surface text-[11px] uppercase tracking-wider">Conseil de sécurité</span>
            <br />
            Vérifiez toujours que l'URL est{" "}
            <code className="text-primary font-mono text-[11px] bg-primary/[0.04] px-1.5 py-0.5 rounded">sicurre.io</code>{" "}
            avant de saisir vos identifiants.
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-on-surface-variant/40 mt-6">
          &copy; 2026 Sicurre. Tous droits réservés. Protection sécurisée pour l'entreprise moderne.
        </p>
      </MotionDiv>
    </div>
  );
}
