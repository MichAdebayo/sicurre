import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  Search,
  Download,
  Activity,
  RotateCcw,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { useThreatLogs, useUpdateThreatStatus, ThreatLog } from "../lib/api";
import { VerdictBadge } from "../components/threats/verdict-badge";
import { Button } from "../components/ui/button";

const MotionDiv = motion.div as any;

export default function ThreatsRoute() {
  const { t } = useTranslation();
  const { data: threats, isLoading, error } = useThreatLogs();
  const updateStatusMutation = useUpdateThreatStatus();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterVerdict, setFilterVerdict] = useState<string>("all");

  const handleUpdateStatus = (id: string, newStatus: "trashed" | "restored") => {
    updateStatusMutation.mutate({ id, status: newStatus });
  };

  const filteredThreats = threats
    ? threats.filter((threat) => {
        const query = searchQuery.toLowerCase();
        const matchesSearch =
          threat.subject?.toLowerCase().includes(query) ||
          threat.sender?.toLowerCase().includes(query);
        const matchesFilter = filterVerdict === "all" || threat.verdict === filterVerdict;
        return matchesSearch && matchesFilter;
      })
    : [];

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
              Flux de Menaces en Direct
            </h1>
            <span className="inline-flex items-center gap-1.5 bg-primary/[0.06] border border-primary/10 text-primary text-[9px] font-bold px-2.5 py-1 rounded-full uppercase tracking-[0.12em]">
              <Activity className="w-3 h-3 animate-pulse" />
              5 Nœuds Actifs
            </span>
          </div>
          <p className="text-sm text-on-surface-variant mt-1">
            Analyse et classification des e-mails entrants en temps réel
          </p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-white hover:bg-surface-low border border-border-subtle text-[13px] font-semibold rounded-lg transition-colors cursor-pointer self-start sm:self-center shadow-sm">
          <Download className="w-4 h-4 text-on-surface-variant" />
          <span>Exporter le Rapport</span>
        </button>
      </div>

      {/* Chart Card */}
      <div className="bg-white rounded-xl border border-border-subtle p-6">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
          <div>
            <h3 className="font-display font-semibold text-[17px] text-on-surface">
              Tentatives de Brèche (24h)
            </h3>
            <p className="text-[12px] text-on-surface-variant/60 mt-0.5">
              Latence d'analyse et phishing intercepté
            </p>
          </div>
          <div className="flex items-center gap-4 text-[11px] font-semibold text-on-surface-variant/70">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-error" />
              <span>Critique</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-secondary" />
              <span>Avertissement</span>
            </div>
          </div>
        </div>
        <div className="h-48 pt-2">
          <svg className="w-full h-full" viewBox="0 0 1000 180" preserveAspectRatio="none">
            {/* Grid */}
            {[36, 72, 108, 144].map((y) => (
              <line key={y} x1="0" y1={y} x2="1000" y2={y} className="stroke-border-subtle" strokeWidth="0.5" />
            ))}
            {/* Area fills */}
            <path d="M 0 160 Q 150 40 300 130 T 600 70 T 900 150 T 1000 120 L 1000 180 L 0 180 Z" fill="rgba(186,26,26,0.04)" />
            <path d="M 0 120 Q 200 150 400 60 T 800 110 T 1000 50 L 1000 180 L 0 180 Z" fill="rgba(133,83,0,0.03)" />
            {/* Lines */}
            <path d="M 0 160 Q 150 40 300 130 T 600 70 T 900 150 T 1000 120" fill="none" className="stroke-error" strokeWidth="2" strokeLinecap="round" />
            <path d="M 0 120 Q 200 150 400 60 T 800 110 T 1000 50" fill="none" className="stroke-secondary" strokeWidth="2" strokeLinecap="round" strokeDasharray="6 4" />
          </svg>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant/30" />
          <input
            type="text"
            placeholder="Rechercher par objet, expéditeur..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-border-subtle rounded-lg text-[13px] text-on-surface placeholder:text-on-surface-variant/35 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all"
          />
        </div>
        <select
          value={filterVerdict}
          onChange={(e) => setFilterVerdict(e.target.value)}
          className="px-4 py-2.5 bg-white border border-border-subtle rounded-lg text-[13px] text-on-surface-variant font-semibold focus:outline-none focus:border-primary transition-all cursor-pointer"
        >
          <option value="all">Tous les verdicts</option>
          <option value="phishing">Phishing</option>
          <option value="spam">Spam</option>
          <option value="legitimate">Légitimes</option>
        </select>
      </div>

      {/* Data Table */}
      <div className="bg-white rounded-xl border border-border-subtle overflow-hidden">
        {isLoading ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-14 bg-surface-low rounded-xl animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="py-16 text-center flex flex-col items-center justify-center">
            <AlertTriangle className="w-10 h-10 text-error/40 mb-3" />
            <p className="font-semibold text-sm text-on-surface">Erreur de chargement du flux</p>
            <p className="text-[12px] text-on-surface-variant/60 mt-1">Impossible de contacter le module backend.</p>
          </div>
        ) : filteredThreats.length === 0 ? (
          <div className="py-16 text-center text-on-surface-variant/50 text-sm">
            Aucune menace détectée — votre boîte est protégée 🎉
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border-subtle bg-surface-low/40">
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Horodatage</th>
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Expéditeur</th>
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Sujet</th>
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Verdict</th>
                  <th className="px-5 py-3 text-right text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {filteredThreats.map((threat, idx) => (
                  <MotionDiv
                    key={threat.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25, delay: idx * 0.03 }}
                    className="contents"
                  >
                    <tr className="hover:bg-surface-low/30 transition-colors text-sm">
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-[12px] text-on-surface-variant/70">
                          {new Date(threat.received_at).toLocaleString("fr-FR", {
                            day: "numeric",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex flex-col">
                          <span className="font-semibold text-on-surface truncate max-w-[220px]">
                            {threat.sender || "Expéditeur inconnu"}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="text-on-surface truncate block max-w-[220px] font-medium" title={threat.subject}>
                          {threat.subject || "(Aucun objet)"}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        {threat.status === "trashed" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleUpdateStatus(threat.id, "restored")}
                            className="text-[12px] gap-1.5"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            Restaurer
                          </Button>
                        ) : (
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => handleUpdateStatus(threat.id, "trashed")}
                            className="text-[12px] gap-1.5"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            Supprimer
                          </Button>
                        )}
                      </td>
                    </tr>
                  </MotionDiv>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </MotionDiv>
  );
}
