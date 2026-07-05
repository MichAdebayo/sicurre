import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Mail, Lock, User, ArrowRight, Home } from "lucide-react";
import { motion } from "framer-motion";
import sicurreLogo from "../assets/sicurre.svg";
import { loginSchema, signUpSchema } from "../lib/schemas";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { useLogin, useSignup } from "../lib/api";

const MotionDiv = motion.div as any;

interface LoginRouteProps {
  onLoginSuccess: () => void;
  initialMode?: "login" | "signup";
  onNavigateToLanding?: () => void;
  onNavigateToCGU?: () => void;
  onNavigateToConfidentialite?: () => void;
}

export default function LoginRoute({
  onLoginSuccess,
  initialMode = "login",
  onNavigateToLanding,
  onNavigateToCGU,
  onNavigateToConfidentialite,
}: LoginRouteProps) {
  const { t } = useTranslation();
  const [isSignUp, setIsSignUp] = useState(initialMode === "signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState("");
  const loginMutation = useLogin();
  const signupMutation = useSignup();

  useEffect(() => {
    setIsSignUp(initialMode === "signup");
    setAuthError("");
  }, [initialMode]);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");

    if (isSignUp) {
      const validation = signUpSchema.safeParse({ name, email, password });
      if (!validation.success) {
        setAuthError(validation.error.errors[0].message);
        return;
      }
      try {
        await signupMutation.mutateAsync({ name, email, password });
        onLoginSuccess();
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : "Inscription impossible.");
      }
    } else {
      const validation = loginSchema.safeParse({ email, password });
      if (!validation.success) {
        setAuthError(validation.error.errors[0].message);
        return;
      }
      try {
        await loginMutation.mutateAsync({ email, password });
        onLoginSuccess();
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : (t("login.error_invalid") || "Identifiants incorrects."));
      }
    }
  };

  const isSubmitting = loginMutation.isPending || signupMutation.isPending;

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

      {/* ── Home Back Button (Top Left) ── */}
      {onNavigateToLanding && (
        <button
          onClick={onNavigateToLanding}
          aria-label="Retour à l'accueil"
          className="absolute top-6 left-6 p-2.5 text-white/90 bg-white/[0.06] hover:bg-primary hover:border-primary border border-white/15 rounded-xl cursor-pointer transition-all shadow-sm z-20 flex items-center justify-center"
        >
          <Home className="w-4.5 h-4.5" />
        </button>
      )}

      {/* ── Unified Brand Background Spotlight & Space Grid ── */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-5xl h-96 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse 60% 50% at 50% 0%, rgba(74,144,217,0.08) 0%, transparent 70%)",
        }}
      />
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.008)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.008)_1px,transparent_1px)] bg-[size:5rem_5rem] pointer-events-none" />

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

        {/* Form Container */}
        <div className="w-full space-y-5">
          {/* Google SSO Button with Primary Hover */}
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-2.5 py-2.5 bg-white/5 hover:bg-primary/20 hover:border-primary/50 hover:text-white border border-white/10 text-white rounded-lg text-sm font-semibold transition-all cursor-pointer shadow-sm hover:shadow-[0_0_20px_rgba(74,144,217,0.2)]"
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

            <Button
              type="submit"
              fullWidth
              disabled={isSubmitting}
              className="mt-2 flex items-center justify-center gap-2 !py-2.5 bg-primary hover:bg-navy-dark text-white font-semibold rounded-lg transition-colors cursor-pointer shadow-md shadow-primary/20 hover:shadow-primary/40 disabled:opacity-70"
            >
              <span>{isSubmitting ? "Connexion en cours…" : isSignUp ? "Créer mon compte" : "Se connecter"}</span>
              <ArrowRight className="w-4 h-4" />
            </Button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-slate-500 mt-10 leading-relaxed">
          En vous connectant, vous acceptez nos{" "}
          <button
            onClick={onNavigateToCGU}
            className="text-white hover:underline cursor-pointer border-none bg-transparent p-0 text-inherit font-inherit"
          >
            Conditions d'utilisation
          </button>{" "}
          et notre{" "}
          <button
            onClick={onNavigateToConfidentialite}
            className="text-white hover:underline cursor-pointer border-none bg-transparent p-0 text-inherit font-inherit"
          >
            Politique de confidentialité
          </button>.
        </p>
      </MotionDiv>
    </div>
  );
}
