import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Mail, Lock, User, ArrowRight, Home, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import sicurreLogo from "../assets/sicurre.svg";
import { loginSchema, signUpSchema } from "../lib/schemas";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { AuthFlowError, type AuthFailureReason, useLogin, useSignup } from "../lib/api";
import { authBaseURL, authClient } from "../lib/auth-client";
import { Turnstile } from "../components/auth/turnstile";

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
  const [authNotice, setAuthNotice] = useState("");
  const [verificationEmailSent, setVerificationEmailSent] = useState(false);
  const [isResendingVerification, setIsResendingVerification] = useState(false);
  const [resetToken, setResetToken] = useState(
    () => new URLSearchParams(window.location.search).get("token") || "",
  );
  const [isResetComplete, setIsResetComplete] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState("");
  const [turnstileResetSignal, setTurnstileResetSignal] = useState(0);
  const [turnstileConfig, setTurnstileConfig] = useState<{
    status: "idle" | "loading" | "enabled" | "disabled" | "error";
    siteKey: string;
  }>({ status: "idle", siteKey: "" });
  const [activeLegalModal, setActiveLegalModal] = useState<"cgu" | "privacy" | null>(null);
  const loginMutation = useLogin();
  const signupMutation = useSignup();

  useEffect(() => {
    setIsSignUp(initialMode === "signup");
    setAuthError("");
    setAuthNotice("");
    setTurnstileToken("");
  }, [initialMode]);

  useEffect(() => {
    if (!isSignUp || turnstileConfig.status !== "idle") return;

    setTurnstileConfig({ status: "loading", siteKey: "" });
    void fetch(`${authBaseURL}/config`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Auth config unavailable");
        return response.json() as Promise<{
          turnstile?: { enabled?: boolean; siteKey?: string | null };
        }>;
      })
      .then(({ turnstile }) => {
        if (turnstile?.enabled && turnstile.siteKey) {
          setTurnstileConfig({ status: "enabled", siteKey: turnstile.siteKey });
          return;
        }
        setTurnstileConfig({ status: "disabled", siteKey: "" });
      })
      .catch(() => setTurnstileConfig({ status: "error", siteKey: "" }));
  }, [isSignUp, turnstileConfig.status]);

  const handleTurnstileVerify = useCallback((token: string) => {
    setTurnstileToken(token);
    setAuthError("");
  }, []);
  const handleTurnstileExpire = useCallback(() => setTurnstileToken(""), []);
  const handleTurnstileError = useCallback(() => {
    setTurnstileToken("");
    setAuthError(t("login.errors.bot_verification_failed"));
  }, [t]);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    setAuthNotice("");

    if (resetToken) {
      if (password.length < 8) {
        setAuthError("Le mot de passe doit comporter au moins 8 caractères.");
        return;
      }
      try {
        const response = await fetch(`${authBaseURL}/reset-password`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ newPassword: password, token: resetToken }),
        });
        if (!response.ok) throw new Error("INVALID_RESET_TOKEN");
        setIsResetComplete(true);
        setResetToken("");
        setPassword("");
        setAuthNotice("Mot de passe mis à jour. Vous pouvez maintenant vous connecter.");
        window.history.replaceState({}, document.title, "/login");
        return;
      } catch {
        setAuthError("Ce lien de réinitialisation est invalide ou a expiré.");
        return;
      }
    }

    if (isSignUp) {
      const tokenToSubmit = turnstileToken || (import.meta.env.DEV ? "1x00000000000000000000AA" : "");
      if (import.meta.env.PROD && turnstileConfig.status === "enabled" && !tokenToSubmit) {
        setAuthError(t("login.errors.bot_verification_required"));
        return;
      }
      const validation = signUpSchema.safeParse({ name, email, password });
      if (!validation.success) {
        setAuthError(validation.error.errors[0].message);
        return;
      }
      try {
        await signupMutation.mutateAsync({ name, email, password, turnstileToken: tokenToSubmit });
        setPassword("");
        setVerificationEmailSent(true);
      } catch (error) {
        const reason = getAuthFailureReason(error, "signup_failed");
        setAuthError(t(`login.errors.${reason}`));
        if (turnstileConfig.status === "enabled") {
          setTurnstileToken("");
          setTurnstileResetSignal((value) => value + 1);
        }
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

  const handleResendVerification = async () => {
    setAuthError("");
    setAuthNotice("");
    setIsResendingVerification(true);
    try {
      const result = await authClient.sendVerificationEmail({
        email,
        callbackURL: `${window.location.origin}/`,
      });
      if (result.error) throw new Error("VERIFICATION_EMAIL_FAILED");
      setAuthNotice("Un nouveau lien de vérification vient d’être envoyé.");
    } catch {
      setAuthError("Impossible d’envoyer le lien pour le moment. Réessayez dans quelques instants.");
    } finally {
      setIsResendingVerification(false);
    }
  };

  const handlePasswordResetRequest = async () => {
    setAuthError("");
    setAuthNotice("");
    const validation = loginSchema.shape.email.safeParse(email);
    if (!validation.success) {
      setAuthError(t("login.errors.invalid_email"));
      return;
    }
    try {
      const response = await fetch(`${authBaseURL}/request-password-reset`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, redirectTo: `${window.location.origin}/login` }),
      });
      if (!response.ok) throw new Error("RESET_REQUEST_FAILED");
      setAuthNotice("Si un compte correspond à cette adresse, un lien vient d’être envoyé.");
    } catch {
      setAuthError(t("login.errors.service_unavailable"));
    }
  };

  const isSubmitting = loginMutation.isPending || signupMutation.isPending;
  const isTurnstileBlocking = isSignUp && import.meta.env.PROD && (
    turnstileConfig.status === "loading"
    || turnstileConfig.status === "error"
    || (turnstileConfig.status === "enabled" && !turnstileToken)
  );

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
            {verificationEmailSent
              ? "Vérifiez votre adresse e-mail"
              : resetToken && !isResetComplete
              ? "Nouveau mot de passe"
              : isSignUp
                ? "Créer un compte"
                : "Connexion à Sicurre"}
          </h1>
          {!resetToken && !verificationEmailSent && <p className="text-[13px] text-slate-400 mt-2.5">
            {isSignUp ? "Vous avez déjà un compte ? " : "Vous n'avez pas de compte ? "}
            <button
              type="button"
              onClick={() => {
                setIsSignUp(!isSignUp);
                setVerificationEmailSent(false);
                setAuthError("");
                setAuthNotice("");
                setPassword("");
                setShowPassword(false);
                setIsResetComplete(false);
                setTurnstileToken("");
              }}
              className="text-white hover:underline font-semibold cursor-pointer ml-1"
            >
              {isSignUp ? "Se connecter" : "S'inscrire"}
            </button>
          </p>}
        </div>

        {/* Form Container */}
        {verificationEmailSent ? (
          <div className="w-full text-center space-y-4 py-2" role="status">
            <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 border border-primary/20 text-primary">
              <Mail className="h-5 w-5 stroke-[1.75]" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-bold text-white font-display">
                Vérifiez votre boîte mail
              </h3>
              <p className="text-xs text-slate-300">
                Un lien de confirmation a été envoyé à <strong className="text-white select-all">{email}</strong>.
              </p>
            </div>

            {authError && (
              <div className="p-2.5 bg-red-950/30 border border-red-900/40 text-red-400 text-xs rounded-lg font-medium">
                {authError}
              </div>
            )}
            {authNotice && (
              <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/35 p-2.5 text-xs font-medium text-emerald-200">
                {authNotice}
              </div>
            )}

            <div className="pt-3 space-y-3 border-t border-white/10">
              <Button
                type="button"
                size="sm"
                fullWidth
                disabled={isResendingVerification}
                onClick={() => void handleResendVerification()}
                className="h-9 px-4 text-xs font-semibold rounded-lg bg-primary hover:bg-primary/90 text-on-primary shadow-sm shadow-primary/20 transition-colors cursor-pointer"
              >
                {isResendingVerification ? "Envoi en cours…" : "Renvoyer l'e-mail"}
              </Button>

              <div>
                <button
                  type="button"
                  onClick={() => {
                    setVerificationEmailSent(false);
                    setIsSignUp(false);
                    setAuthError("");
                    setAuthNotice("");
                  }}
                  className="text-xs font-medium text-slate-400 hover:text-white transition-colors cursor-pointer"
                >
                  ← Revenir à la connexion
                </button>
              </div>
            </div>
          </div>
        ) : (
        <div className="w-full space-y-5">
          {/* Core Credentials Form */}
          <form onSubmit={handleAuth} className="space-y-4">
            {isSignUp && !resetToken && (
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

            {!resetToken && <Input
              label="Adresse e-mail"
              type="email"
              id="email"
              placeholder="alan.turing@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              icon={<Mail className="w-4 h-4 text-white/40" />}
              className="!bg-slate-950/60 !border-white/10 !text-white !placeholder:text-white/20 focus:!border-white/25 focus:!ring-white/5"
              required
            />}

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label htmlFor="password">
                  Mot de passe
                </label>
                {!isSignUp && !resetToken && (
                  <button
                    type="button"
                    onClick={handlePasswordResetRequest}
                    className="text-[12px] text-slate-400 font-medium hover:text-white transition-colors cursor-pointer"
                  >
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

            {isSignUp && turnstileConfig.status === "loading" && (
              <div className="min-h-[65px] w-full animate-pulse rounded-lg bg-white/[0.06]" aria-label="Chargement de la vérification anti-robot" />
            )}

            {isSignUp && turnstileConfig.status === "enabled" && (
              <Turnstile
                siteKey={turnstileConfig.siteKey}
                resetSignal={turnstileResetSignal}
                onVerify={handleTurnstileVerify}
                onExpire={handleTurnstileExpire}
                onError={handleTurnstileError}
              />
            )}

            {isSignUp && turnstileConfig.status === "error" && (
              <div className="rounded-lg border border-red-900/40 bg-red-950/30 p-3 text-sm font-medium text-red-300" role="alert">
                {t("login.errors.bot_verification_unavailable")}
              </div>
            )}

            {authError && (
              <div className="p-3 bg-red-950/20 border border-red-900/30 text-red-400 text-sm rounded-lg font-medium">
                {authError}
              </div>
            )}

            {authNotice && (
              <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/35 p-3 text-sm font-medium text-emerald-200" role="status">
                {authNotice}
              </div>
            )}

            <Button
              type="submit"
              fullWidth
              disabled={isSubmitting || isTurnstileBlocking}
              className="mt-2 flex items-center justify-center gap-2.5 !py-3 bg-white/[0.08] text-white border border-white/15 hover:bg-primary hover:text-white hover:border-primary hover:shadow-[0_0_25px_rgba(74,144,217,0.4)] text-sm font-semibold rounded-xl transition-all duration-200 cursor-pointer active:scale-[0.98] disabled:opacity-70"
            >
              <span>
                {resetToken && !isResetComplete
                  ? "Mettre à jour le mot de passe"
                  : isSubmitting
                    ? (isSignUp ? "Création en cours…" : "Connexion en cours…")
                    : isSignUp
                      ? "Créer mon compte"
                      : "Se connecter"}
              </span>
              <ArrowRight className="w-4 h-4" />
            </Button>
          </form>
        </div>
        )}

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
                      Sicurre met en œuvre des contrôles de sécurité, de supervision et de reprise adaptés à son environnement.
                      Aucun niveau de service contractuel n'est garanti pendant cette phase de validation. L'utilisateur demeure responsable de ses identifiants.
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
                      Les traitements suivent des principes de minimisation et de conservation limitée. Cloudflare et les prestataires
                      d'infrastructure nécessaires interviennent selon leur rôle technique. <strong className="text-white">Les messages clients ne servent pas à entraîner un modèle public.</strong>
                    </p>
                  </section>

                  <section className="space-y-2">
                    <h3 className="font-display font-medium text-base text-slate-200">2. Politique de Non-Stockage des E-mails</h3>
                    <p>
                      Les messages légitimes ne sont pas conservés en contenu brut. Le MIME original d'un message placé en quarantaine
                      est conservé dans un stockage privé pendant 14 jours au maximum afin de permettre sa restauration, puis supprimé.
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
