import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mail,
  ShieldCheck,
  ShieldX,
  CheckCircle2,
  XCircle,
} from "lucide-react";

const MotionDiv = motion.div as any;

/* ── Fake email data for the animation ── */
const EMAIL_POOL = [
  { sender: "support@paypa1-secure.com", subject: "Vérifiez votre compte immédiatement", verdict: "blocked" as const },
  { sender: "marie.dupont@acme.fr", subject: "Rapport trimestriel Q2 2026", verdict: "delivered" as const },
  { sender: "noreply@impots-gouv.info", subject: "Remboursement en attente #4892", verdict: "blocked" as const },
  { sender: "jean@partenaire.fr", subject: "Contrat de prestation — Signature", verdict: "delivered" as const },
  { sender: "security@micros0ft.com", subject: "Activité suspecte détectée", verdict: "blocked" as const },
  { sender: "compta@fournisseur.fr", subject: "Facture Mars 2026 — FV-2026-0312", verdict: "delivered" as const },
  { sender: "admin@chr0mecast.net", subject: "Mise à jour de sécurité critique", verdict: "blocked" as const },
  { sender: "claire@startup.fr", subject: "Proposition commerciale v3", verdict: "delivered" as const },
];

interface AnimatedEmail {
  id: number;
  email: typeof EMAIL_POOL[number];
  phase: "entering" | "scanning" | "routed";
}

export function EmailGatewayAnimation() {
  const [queue, setQueue] = useState<AnimatedEmail[]>([]);
  const [deliveredCount, setDeliveredCount] = useState(0);
  const [blockedCount, setBlockedCount] = useState(0);
  const [emailIndex, setEmailIndex] = useState(0);
  const [idCounter, setIdCounter] = useState(0);

  const spawnEmail = useCallback(() => {
    const email = EMAIL_POOL[emailIndex % EMAIL_POOL.length];
    const id = idCounter;

    setEmailIndex((i) => i + 1);
    setIdCounter((c) => c + 1);

    // Phase 1: entering
    setQueue((q) => [...q, { id, email, phase: "entering" }]);

    // Phase 2: scanning (after 800ms)
    setTimeout(() => {
      setQueue((q) =>
        q.map((item) => (item.id === id ? { ...item, phase: "scanning" } : item))
      );
    }, 800);

    // Phase 3: routed (after 1800ms)
    setTimeout(() => {
      setQueue((q) =>
        q.map((item) => (item.id === id ? { ...item, phase: "routed" } : item))
      );
      if (email.verdict === "delivered") {
        setDeliveredCount((c) => c + 1);
      } else {
        setBlockedCount((c) => c + 1);
      }
    }, 1800);

    // Remove from queue (after 3000ms)
    setTimeout(() => {
      setQueue((q) => q.filter((item) => item.id !== id));
    }, 3000);
  }, [emailIndex, idCounter]);

  useEffect(() => {
    // Spawn first email immediately
    const timeout = setTimeout(() => spawnEmail(), 600);
    // Then spawn every 2.2s
    const interval = setInterval(() => spawnEmail(), 2200);
    return () => {
      clearTimeout(timeout);
      clearInterval(interval);
    };
  }, [spawnEmail]);

  return (
    <div className="w-full max-w-md select-none">
      {/* Card container */}
      <div className="bg-white rounded-2xl border border-border-subtle shadow-xl shadow-on-surface/[0.06] p-5 space-y-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-safe opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-safe" />
            </span>
            <span className="text-sm font-bold text-on-surface">
              Passerelle Email Active
            </span>
          </div>
          <span className="text-[10px] font-mono text-primary bg-primary/[0.06] px-2 py-0.5 rounded-md font-bold">
            LIVE
          </span>
        </div>

        {/* Gateway visualization */}
        <div className="relative bg-surface-low/50 rounded-xl border border-border-subtle p-4 min-h-[180px]">
          {/* Three columns: Incoming → Gateway → Result */}
          <div className="grid grid-cols-[1fr_auto_1fr] gap-2 items-center h-full">
            {/* Left: Incoming emails */}
            <div className="space-y-1.5 min-h-[160px] flex flex-col justify-center">
              <span className="text-[9px] font-bold text-on-surface-variant/50 uppercase tracking-[0.12em] text-center mb-2">
                Entrants
              </span>
              <AnimatePresence mode="popLayout">
                {queue
                  .filter((e) => e.phase === "entering")
                  .slice(-2)
                  .map((item) => (
                    <MotionDiv
                      key={item.id}
                      initial={{ opacity: 0, x: -30, scale: 0.8 }}
                      animate={{ opacity: 1, x: 0, scale: 1 }}
                      exit={{ opacity: 0, x: 20, scale: 0.9 }}
                      transition={{ duration: 0.4, ease: "easeOut" }}
                      className="flex items-center gap-2 p-2 bg-white rounded-lg border border-border-subtle shadow-sm"
                    >
                      <Mail className="w-3.5 h-3.5 text-primary shrink-0" />
                      <div className="min-w-0">
                        <p className="text-[10px] font-bold text-on-surface truncate leading-tight">
                          {item.email.sender.split("@")[0]}
                        </p>
                        <p className="text-[9px] text-on-surface-variant/60 truncate leading-tight">
                          {item.email.subject.slice(0, 22)}…
                        </p>
                      </div>
                    </MotionDiv>
                  ))}
              </AnimatePresence>
            </div>

            {/* Center: Gateway shield */}
            <div className="flex flex-col items-center gap-1.5">
              <div className="relative">
                <MotionDiv
                  animate={{
                    boxShadow: queue.some((e) => e.phase === "scanning")
                      ? [
                          "0 0 0 0 rgba(0,56,164,0.15)",
                          "0 0 0 12px rgba(0,56,164,0)",
                        ]
                      : "0 0 0 0 rgba(0,56,164,0)",
                  }}
                  transition={{ duration: 0.8, repeat: Infinity }}
                  className="p-3 bg-primary rounded-xl text-on-primary"
                >
                  <ShieldCheck className="w-6 h-6" />
                </MotionDiv>
                {/* Scanning indicator */}
                <AnimatePresence>
                  {queue.some((e) => e.phase === "scanning") && (
                    <MotionDiv
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.5 }}
                      className="absolute -top-1 -right-1 w-4 h-4 bg-secondary-container rounded-full flex items-center justify-center"
                    >
                      <span className="text-[8px] font-bold text-on-secondary-container">⚡</span>
                    </MotionDiv>
                  )}
                </AnimatePresence>
              </div>
              <span className="text-[8px] font-bold text-primary uppercase tracking-[0.1em]">
                Analyse
              </span>
            </div>

            {/* Right: Sorted results */}
            <div className="space-y-1.5 min-h-[160px] flex flex-col justify-center">
              <span className="text-[9px] font-bold text-on-surface-variant/50 uppercase tracking-[0.12em] text-center mb-2">
                Résultat
              </span>
              <AnimatePresence mode="popLayout">
                {queue
                  .filter((e) => e.phase === "routed")
                  .slice(-2)
                  .map((item) => {
                    const isBlocked = item.email.verdict === "blocked";
                    return (
                      <MotionDiv
                        key={item.id}
                        initial={{ opacity: 0, x: -10, scale: 0.8 }}
                        animate={{ opacity: 1, x: 0, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.85, y: 10 }}
                        transition={{ duration: 0.35, ease: "easeOut" }}
                        className={`flex items-center gap-2 p-2 rounded-lg border shadow-sm ${
                          isBlocked
                            ? "bg-error/[0.04] border-error/15"
                            : "bg-safe/[0.04] border-safe/15"
                        }`}
                      >
                        {isBlocked ? (
                          <XCircle className="w-3.5 h-3.5 text-error shrink-0" />
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5 text-safe shrink-0" />
                        )}
                        <div className="min-w-0">
                          <p className={`text-[10px] font-bold truncate leading-tight ${
                            isBlocked ? "text-error" : "text-safe"
                          }`}>
                            {isBlocked ? "Bloqué" : "Distribué"}
                          </p>
                          <p className="text-[9px] text-on-surface-variant/60 truncate leading-tight">
                            {item.email.sender.split("@")[1]}
                          </p>
                        </div>
                      </MotionDiv>
                    );
                  })}
              </AnimatePresence>
            </div>
          </div>

          {/* Connecting lines (decorative) */}
          <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
            <div className="w-full flex items-center px-6">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-border-subtle to-primary/20" />
              <div className="w-12" />
              <div className="flex-1 h-px bg-gradient-to-r from-primary/20 via-border-subtle to-transparent" />
            </div>
          </div>
        </div>

        {/* Bottom counters */}
        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-center gap-2.5 p-3 bg-safe/[0.04] border border-safe/10 rounded-xl">
            <CheckCircle2 className="w-4.5 h-4.5 text-safe shrink-0" />
            <div>
              <p className="text-[18px] font-display font-bold text-on-surface leading-none">
                {deliveredCount}
              </p>
              <p className="text-[9px] font-bold text-safe uppercase tracking-[0.1em] mt-0.5">
                Distribués
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 p-3 bg-error/[0.04] border border-error/10 rounded-xl">
            <ShieldX className="w-4.5 h-4.5 text-error shrink-0" />
            <div>
              <p className="text-[18px] font-display font-bold text-on-surface leading-none">
                {blockedCount}
              </p>
              <p className="text-[9px] font-bold text-error uppercase tracking-[0.1em] mt-0.5">
                Bloqués
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
