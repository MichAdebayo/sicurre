import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Search } from "lucide-react";
import { Badge } from "../components/ui/badge";

const MotionDiv = motion.div as any;

interface AuditLog {
  id: string;
  timestamp: string;
  action: string;
  actor: string;
  status: "success" | "warning" | "error";
  details: string;
}

export default function LogsRoute() {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");

  const mockLogs: AuditLog[] = [
    {
      id: "1",
      timestamp: "2026-06-17T00:35:12Z",
      action: "Inférence anti-phishing",
      actor: "System / Inférence IA",
      status: "success",
      details: "E-mail de support@paypal-verification.fr classifié comme PHISHING (confidence 99.8 %)",
    },
    {
      id: "2",
      timestamp: "2026-06-17T00:35:14Z",
      action: "Remédiation automatique",
      actor: "Gmail Listener Service",
      status: "success",
      details: "E-mail de PayPal classifié comme Phishing déplacé vers la corbeille Gmail avec succès.",
    },
    {
      id: "3",
      timestamp: "2026-06-17T00:20:00Z",
      action: "Audit de Sécurité Automatique",
      actor: "System Scheduler",
      status: "warning",
      details: "Score d'intégrité de la console recalculé : 88%. Recommandation : activer le MFA matériel.",
    },
    {
      id: "4",
      timestamp: "2026-06-16T23:55:00Z",
      action: "Génération de clé API",
      actor: "admin@sicurre.fr",
      status: "success",
      details: "Clé API 'SIEM Connector' générée avec des scopes de lecture seule.",
    },
    {
      id: "5",
      timestamp: "2026-06-16T22:12:05Z",
      action: "Échec d'authentification SSO",
      actor: "unknown@sicurre.fr",
      status: "error",
      details: "Échec de l'authentification Google OAuth : Token non vérifié par l'autorité GCP.",
    },
  ];

  const filteredLogs = mockLogs.filter((log) => {
    const matchesSearch =
      log.action.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.details.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.actor.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = filterStatus === "all" || log.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

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
          Historique immuable de l'activité du pipeline et des événements d'administration
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant/30" />
          <input
            type="text"
            placeholder="Rechercher par événement, acteur..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-border-subtle rounded-lg text-[13px] text-on-surface placeholder:text-on-surface-variant/35 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all"
          />
        </div>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="px-4 py-2.5 bg-white border border-border-subtle rounded-lg text-[13px] text-on-surface-variant font-semibold focus:outline-none focus:border-primary transition-all cursor-pointer"
        >
          <option value="all">Tous les statuts</option>
          <option value="success">Réussi</option>
          <option value="warning">Avertissement</option>
          <option value="error">Erreur</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-border-subtle overflow-hidden">
        {filteredLogs.length === 0 ? (
          <div className="py-16 text-center text-on-surface-variant/50 text-sm">
            Aucun journal d'audit correspondant.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border-subtle bg-surface-low/40">
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Horodatage</th>
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Action</th>
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Acteur</th>
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Statut</th>
                  <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Détails</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {filteredLogs.map((log, idx) => (
                  <MotionDiv
                    key={log.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25, delay: idx * 0.03 }}
                    className="contents"
                  >
                    <tr className="hover:bg-surface-low/30 transition-colors text-sm">
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-[12px] text-on-surface-variant/70">
                          {new Date(log.timestamp).toLocaleString("fr-FR", {
                            day: "numeric",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 font-bold text-on-surface">{log.action}</td>
                      <td className="px-5 py-3.5 font-mono text-[12px] text-on-surface-variant/70">{log.actor}</td>
                      <td className="px-5 py-3.5">
                        <Badge variant={log.status === "success" ? "success" : log.status === "warning" ? "warning" : "critical"}>
                          {log.status === "success" ? "Réussi" : log.status === "warning" ? "Avertissement" : "Erreur"}
                        </Badge>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="text-[13px] text-on-surface-variant/70 truncate block max-w-[300px]" title={log.details}>
                          {log.details}
                        </span>
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
