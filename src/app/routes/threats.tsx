import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Download,
  Activity,
  RotateCcw,
  Trash2,
  AlertTriangle,
  Eye,
  Check,
  X,
  ShieldCheck,
  Clock,
} from "lucide-react";
import {
  useThreatLogs,
  useUpdateThreatStatus,
  useCreateSecurityRule,
  ThreatLog,
} from "../lib/api";
import { VerdictBadge } from "../components/threats/verdict-badge";
import { Button } from "../components/ui/button";

const MotionDiv = motion.div as any;

export default function ThreatsRoute() {
  const { t, i18n } = useTranslation();
  const { data: threats, isLoading, error, refetch } = useThreatLogs();
  const updateStatusMutation = useUpdateThreatStatus();
  const whitelistMutation = useCreateSecurityRule();

  const [searchQuery, setSearchQuery] = useState("");
  const [filterVerdict, setFilterVerdict] = useState<string>("all");
  const [selectedThreat, setSelectedThreat] = useState<ThreatLog | null>(null);

  const [actionSuccess, setActionSuccess] = useState("");
  const [actionError, setActionError] = useState("");

  const handleUpdateStatus = async (id: string, newStatus: "trashed" | "restored") => {
    setActionSuccess("");
    setActionError("");
    try {
      await updateStatusMutation.mutateAsync({ id, status: newStatus });
      setActionSuccess(
        newStatus === "trashed"
          ? (i18n.language === "fr" ? "Menace confirmée et mise à la corbeille." : "Threat confirmed and trashed.")
          : (i18n.language === "fr" ? "Email restauré avec succès." : "Email restored successfully.")
      );
      if (selectedThreat?.id === id) {
        setSelectedThreat(prev => prev ? { ...prev, status: newStatus } : null);
      }
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to update threat status.");
    }
  };

  const handleMarkAsSafe = async (threat: ThreatLog) => {
    setActionSuccess("");
    setActionError("");
    try {
      // 1. Restore email in inbox
      await updateStatusMutation.mutateAsync({ id: threat.id, status: "restored" });
      // 2. Whitelist the sender address
      if (threat.sender) {
        await whitelistMutation.mutateAsync({
          rule_type: "whitelist",
          pattern: threat.sender.trim(),
        });
        setActionSuccess(
          i18n.language === "fr"
            ? `Email marqué comme sain et expéditeur (${threat.sender}) ajouté à la liste blanche.`
            : `Email marked as safe and sender (${threat.sender}) added to whitelist.`
        );
      } else {
        setActionSuccess(
          i18n.language === "fr" ? "Email restauré avec succès." : "Email restored successfully."
        );
      }
      setSelectedThreat(null);
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to whitelist sender.");
    }
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

  const handleExportCSV = () => {
    if (!threats || threats.length === 0) return;
    const headers = "Timestamp,Sender,Subject,Verdict,Confidence,Status,Latency(ms)\n";
    const rows = threats
      .map(
        (t) =>
          `"${t.received_at}","${t.sender}","${t.subject}","${t.verdict}","${t.confidence}","${t.status}","${t.latency_ms || 0}"`
      )
      .join("\n");
    const blob = new Blob([headers + rows], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.setAttribute("download", `sicurre_threat_report_${new Date().toISOString().slice(0,10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const renderSafeHtml = (rawText: string) => {
    const escaped = rawText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
    return escaped.replace(/\n/g, "<br />");
  };

  const getReasoningText = (threat: ThreatLog) => {
    if (threat.explanation) return threat.explanation;
    if (threat.verdict === "phishing") return t("threats.explain_phishing");
    if (threat.verdict === "spam") return t("threats.explain_spam");
    return t("threats.explain_legitimate");
  };

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
              {t("threats.title")}
            </h1>
            <span className="inline-flex items-center gap-1.5 bg-primary/[0.06] border border-primary/10 text-primary text-[9px] font-bold px-2.5 py-1 rounded-full uppercase tracking-[0.12em]">
              <Activity className="w-3 h-3 animate-pulse" />
              {t("threats.live_nodes")}
            </span>
          </div>
          <p className="text-sm text-on-surface-variant mt-1">
            {t("threats.subtitle")}
          </p>
        </div>
        <button
          onClick={handleExportCSV}
          className="flex items-center gap-2 px-4 py-2 bg-white hover:bg-surface-low border border-border-subtle text-[13px] font-semibold rounded-lg transition-colors cursor-pointer self-start sm:self-center shadow-sm"
        >
          <Download className="w-4 h-4 text-on-surface-variant" />
          <span>{t("threats.export_report")}</span>
        </button>
      </div>

      {actionSuccess && (
        <div className="p-3 bg-safe/10 border border-safe/25 text-safe text-xs font-semibold rounded-lg">
          {actionSuccess}
        </div>
      )}
      {actionError && (
        <div className="p-3 bg-error/10 border border-error/25 text-error text-xs font-semibold rounded-lg">
          {actionError}
        </div>
      )}

      {/* Chart Card */}
      <div className="bg-white rounded-xl border border-border-subtle p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
          <div>
            <h3 className="font-display font-semibold text-[17px] text-on-surface">
              {t("threats.breach_attempts")}
            </h3>
            <p className="text-[12px] text-on-surface-variant/60 mt-0.5">
              {t("threats.analysis_latency")}
            </p>
          </div>
          <div className="flex items-center gap-4 text-[11px] font-semibold text-on-surface-variant/70">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-error" />
              <span>{t("threats.critical")}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-secondary" />
              <span>{t("threats.warning")}</span>
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
            placeholder={t("threats.search_placeholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-border-subtle rounded-lg text-[13px] text-on-surface placeholder:text-on-surface-variant/35 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all shadow-sm"
          />
        </div>
        <select
          value={filterVerdict}
          onChange={(e) => setFilterVerdict(e.target.value)}
          className="px-4 py-2.5 bg-white border border-border-subtle rounded-lg text-[13px] text-on-surface-variant font-semibold focus:outline-none focus:border-primary transition-all cursor-pointer shadow-sm"
        >
          <option value="all">{t("threats.all_verdicts")}</option>
          <option value="phishing">{t("threats.phishing")}</option>
          <option value="spam">{t("threats.spam")}</option>
          <option value="legitimate">{t("threats.legitimate")}</option>
        </select>
      </div>

      {/* Grid: Data Table + Safe Preview detail pane */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Threats Table */}
        <div className="lg:col-span-8 bg-white rounded-xl border border-border-subtle overflow-hidden shadow-sm">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-14 bg-surface-low rounded-xl animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="py-16 text-center flex flex-col items-center justify-center">
              <AlertTriangle className="w-10 h-10 text-error/40 mb-3" />
              <p className="font-semibold text-sm text-on-surface">{t("common.error_occurred")}</p>
            </div>
          ) : filteredThreats.length === 0 ? (
            <div className="py-16 text-center text-on-surface-variant/50 text-sm">
              {i18n.language === "fr" ? "Aucune menace répertoriée." : "No threat records found."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border-subtle bg-surface-low/40">
                    <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("threats.timestamp")}</th>
                    <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("threats.sender")}</th>
                    <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("threats.subject")}</th>
                    <th className="px-5 py-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("threats.verdict")}</th>
                    <th className="px-5 py-3 text-right text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("threats.actions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {filteredThreats.map((threat, idx) => (
                    <MotionDiv
                      key={threat.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25, delay: idx * 0.02 }}
                      className="contents"
                    >
                      <tr
                        onClick={() => setSelectedThreat(threat)}
                        className={`hover:bg-surface-low/20 transition-all cursor-pointer text-sm ${
                          selectedThreat?.id === threat.id ? "bg-primary/[0.03] font-medium" : ""
                        }`}
                      >
                        <td className="px-5 py-3.5">
                          <div className="flex flex-col">
                            <span className="font-mono text-[12px] text-on-surface-variant/80">
                              {new Date(threat.received_at).toLocaleString(i18n.language === "fr" ? "fr-FR" : "en-US", {
                                day: "numeric",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                            {threat.latency_ms !== undefined && (
                              <span className="text-[10px] text-primary/70 font-mono mt-0.5 flex items-center gap-0.5">
                                <Clock className="w-2.5 h-2.5" />
                                {threat.latency_ms} ms
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="font-semibold text-on-surface truncate max-w-[150px] block select-none">
                            {threat.sender || t("threats.unknown_sender")}
                          </span>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="text-on-surface truncate block max-w-[180px] select-none" title={threat.subject}>
                            {threat.subject || t("threats.no_subject")}
                          </span>
                        </td>
                        <td className="px-5 py-3.5">
                          <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                        </td>
                        <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="inline-flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-xs px-2"
                              onClick={() => setSelectedThreat(threat)}
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </Button>
                            {threat.status === "trashed" ? (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleUpdateStatus(threat.id, "restored")}
                                className="text-[11px] gap-1.5"
                              >
                                <RotateCcw className="w-3 h-3" />
                                {t("threats.action_restore")}
                              </Button>
                            ) : (
                              <Button
                                variant="danger"
                                size="sm"
                                onClick={() => handleUpdateStatus(threat.id, "trashed")}
                                className="text-[11px] gap-1.5"
                              >
                                <Trash2 className="w-3 h-3" />
                                {t("threats.action_trash").replace("Mettre à la", "").replace("Move to", "").trim()}
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    </MotionDiv>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right Hand: Safe Preview Sidebar Detail Panel */}
        <div className="lg:col-span-4 bg-white rounded-xl border border-border-subtle p-6 shadow-sm min-h-[400px] flex flex-col justify-between">
          <AnimatePresence mode="wait">
            {selectedThreat ? (
              <MotionDiv
                key={selectedThreat.id}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                className="space-y-6 flex-1 flex flex-col justify-between"
              >
                <div>
                  <div className="flex justify-between items-start border-b border-border-subtle pb-4">
                    <div>
                      <h3 className="font-display font-semibold text-[17px] text-on-surface">
                        {t("threats.details")}
                      </h3>
                      <p className="text-[11px] text-on-surface-variant/60 mt-0.5 font-mono">
                        Speed: {selectedThreat.latency_ms || 0} ms
                      </p>
                    </div>
                    <button
                      onClick={() => setSelectedThreat(null)}
                      className="p-1 rounded-md hover:bg-surface-low transition-colors cursor-pointer"
                    >
                      <X className="w-4 h-4 text-on-surface-variant" />
                    </button>
                  </div>

                  <div className="space-y-3.5 pt-4 text-xs">
                    <div>
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px]">
                        From
                      </span>
                      <span className="text-on-surface font-semibold select-all block mt-0.5">
                        {selectedThreat.sender}
                      </span>
                    </div>

                    <div>
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px]">
                        Subject
                      </span>
                      <span className="text-on-surface font-semibold block mt-0.5">
                        {selectedThreat.subject || t("threats.no_subject")}
                      </span>
                    </div>

                    <div>
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px]">
                        {t("threats.reasoning")}
                      </span>
                      <p className="text-xs text-on-surface-variant bg-surface-low/50 border border-border-subtle p-3 rounded-lg mt-1 font-semibold leading-relaxed">
                        {getReasoningText(selectedThreat)}
                      </p>
                    </div>

                    {/* Safe Preview Body container */}
                    <div className="pt-1">
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px] mb-1.5">
                        {t("threats.safe_preview")}
                      </span>
                      <iframe
                        title="Threat Safe Preview Frame"
                        srcDoc={`<!DOCTYPE html><html><head><style>body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #374151; font-size: 12px; line-height: 1.6; margin: 10px; word-break: break-word; } a { color: #2563eb; pointer-events: none !important; text-decoration: underline; } img { display: none !important; }</style></head><body>${renderSafeHtml(selectedThreat.body_preview || "")}</body></html>`}
                        sandbox=""
                        className="w-full h-[200px] bg-surface-low border border-border-subtle rounded-xl select-text"
                      />
                    </div>
                  </div>
                </div>

                {/* Actions drawer */}
                <div className="space-y-2 pt-4 border-t border-border-subtle mt-4">
                  {selectedThreat.status !== "restored" && (
                    <Button
                      variant="outline"
                      className="w-full gap-2 text-xs py-2.5 border-safe/30 text-safe hover:bg-safe/5 font-bold uppercase tracking-wider"
                      onClick={() => handleMarkAsSafe(selectedThreat)}
                    >
                      <ShieldCheck className="w-4 h-4 text-safe" />
                      {t("threats.mark_safe")}
                    </Button>
                  )}

                  {selectedThreat.status !== "trashed" && (
                    <Button
                      variant="danger"
                      className="w-full gap-2 text-xs py-2.5 uppercase font-bold tracking-wider"
                      onClick={() => handleUpdateStatus(selectedThreat.id, "trashed")}
                    >
                      <Trash2 className="w-4 h-4" />
                      {t("threats.confirm_threat")}
                    </Button>
                  )}
                </div>
              </MotionDiv>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center text-on-surface-variant/40 py-12">
                <Eye className="w-10 h-10 mb-2 stroke-[1.5]" />
                <p className="text-sm font-semibold">Select an Email to Preview</p>
                <p className="text-xs max-w-[200px] mt-1">
                  View plain-language classification logs and inspect email bodies safely.
                </p>
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </MotionDiv>
  );
}
