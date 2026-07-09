import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Mail, Lock, User, ArrowRight, Home, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import sicurreLogo from "../assets/sicurre.svg";
import { loginSchema, signUpSchema } from "../lib/schemas";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { AuthFlowError, type AuthFailureReason, useLogin, useSignup } from "../lib/api";

const MotionDiv = motion.div as any;

interface LoginRouteProps {
  onLoginSuccess: () => void;
  initialMode?: "login" | "signup";
  onNavigateToLanding?: () => void;
}

const getAuthFailureReason = (error: unknown, fallback: AuthFailureReason): AuthFailureReason => {
  if (error instanceof AuthFlowError) {
    return error.reason;
  }
  return fallback;
};

export default function LoginRoute({
  onLoginSuccess,
  initialMode = "login",
  onNavigateToLanding,
}: LoginRouteProps) {
  const { t } = useTranslation();
  const [isSignUp, setIsSignUp] = useState(initialMode === "signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState("");
  const [activeLegalModal, setActiveLegalModal] = useState<"cgu" | "privacy" | null>(null);
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
        const reason = getAuthFailureReason(error, "signup_failed");
        setAuthError(t(`login.errors.${reason}`));
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
        const reason = getAuthFailureReason(error, "login_failed");
        setAuthError(t(`login.errors.${reason}`));
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

      {/* ── Main Form Layout ── */}
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
          {/* Google SSO Button */}
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-2.5 !py-3 bg-white/[0.08] text-white border border-white/15 hover:bg-primary hover:text-white hover:border-primary hover:shadow-[0_0_25px_rgba(74,144,217,0.4)] text-sm font-semibold rounded-xl transition-all duration-200 cursor-pointer active:scale-[0.98]"
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
              className="mt-2 flex items-center justify-center gap-2.5 !py-3 bg-white/[0.08] text-white border border-white/15 hover:bg-primary hover:text-white hover:border-primary hover:shadow-[0_0_25px_rgba(74,144,217,0.4)] text-sm font-semibold rounded-xl transition-all duration-200 cursor-pointer active:scale-[0.98] disabled:opacity-70"
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
            onClick={() => setActiveLegalModal("cgu")}
            className="text-white hover:underline cursor-pointer border-none bg-transparent p-0 text-inherit font-inherit"
          >
            Conditions d'utilisation
          </button>{" "}
          et notre{" "}
          <button
            onClick={() => setActiveLegalModal("privacy")}
            className="text-white hover:underline cursor-pointer border-none bg-transparent p-0 text-inherit font-inherit"
          >
            Politique de confidentialité
          </button>.
        </p>
      </MotionDiv>

      {/* ── In-Place Legal Modal Overlay ── */}
      <AnimatePresence>
        {activeLegalModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 lg:p-8 bg-black/80 backdrop-blur-md overflow-y-auto">
            <MotionDiv
              initial={{ opacity: 0, scale: 0.95, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 16 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              className="relative w-full max-w-3xl max-h-[85vh] bg-[#0a0d18] border border-white/15 rounded-2xl p-6 sm:p-8 lg:p-10 overflow-y-auto shadow-2xl text-left font-sans text-white space-y-6"
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between border-b border-white/10 pb-4 sticky top-0 bg-[#0a0d18] z-20 pt-1">
                <h2 className="font-display font-medium text-2xl text-slate-100 tracking-tight">
                  {activeLegalModal === "cgu" ? "Conditions Générales d'Utilisation" : "Politique de Confidentialité"}
                </h2>
                <button
                  onClick={() => setActiveLegalModal(null)}
                  aria-label="Fermer"
                  className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Modal Body */}
              {activeLegalModal === "cgu" ? (
                <div className="space-y-6 text-slate-400 text-sm leading-relaxed">
                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">1. Objet des CGU</h3>
                    <p>
                      Les présentes Conditions Générales d'Utilisation (CGU) encadrent l'accès et l'utilisation de la plateforme 
                      <strong className="text-white"> Sicurre</strong>. La plateforme fournit un service automatisé 
                      d'analyse et de remédiation en temps réel des menaces par e-mail (phishing, indésirables, ingénierie sociale).
                    </p>
                  </section>

                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">2. Connexion & Intégration Cloudflare</h3>
                    <p>
                      L'activation de la protection Sicurre nécessite l'association d'un jeton d'accès Cloudflare restreint. 
                      En configurant cette intégration, l'utilisateur autorise Sicurre à inspecter les métadonnées des e-mails entrants, 
                      sécuriser les enregistrements DNS (SPF, DKIM, DMARC), et isoler temporairement les messages malveillants.
                    </p>
                  </section>

                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">3. Engagements & Responsabilités</h3>
                    <p>
                      Sicurre s'engage à maintenir un niveau élevé de disponibilité (99.9% de SLA) et à appliquer les meilleures 
                      règles de sécurité informatique souveraine. L'utilisateur demeure responsable de la confidentialité de ses identifiants.
                    </p>
                  </section>

                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">4. Droit applicable</h3>
                    <p>
                      Les présentes CGU sont soumises au droit français. Tout litige relève des tribunaux compétents de Paris, France.
                    </p>
                  </section>
                </div>
              ) : (
                <div className="space-y-6 text-slate-400 text-sm leading-relaxed">
                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">1. Engagements RGPD et Souveraineté</h3>
                    <p>
                      Chez Sicurre, nous traitons la sécurité et la confidentialité de vos e-mails avec la plus grande rigueur. 
                      En conformité totale avec le RGPD, toutes les analyses d'inférence de phishing sont exécutées sur des 
                      infrastructures souveraines situées en France. <strong className="text-white">Aucun e-mail n'est partagé avec des tiers ou utilisé pour entraîner des modèles publics.</strong>
                    </p>
                  </section>

                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">2. Politique de Non-Stockage des E-mails</h3>
                    <p>
                      Par défaut, <strong className="text-white">Sicurre ne stocke jamais le corps ou le contenu de vos e-mails</strong> dans ses bases de données. 
                      Seules les métadonnées techniques indispensables à votre journal de sécurité sont enregistrées (expéditeur, destinataire, sujet, verdict score).
                    </p>
                  </section>

                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">3. Masquage PII Automatique</h3>
                    <p>
                      Toutes les données à caractère personnel (e-mails secondaires, numéros de téléphone, IBAN) transitant par le système 
                      sont automatiquement transformées en balises anonymisées (<code className="text-primary bg-primary/10 px-1.5 py-0.5 rounded border border-primary/20">[EMAIL]</code>, <code className="text-primary bg-primary/10 px-1.5 py-0.5 rounded border border-primary/20">[IBAN]</code>) avant tout archivage.
                    </p>
                  </section>
                </div>
              )}
            </MotionDiv>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
