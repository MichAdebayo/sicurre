import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, RotateCcw, Trash2 } from "lucide-react";
import { ThreatLog } from "../../lib/api";
import { VerdictBadge } from "./verdict-badge";
import { Button } from "../ui/button";
import { clsx } from "clsx";

const MotionDiv = motion.div as any;

interface ThreatRowProps {
  threat: ThreatLog;
  onUpdateStatus: (id: string, status: "trashed" | "restored") => void;
}

export function ThreatRow({ threat, onUpdateStatus }: ThreatRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={clsx(
        "border-b border-border-subtle bg-surface-lowest transition-colors",
        threat.verdict === "phishing" && "hover:bg-error/5",
        threat.verdict === "spam" && "hover:bg-warning-bg/50",
        threat.verdict === "legitimate" && "hover:bg-safe-bg/50",
      )}
    >
      <div className="flex items-center justify-between gap-4 p-4">
        {/* Subject Header */}
        <div
          className="flex-1 cursor-pointer flex items-center gap-3 min-w-0"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="text-on-surface-variant/50 shrink-0">
            {isExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-body-md font-bold text-on-surface truncate hover:text-primary transition-colors">
              {threat.subject || "(Aucun objet)"}
            </span>
            <span className="text-body-sm text-on-surface-variant/70 truncate">
              expediteur@sicurre-logs.fr
            </span>
          </div>
        </div>

        {/* Info Column */}
        <div className="flex items-center gap-5 shrink-0">
          <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
          
          <span className="text-mono-data text-xs text-on-surface-variant/70">
            {new Date(threat.received_at).toLocaleDateString("fr-FR", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>

          {threat.status === "trashed" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onUpdateStatus(threat.id, "restored");
              }}
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1" />
              <span>Restaurer</span>
            </Button>
          ) : (
            <Button
              variant="danger"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onUpdateStatus(threat.id, "trashed");
              }}
            >
              <Trash2 className="w-3.5 h-3.5 mr-1" />
              <span>Mettre en quarantaine</span>
            </Button>
          )}
        </div>
      </div>

      {/* Expanded body preview drawer */}
      <AnimatePresence initial={false}>
        {isExpanded && (
          <MotionDiv
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden bg-surface-low border-t border-border-subtle/50"
          >
            <div className="p-4 text-body-sm text-on-surface-variant/90 leading-relaxed max-w-3xl whitespace-pre-wrap">
              {threat.body_preview || "Aucun aperçu du contenu de l'e-mail disponible."}
            </div>
            {/* Which model produced this verdict. Absent when a blocklist rule
                decided without consulting the model, and for events recorded
                before the identity was captured - shown as such rather than
                blank, so the distinction stays legible. */}
            <div className="px-4 pb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-mono-data text-xs text-on-surface-variant/70">
              <span>
                Modèle&nbsp;:{" "}
                {threat.model_version ? (
                  <span className="text-on-surface">{threat.model_version}</span>
                ) : (
                  <span className="italic">non enregistré</span>
                )}
              </span>
              {threat.model_revision ? (
                <span title={threat.model_revision}>
                  Révision&nbsp;:{" "}
                  <span className="text-on-surface">
                    {threat.model_revision.slice(0, 12)}
                  </span>
                </span>
              ) : null}
              {threat.latency_ms ? <span>Latence&nbsp;: {Math.round(threat.latency_ms)}&nbsp;ms</span> : null}
            </div>
          </MotionDiv>
        )}
      </AnimatePresence>
    </div>
  );
}
