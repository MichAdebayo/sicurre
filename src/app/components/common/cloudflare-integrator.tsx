import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Cloud,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronRight,
  ShieldCheck,
  Mail,
  ExternalLink,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Eye,
  EyeOff,
  Zap,
} from "lucide-react";
import { Input } from "../ui/input";
import { Button } from "../ui/button";
import {
  useCloudflareStatus,
  useVerifyCloudflareToken,
  useSetupCloudflare,
  useTeardownCloudflare,
  type CloudflareStatus,
} from "../../lib/api";

const MotionDiv = motion.div as any;

// ── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
    not_configured:       { label: "Non configuré",          className: "text-on-surface-variant bg-surface-container border-border-subtle", icon: <Cloud className="w-3 h-3" /> },
    provisioning:         { label: "Provisionnement…",       className: "text-amber-600 bg-amber-50 border-amber-200",    icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    pending_verification: { label: "Vérification en attente",className: "text-amber-600 bg-amber-50 border-amber-200",    icon: <Mail className="w-3 h-3" /> },
    active:               { label: "Actif",                   className: "text-safe bg-safe/[0.08] border-safe/20",        icon: <Zap className="w-3 h-3" /> },
    error:                { label: "Erreur",                  className: "text-error bg-error/[0.06] border-error/20",     icon: <XCircle className="w-3 h-3" /> },
  };
  const cfg = map[status] ?? map.not_configured;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.1em] px-2.5 py-1 rounded-full border ${cfg.className}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

// ── Step indicator ────────────────────────────────────────────────────────────

function StepDot({ n, current, done }: { n: number; current: number; done: boolean }) {
  const active = n === current;
  return (
    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold border-2 transition-all ${
      done    ? "bg-safe border-safe text-white" :
      active  ? "bg-primary border-primary text-white" :
                "bg-surface-container border-border-subtle text-on-surface-variant"
    }`}>
      {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : n}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function CloudflareIntegrator() {
  const userEmail = localStorage.getItem("sicurre_user_email") || localStorage.getItem("sicurre_user_name") || "user@example.com";

  const { data: cfStatus, isLoading: statusLoading, refetch } = useCloudflareStatus(userEmail);
  const verifyMutation = useVerifyCloudflareToken();
  const setupMutation  = useSetupCloudflare();
  const teardownMutation = useTeardownCloudflare();

  // Wizard form state
  const [step, setStep]                 = useState(1);
  const [cfToken, setCfToken]           = useState("");
  const [showToken, setShowToken]       = useState(false);
  const [zoneName, setZoneName]         = useState("");
  const [destEmail, setDestEmail]       = useState("");
  const [tokenValid, setTokenValid]     = useState<null | boolean>(null);
  const [zoneId, setZoneId]             = useState<string | null>(null);
  const [tokenError, setTokenError]     = useState("");
  const [teardownToken, setTeardownToken] = useState("");
  const [showTeardown, setShowTeardown] = useState(false);

  // Poll while provisioning
  const isProvisioning = cfStatus?.status === "provisioning";
  useEffect(() => {
    if (!isProvisioning) return;
    const id = setInterval(() => refetch(), 3000);
    return () => clearInterval(id);
  }, [isProvisioning, refetch]);

  // ── Step 1: Validate token + zone ────────────────────────────────────────

  const handleVerifyToken = async () => {
    if (!cfToken.trim() || !zoneName.trim()) return;
    setTokenValid(null);
    setTokenError("");
    try {
      const result = await verifyMutation.mutateAsync({ cf_api_token: cfToken, zone_name: zoneName });
      if (result.valid) {
        setTokenValid(true);
        setZoneId(result.zone_id);
      } else {
        setTokenValid(false);
        setTokenError(result.error || "Token ou domaine invalide.");
      }
    } catch {
      setTokenValid(false);
      setTokenError("Erreur réseau lors de la vérification.");
    }
  };

  // ── Step 2: Submit setup ──────────────────────────────────────────────────

  const handleSetup = async () => {
    if (!tokenValid || !destEmail.trim()) return;
    try {
      await setupMutation.mutateAsync({
        cf_api_token: cfToken,
        zone_name:    zoneName,
        destination_email: destEmail,
        user_email:   userEmail,
      });
      refetch();
    } catch (err: any) {
      // error shown via setupMutation.error
    }
  };

  // ── Teardown ──────────────────────────────────────────────────────────────

  const handleTeardown = async () => {
    if (!teardownToken.trim()) return;
    try {
      await teardownMutation.mutateAsync({ cf_api_token: teardownToken, user_email: userEmail });
      setShowTeardown(false);
      setTeardownToken("");
      refetch();
    } catch {
      // error shown via teardownMutation.error
    }
  };

  // ── Render based on current status ────────────────────────────────────────

  if (statusLoading) {
    return (
      <div className="flex items-center gap-2.5 py-6 text-on-surface-variant text-sm">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Vérification de l'intégration…</span>
      </div>
    );
  }

  const intStatus: CloudflareStatus = cfStatus || { status: "not_configured" };

  // ── ACTIVE STATE ──────────────────────────────────────────────────────────
  if (intStatus.status === "active") {
    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
        <div className="flex items-start justify-between gap-4 p-4 bg-safe/[0.05] border border-safe/20 rounded-xl">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-safe/10 rounded-lg flex items-center justify-center border border-safe/20">
              <ShieldCheck className="w-5 h-5 text-safe" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-bold text-sm text-on-surface">{intStatus.zone_name}</span>
                <StatusBadge status="active" />
              </div>
              <p className="text-xs text-on-surface-variant">
                Emails transférés vers <strong>{intStatus.destination_email}</strong> après scan
              </p>
              <p className="text-[10px] text-on-surface-variant/50 font-mono mt-0.5">
                Worker: {intStatus.worker_name}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="p-3 bg-surface-low border border-border-subtle rounded-lg text-center">
            <div className="font-bold text-on-surface text-sm mb-0.5">Phishing</div>
            <div className="text-on-surface-variant">Rejeté automatiquement</div>
          </div>
          <div className="p-3 bg-surface-low border border-border-subtle rounded-lg text-center">
            <div className="font-bold text-on-surface text-sm mb-0.5">Spam</div>
            <div className="text-on-surface-variant">Transféré + marqué</div>
          </div>
          <div className="p-3 bg-surface-low border border-border-subtle rounded-lg text-center">
            <div className="font-bold text-on-surface text-sm mb-0.5">Légitime</div>
            <div className="text-on-surface-variant">Transféré intact</div>
          </div>
        </div>

        {/* Teardown section */}
        {!showTeardown ? (
          <button
            onClick={() => setShowTeardown(true)}
            className="flex items-center gap-1.5 text-xs text-error/70 hover:text-error transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Désactiver l'intégration
          </button>
        ) : (
          <div className="p-4 border border-error/20 bg-error/[0.03] rounded-xl space-y-3">
            <p className="text-xs font-semibold text-error">
              Fournissez votre token Cloudflare pour supprimer le Worker et la règle de routage.
            </p>
            <Input
              label="Token Cloudflare"
              type="password"
              value={teardownToken}
              onChange={e => setTeardownToken(e.target.value)}
              placeholder="Votre token CF…"
            />
            {teardownMutation.isError && (
              <p className="text-xs text-error">{(teardownMutation.error as Error)?.message}</p>
            )}
            <div className="flex gap-2">
              <Button
                variant="danger"
                onClick={handleTeardown}
                disabled={!teardownToken || teardownMutation.isPending}
                className="gap-1.5 text-[11px]"
              >
                {teardownMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                Confirmer la désactivation
              </Button>
              <Button variant="secondary" onClick={() => setShowTeardown(false)} className="text-[11px]">
                Annuler
              </Button>
            </div>
          </div>
        )}
      </MotionDiv>
    );
  }

  // ── PENDING VERIFICATION ──────────────────────────────────────────────────
  if (intStatus.status === "pending_verification") {
    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl">
          <Mail className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-bold text-sm text-amber-800 mb-1">Vérifiez votre boîte email</p>
            <p className="text-xs text-amber-700">
              Cloudflare a envoyé un email de vérification à{" "}
              <strong>{intStatus.destination_email}</strong>. Cliquez sur le lien dans cet email pour
              activer le transfert. L'intégration deviendra active automatiquement dès le premier email reçu.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-on-surface-variant">
            Zone : <strong>{intStatus.zone_name}</strong> · Worker : <code className="font-mono text-[10px] bg-surface-container px-1 rounded">{intStatus.worker_name}</code>
          </div>
          <StatusBadge status="pending_verification" />
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 text-xs text-primary hover:text-primary-dark transition-colors cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Actualiser le statut
        </button>
        {!showTeardown ? (
          <button onClick={() => setShowTeardown(true)} className="flex items-center gap-1.5 text-xs text-error/70 hover:text-error transition-colors cursor-pointer">
            <Trash2 className="w-3.5 h-3.5" /> Annuler et supprimer
          </button>
        ) : (
          <div className="p-4 border border-error/20 bg-error/[0.03] rounded-xl space-y-3">
            <Input label="Token Cloudflare" type="password" value={teardownToken} onChange={e => setTeardownToken(e.target.value)} placeholder="Votre token CF…" />
            <div className="flex gap-2">
              <Button variant="danger" onClick={handleTeardown} disabled={!teardownToken || teardownMutation.isPending} className="gap-1.5 text-[11px]">
                {teardownMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                Supprimer
              </Button>
              <Button variant="secondary" onClick={() => setShowTeardown(false)} className="text-[11px]">Annuler</Button>
            </div>
          </div>
        )}
      </MotionDiv>
    );
  }

  // ── PROVISIONING ──────────────────────────────────────────────────────────
  if (intStatus.status === "provisioning") {
    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center py-8 gap-3">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
        <p className="font-semibold text-sm text-on-surface">Provisionnement en cours…</p>
        <p className="text-xs text-on-surface-variant text-center max-w-xs">
          Déploiement du Worker Cloudflare et configuration du routage email. Cela prend 10–20 secondes.
        </p>
      </MotionDiv>
    );
  }

  // ── ERROR STATE ───────────────────────────────────────────────────────────
  if (intStatus.status === "error") {
    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-error/[0.04] border border-error/20 rounded-xl">
          <AlertTriangle className="w-5 h-5 text-error shrink-0 mt-0.5" />
          <div>
            <p className="font-bold text-sm text-error mb-1">Échec du provisionnement</p>
            <p className="text-xs text-error/80 font-mono break-all">{intStatus.error_message || "Erreur inconnue"}</p>
          </div>
        </div>
        <p className="text-xs text-on-surface-variant">Vérifiez le token et les permissions, puis réessayez.</p>
        <Button
          variant="secondary"
          onClick={async () => {
            // Delete the error record so the wizard resets
            if (cfToken) {
              await teardownMutation.mutateAsync({ cf_api_token: cfToken || "dummy", user_email: userEmail }).catch(() => {});
            }
            refetch();
          }}
          className="gap-1.5 text-[11px]"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Réessayer
        </Button>
      </MotionDiv>
    );
  }

  // ── WIZARD (not_configured) ───────────────────────────────────────────────
  return (
    <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      {/* Step indicators */}
      <div className="flex items-center gap-0">
        {[1, 2, 3].map((n, i) => (
          <React.Fragment key={n}>
            <StepDot n={n} current={step} done={n < step} />
            {i < 2 && (
              <div className={`flex-1 h-px mx-1 transition-colors ${step > n ? "bg-primary" : "bg-border-subtle"}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {/* ── Step 1: Token + domain ─────────────────────────────────────── */}
        {step === 1 && (
          <MotionDiv key="step1" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} className="space-y-4">
            <div>
              <h4 className="font-display font-semibold text-[15px] text-on-surface mb-0.5">Token Cloudflare & Domaine</h4>
              <p className="text-xs text-on-surface-variant">
                Créez un token restreint sur{" "}
                <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2 inline-flex items-center gap-0.5">
                  dash.cloudflare.com <ExternalLink className="w-3 h-3" />
                </a>{" "}
                avec les permissions : <strong>Zone › DNS › Edit</strong>, <strong>Workers Scripts › Edit</strong>, <strong>Email Routing › Edit</strong>.
              </p>
            </div>

            <Input
              label="Token Cloudflare API"
              type={showToken ? "text" : "password"}
              value={cfToken}
              onChange={e => { setCfToken(e.target.value); setTokenValid(null); }}
              placeholder="Votre token CF…"
              suffix={
                <button type="button" onClick={() => setShowToken(v => !v)} className="text-on-surface-variant/60 hover:text-on-surface transition-colors cursor-pointer">
                  {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              }
            />

            <Input
              label="Domaine à protéger"
              type="text"
              value={zoneName}
              onChange={e => { setZoneName(e.target.value.trim().toLowerCase()); setTokenValid(null); }}
              placeholder="vinse.app"
            />

            {tokenValid === false && (
              <div className="flex items-center gap-2 text-xs text-error">
                <XCircle className="w-3.5 h-3.5 shrink-0" /> {tokenError}
              </div>
            )}
            {tokenValid === true && (
              <div className="flex items-center gap-2 text-xs text-safe">
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> Token valide · Zone <strong>{zoneName}</strong> trouvée (id: {zoneId})
              </div>
            )}

            <div className="flex items-center gap-2 pt-1">
              {tokenValid !== true && (
                <Button
                  variant="secondary"
                  onClick={handleVerifyToken}
                  disabled={!cfToken || !zoneName || verifyMutation.isPending}
                  className="gap-1.5 text-[11px]"
                >
                  {verifyMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                  Vérifier le token
                </Button>
              )}
              {tokenValid === true && (
                <Button onClick={() => setStep(2)} className="gap-1.5 text-[11px]">
                  Continuer <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              )}
            </div>
          </MotionDiv>
        )}

        {/* ── Step 2: Destination email ──────────────────────────────────── */}
        {step === 2 && (
          <MotionDiv key="step2" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} className="space-y-4">
            <div>
              <h4 className="font-display font-semibold text-[15px] text-on-surface mb-0.5">Adresse de livraison</h4>
              <p className="text-xs text-on-surface-variant">
                Les emails propres (non-phishing) seront transférés vers cette adresse après scan. Cloudflare vous enverra un email de vérification à cette adresse.
              </p>
            </div>

            <Input
              label="Email de destination"
              type="email"
              value={destEmail}
              onChange={e => setDestEmail(e.target.value)}
              placeholder="votre@gmail.com"
            />

            <div className="p-3 bg-primary/[0.04] border border-primary/20 rounded-lg text-xs text-on-surface-variant space-y-1">
              <p><strong>Ce qui se passera automatiquement :</strong></p>
              <p>• Email Routing activé sur <strong>{zoneName}</strong></p>
              <p>• Worker Sicurre déployé sur Cloudflare</p>
              <p>• Règle catch-all créée (tous emails → Worker → scan → livraison)</p>
              <p>• Email de vérification CF envoyé à <strong>{destEmail || "votre adresse"}</strong></p>
            </div>

            {setupMutation.isError && (
              <div className="flex items-start gap-2 text-xs text-error">
                <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                {(setupMutation.error as Error)?.message}
              </div>
            )}

            <div className="flex items-center gap-2 pt-1">
              <Button variant="secondary" onClick={() => setStep(1)} className="text-[11px]">Retour</Button>
              <Button
                onClick={handleSetup}
                disabled={!destEmail || setupMutation.isPending}
                className="gap-1.5 text-[11px]"
              >
                {setupMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                Lancer le provisionnement
              </Button>
            </div>
          </MotionDiv>
        )}
      </AnimatePresence>
    </MotionDiv>
  );
}
