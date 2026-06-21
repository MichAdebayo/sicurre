import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";

const MotionDiv = motion.div as any;

export default function LogsRoute() {
  const { t } = useTranslation();

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="pb-6 border-b border-border-subtle">
        <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
          Journaux d'Audit
        </h1>
        <p className="text-sm text-on-surface-variant mt-1">
          Cette surface admin n'est plus alimentée par des données simulées.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-border-subtle p-6 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-secondary shrink-0 mt-0.5" />
        <div className="space-y-2 text-sm text-on-surface-variant">
          <p className="font-semibold text-on-surface">Vue admin en attente de câblage backend dédié</p>
          <p>
            Les anciens journaux simulés ont été retirés pour éviter toute confusion. Cette page doit encore être reliée à un vrai flux d'audit admin distinct des données utilisateur.
          </p>
          <p>
            Pour l'instant, utilisez Threat Intel pour vérifier les événements réellement stockés par compte.
          </p>
        </div>
      </div>
    </MotionDiv>
  );
}
