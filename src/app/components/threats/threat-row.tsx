import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { ChevronDown, ChevronUp, RotateCcw, Trash2 } from "lucide-react";
import { ThreatLog } from "../../lib/api";
import { VerdictBadge } from "./verdict-badge";
import { Button } from "../ui/button";

const MotionDiv = motion.div as any;

interface ThreatRowProps {
  threat: ThreatLog;
  onUpdateStatus: (id: string, status: "trashed" | "restored") => void;
}

export function ThreatRow({ threat, onUpdateStatus }: ThreatRowProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="p-4 space-y-3 transition-colors hover:bg-slate-50/50">
      <div className="flex items-center justify-between gap-4">
        {/* Toggle details and subject title */}
        <div
          className="flex-1 cursor-pointer flex items-center gap-2.5 truncate"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
          )}
          <span className="text-sm font-medium text-slate-900 truncate hover:text-primary transition-colors">
            {threat.subject}
          </span>
        </div>

        {/* Action column */}
        <div className="flex items-center gap-4 shrink-0">
          <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
          <span className="text-xs text-slate-500 font-mono">
            {new Date(threat.received_at).toLocaleDateString("fr-FR")}
          </span>

          {threat.status === "trashed" ? (
            <Button
              variant="safe"
              onClick={() => onUpdateStatus(threat.id, "restored")}
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1" />
              <span>{t("threats.action_restore")}</span>
            </Button>
          ) : (
            <Button
              variant="danger"
              onClick={() => onUpdateStatus(threat.id, "trashed")}
            >
              <Trash2 className="w-3.5 h-3.5 mr-1" />
              <span>{t("threats.action_trash")}</span>
            </Button>
          )}
        </div>
      </div>

      {/* Expanded body preview drawer */}
      {isExpanded && (
        <MotionDiv
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="text-xs text-slate-600 bg-slate-50 rounded-lg p-3.5 border border-slate-100 leading-relaxed font-sans"
        >
          {threat.body_preview || "Aucun contenu de prévisualisation disponible."}
        </MotionDiv>
      )}
    </div>
  );
}
