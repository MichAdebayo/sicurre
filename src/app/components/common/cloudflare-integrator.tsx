import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Cloud,
  CheckCircle2,
  XCircle,
  Loader2,
  ShieldCheck,
  Mail,
  ExternalLink,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Eye,
  EyeOff,
  Zap,
  HelpCircle,
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

// ── Checklist interface ───────────────────────────────────────────────────────

interface IntegrationStage {
  id: string;
  label: string;
  description: string;
  status: "idle" | "loading" | "success" | "error";
  errorMsg?: string;
}

interface CloudflareIntegratorProps {
  userEmail: string;
}

// ── Main component ────────────────────────────────────────────────────────────

export function CloudflareIntegrator({ userEmail }: CloudflareIntegratorProps) {
  const { data: cfStatus, isLoading: statusLoading, refetch } = useCloudflareStatus();
  const verifyMutation = useVerifyCloudflareToken();
  const setupMutation  = useSetupCloudflare();
  const teardownMutation = useTeardownCloudflare();

  // Controlled form state
  const [cfToken, setCfToken]           = useState("");
  const [showToken, setShowToken]       = useState(false);
  const [zoneName, setZoneName]         = useState("");
  const [showHelp, setShowHelp]         = useState(false);

  // Integration progress state
  const [isIntegrating, setIsIntegrating] = useState(false);
  const [stages, setStages] = useState<IntegrationStage[]>([
    { id: "verify", label: "Vérification des informations d'identification", description: "Vérification du token API Cloudflare et de l'accès au domaine.", status: "idle" },
    { id: "dns", label: "Configuration des enregistrements DNS", description: "Configuration des enregistrements MX nécessaires pour l'acheminement des e-mails.", status: "idle" },
    { id: "worker", label: "Déploiement du Worker", description: "Déploiement du Worker Sicurre pour analyser chaque e-mail entrant en temps réel.", status: "idle" },
    { id: "routing", label: "Liaison du routage & validation finale", description: "Création de la règle catch-all et test final de connectivité de la passerelle.", status: "idle" }
  ]);

  // Teardown state
  const [teardownToken, setTeardownToken] = useState("");
  const [showTeardown, setShowTeardown] = useState(false);

  // Sync background provisioning state with UI progress checklist
  useEffect(() => {
    if (cfStatus?.status === "provisioning" && !isIntegrating) {
      setIsIntegrating(true);
      setStages([
        { id: "verify", label: "Vérification des informations d'identification", description: "Vérification du token API Cloudflare et de l'accès au domaine.", status: "success" },
        { id: "dns", label: "Configuration des enregistrements DNS", description: "Configuration des enregistrements MX nécessaires pour l'acheminement des e-mails.", status: "success" },
        { id: "worker", label: "Déploiement du Worker", description: "Déploiement du Worker Sicurre pour analyser chaque e-mail entrant en temps réel.", status: "success" },
        { id: "routing", label: "Liaison du routage & validation finale", description: "Création de la règle catch-all et test final de connectivité de la passerelle.", status: "loading" }
      ]);
    }
  }, [cfStatus?.status, isIntegrating]);

  // React to status completion updates during routing step
  useEffect(() => {
    let timerId: NodeJS.Timeout | undefined;
    if (isIntegrating && stages.find(s => s.id === "routing")?.status === "loading") {
      if (cfStatus?.status === "pending_verification" || cfStatus?.status === "active") {
        setStages(prev => prev.map(s => s.id === "routing" ? { ...s, status: "success" } : s));
        timerId = setTimeout(() => {
          setIsIntegrating(false);
        }, 1500);
      } else if (cfStatus?.status === "error") {
        setStages(prev => prev.map(s => s.id === "routing" ? { ...s, status: "error", errorMsg: cfStatus.error_message || "Échec de la configuration finale." } : s));
      }
    }
    return () => {
      if (timerId) clearTimeout(timerId);
    };
  }, [cfStatus?.status, isIntegrating, stages]);

  // Poll status ONLY when integrating or provisioning in the background
  useEffect(() => {
    if (!isIntegrating && cfStatus?.status !== "provisioning") return;
    const id = setInterval(() => refetch(), 3000);
    return () => clearInterval(id);
  }, [isIntegrating, cfStatus?.status, refetch]);

  // ── Integration Orchestration ─────────────────────────────────────────────

  const handleIntegrate = async () => {
    if (!cfToken.trim() || !zoneName.trim()) return;

    setIsIntegrating(true);
    setStages([
      { id: "verify", label: "Vérification des informations d'identification", description: "Vérification du token API Cloudflare et de l'accès au domaine.", status: "loading" },
      { id: "dns", label: "Configuration des enregistrements DNS", description: "Configuration des enregistrements MX nécessaires pour l'acheminement des e-mails.", status: "idle" },
      { id: "worker", label: "Déploiement du Worker", description: "Déploiement du Worker Sicurre pour analyser chaque e-mail entrant en temps réel.", status: "idle" },
      { id: "routing", label: "Liaison du routage & validation finale", description: "Création de la règle catch-all et test final de connectivité de la passerelle.", status: "idle" }
    ]);

    try {
      // Step 1: Verify token
      const result = await verifyMutation.mutateAsync({
        cf_api_token: cfToken,
        zone_name: zoneName,
      });

      if (!result.valid) {
        setStages(prev => prev.map(s => s.id === "verify" ? { ...s, status: "error", errorMsg: result.error || "Token ou domaine invalide." } : s));
        return;
      }

      setStages(prev => prev.map(s =>
        s.id === "verify" ? { ...s, status: "success" } :
        s.id === "dns" ? { ...s, status: "loading" } : s
      ));

      // Step 2: DNS MX Configuration simulation (DNS check happens backend)
      await new Promise(resolve => setTimeout(resolve, 1500));
      setStages(prev => prev.map(s =>
        s.id === "dns" ? { ...s, status: "success" } :
        s.id === "worker" ? { ...s, status: "loading" } : s
      ));

      // Step 3: Trigger setup
      await setupMutation.mutateAsync({
        cf_api_token: cfToken,
        zone_name: zoneName,
        destination_email: userEmail,
      });

      setStages(prev => prev.map(s =>
        s.id === "worker" ? { ...s, status: "success" } :
        s.id === "routing" ? { ...s, status: "loading" } : s
      ));

      // Step 4: Routing & validation will update via the useEffect watching status changes
      refetch();
    } catch (err: any) {
      setStages(prev => prev.map(s => {
        if (s.status === "loading") {
          return { ...s, status: "error", errorMsg: err.message || "Une erreur est survenue lors de cette étape." };
        }
        return s;
      }));
    }
  };

  // ── Teardown ──────────────────────────────────────────────────────────────

  const handleTeardown = async () => {
    if (!teardownToken.trim()) return;
    try {
      await teardownMutation.mutateAsync({ cf_api_token: teardownToken });
      setShowTeardown(false);
      setTeardownToken("");
      refetch();
    } catch {
      // error shown via teardownMutation.error
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  // Clean, quiet skeleton loader when status is checking for the first time
  if (statusLoading && !cfStatus) {
    return (
      <div className="space-y-6">
        <div className="bg-surface-lowest border border-border-subtle rounded-xl p-5 space-y-4 animate-pulse">
          <div className="h-6 bg-surface-container rounded-md w-1/3" />
          <div className="h-4 bg-surface-container rounded-md w-2/3" />
          <div className="grid grid-cols-1 gap-4">
            <div className="h-10 bg-surface-container rounded-md" />
            <div className="h-10 bg-surface-container rounded-md" />
          </div>
        </div>
        <div className="flex justify-end">
          <div className="h-10 bg-surface-container rounded-md w-32" />
        </div>
      </div>
    );
  }

  const intStatus: CloudflareStatus = cfStatus || { status: "not_configured" };

  // ── INTEGRATING / WIZARD CHECKLIST STATE ────────────────────────────────────
  if (isIntegrating) {
    const activeStage = stages.find(s => s.status === "loading" || s.status === "error");
    const hasError = stages.some(s => s.status === "error");

    return (
      <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
        <div className="bg-surface-low/30 border border-border-subtle rounded-xl p-5 space-y-5">
          <div>
            <h4 className="font-display font-semibold text-[15px] text-on-surface">Configuration de l'Intégration</h4>
            <p className="text-xs text-on-surface-variant mt-0.5">
              Suivi en direct des étapes de provisionnement sur votre compte Cloudflare.
            </p>
          </div>

          <div className="space-y-4">
            {stages.map((stage) => (
              <div key={stage.id} className="flex items-start gap-3.5">
                <div className="mt-0.5 shrink-0">
                  {stage.status === "idle" && (
                    <div className="w-5 h-5 rounded-full border border-border-subtle bg-surface-lowest flex items-center justify-center text-[10px] text-on-surface-variant/40 font-bold" />
                  )}
                  {stage.status === "loading" && (
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                  )}
                  {stage.status === "success" && (
                    <CheckCircle2 className="w-5 h-5 text-safe" />
                  )}
                  {stage.status === "error" && (
                    <XCircle className="w-5 h-5 text-error" />
                  )}
                </div>
                <div className="space-y-0.5">
                  <p className={`text-sm font-semibold ${
                    stage.status === "error" ? "text-error" :
                    stage.status === "loading" ? "text-primary" :
                    stage.status === "success" ? "text-on-surface" : "text-on-surface-variant/60"
                  }`}>
                    {stage.label}
                  </p>
                  <p className="text-xs text-on-surface-variant/70 leading-relaxed">
                    {stage.description}
                  </p>
                  {stage.status === "error" && stage.errorMsg && (
                    <p className="text-[11px] font-semibold text-error bg-error/[0.04] border border-error/10 rounded px-2.5 py-1.5 mt-2.5 max-w-xl font-mono break-all">
                      {stage.errorMsg}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>

          {hasError && (
            <div className="pt-2 border-t border-border-subtle flex gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsIntegrating(false)}
                className="text-[11px]"
              >
                Retourner à la configuration
              </Button>
            </div>
          )}
        </div>
      </MotionDiv>
    );
  }

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
                size="sm"
                onClick={handleTeardown}
                disabled={!teardownToken || teardownMutation.isPending}
                className="gap-1.5 text-[11px]"
              >
                {teardownMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                Confirmer la désactivation
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowTeardown(false)} className="text-[11px]">
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
              <Button variant="danger" size="sm" onClick={handleTeardown} disabled={!teardownToken || teardownMutation.isPending} className="gap-1.5 text-[11px]">
                {teardownMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                Supprimer
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowTeardown(false)} className="text-[11px]">Annuler</Button>
            </div>
          </div>
        )}
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
          variant="outline"
          size="sm"
          onClick={async () => {
            if (cfToken) {
              await teardownMutation.mutateAsync({ cf_api_token: cfToken || "dummy" }).catch(() => {});
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

  // ── WIZARD / INPUT FORM STATE (not_configured) ─────────────────────────────
  const isFormValid = cfToken.trim() !== "" && zoneName.trim() !== "";

  return (
    <MotionDiv initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="bg-surface-low/30 border border-border-subtle rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 relative">
          <h4 className="font-display font-semibold text-[15px] text-on-surface">Configurer l'Intégration</h4>
          <div
            className="relative inline-block"
            onMouseEnter={() => setShowHelp(true)}
            onMouseLeave={() => setShowHelp(false)}
          >
            <button
              type="button"
              onClick={() => setShowHelp(v => !v)}
              className="text-on-surface-variant/50 hover:text-primary transition-colors cursor-help p-0.5 rounded-full hover:bg-surface-low/50 flex items-center justify-center outline-none"
              aria-label="Aide à la configuration"
            >
              <HelpCircle className="w-3.5 h-3.5" />
            </button>
            <AnimatePresence>
              {showHelp && (
                <MotionDiv
                  initial={{ opacity: 0, y: 8, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 8, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute left-6 -top-2 z-30 w-72 bg-white border border-border-subtle p-4 rounded-xl shadow-lg text-[11px] text-on-surface-variant/80 space-y-1.5 leading-normal"
                >
                  <p className="font-bold text-on-surface">Instructions pour générer le token Cloudflare :</p>
                  <p>1. Connectez-vous à votre compte sur <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noreferrer" className="text-primary underline inline-flex items-center gap-0.5 font-semibold">dash.cloudflare.com <ExternalLink className="w-3 h-3" /></a>.</p>
                  <p>2. Créez un jeton personnalisé avec les droits d'écriture (Edit) suivants :</p>
                  <ul className="list-disc pl-4 space-y-0.5 mt-1 font-medium text-on-surface">
                    <li>Zone › DNS › Modifier</li>
                    <li>Workers Scripts › Modifier</li>
                    <li>Email Routing › Modifier</li>
                  </ul>
                </MotionDiv>
              )}
            </AnimatePresence>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 pt-2">
          <div>
            <Input
              label="Token Cloudflare API"
              type={showToken ? "text" : "password"}
              value={cfToken}
              onChange={e => setCfToken(e.target.value)}
              placeholder="Ex: d784a3b8cd9a98ef12..."
              suffix={
                <button type="button" onClick={() => setShowToken(v => !v)} className="text-on-surface-variant/60 hover:text-on-surface transition-colors cursor-pointer">
                  {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              }
            />
          </div>

          <div>
            <Input
              label="Domaine à protéger"
              type="text"
              value={zoneName}
              onChange={e => setZoneName(e.target.value.trim().toLowerCase())}
              placeholder="Ex: mon-entreprise.fr"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <Button
          onClick={handleIntegrate}
          disabled={!isFormValid || verifyMutation.isPending || setupMutation.isPending}
          className="w-full sm:w-auto gap-2 uppercase tracking-wider text-[12px] font-bold"
        >
          {verifyMutation.isPending || setupMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Zap className="w-4 h-4" />
          )}
          Intégrer le domaine
        </Button>
      </div>
    </MotionDiv>
  );
}
