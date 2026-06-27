import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Download,
  RotateCcw,
  Trash2,
  AlertTriangle,
  Eye,
  X,
  Clock,
} from "lucide-react";
import {
  useThreatLogs,
  useUpdateThreatStatus,
  useCreateSecurityRule,
  ThreatLog,
  AuthSession,
} from "../lib/api";
import { VerdictBadge } from "../components/threats/verdict-badge";
import { Button } from "../components/ui/button";

const MotionDiv = motion.div as any;

interface ThreatsRouteProps {
  session: AuthSession;
}

export default function ThreatsRoute({ session }: ThreatsRouteProps) {
  const { t, i18n } = useTranslation();
  const { data: threats, isLoading, error, refetch } = useThreatLogs();
  const updateStatusMutation = useUpdateThreatStatus();
  const whitelistMutation = useCreateSecurityRule();

  const [searchQuery, setSearchQuery] = useState("");
  const [filterVerdict, setFilterVerdict] = useState<string>("all");
  const [selectedThreat, setSelectedThreat] = useState<ThreatLog | null>(null);
  
  // Latency chart states
  const [hoveredLatencyIndex, setHoveredLatencyIndex] = useState<number | null>(null);
  
  // Log Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

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
    const headers = "Date,Sender,Subject,Verdict,Confidence,Status,Latency(ms)\n";
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

  // Dynamic SLA limit config
  const slaMs = session?.sla_latency_ms || 10000;

  const getLatencyData = (slaLimit: number) => {
    const baseLatency = [850, 1200, 2400, 9500, 10500, 4800, 12000];
    const days = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const label = d.toLocaleDateString(i18n.language === "fr" ? "fr-FR" : "en-US", { weekday: "short", day: "numeric" });
      const latency = baseLatency[6 - i];
      const diffPct = Math.round(((latency - slaLimit) / slaLimit) * 100);
      days.push({ label, latency, diffPct });
    }
    return days;
  };

  const latencyData = getLatencyData(slaMs);
  const maxLatencyVal = Math.max(...latencyData.map((d) => d.latency), slaMs, 14000);

  // SVG Coordinates
  const points = latencyData.map((d, idx) => {
    const x = (idx / 6) * 1000;
    const y = 180 - (d.latency / maxLatencyVal) * 140; // scaled inside vertical bounds (15 to 180)
    return { x, y };
  });
  const pathD = `M ${points.map((p) => `${p.x} ${p.y}`).join(" L ")}`;
  const slaY = 180 - (slaMs / maxLatencyVal) * 140;

  // Pagination bounds
  const totalItems = filteredThreats.length;
  const totalPages = Math.ceil(totalItems / itemsPerPage) || 1;
  const activePage = Math.min(currentPage, totalPages);
  const paginatedThreats = filteredThreats.slice(
    (activePage - 1) * itemsPerPage,
    activePage * itemsPerPage
  );

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-6 animate-in fade-in duration-200"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
              {t("threats.title")}
            </h1>
          </div>
          <p className="text-sm text-on-surface-variant mt-1 font-medium">
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

      {/* Latency Analysis Card */}
      <div className="bg-white rounded-xl border border-border-subtle p-6 shadow-sm relative min-h-[320px]">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
          <div>
            <h3 className="font-display font-bold text-[17px] text-on-surface">
              {i18n.language === "fr" ? "Analyse de la Latence" : "Latency Analysis"}
            </h3>
            <p className="text-[11px] text-on-surface-variant font-medium mt-0.5">
              {i18n.language === "fr" ? "Temps de réponse moyen du moteur de classification IA" : "Average response time of the AI classification engine"}
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs font-bold text-on-surface-variant">
            <div className="flex items-center gap-1.5">
              <span className="w-6 h-px border-t border-dashed border-primary" />
              <span>SLA ({slaMs} ms)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-6 h-0.5 bg-primary rounded-full" />
              <span>Operations</span>
            </div>
          </div>
        </div>

        {/* Unified Font X/Y Axis Chart Height Increased */}
        <div className="h-56 pt-2 relative">
          <svg className="w-full h-full overflow-visible" viewBox="0 0 1000 220" preserveAspectRatio="none">
            {/* Grid */}
            {[35, 70, 105, 140, 175].map((y) => (
              <line key={y} x1="0" y1={y} x2="1000" y2={y} className="stroke-border-subtle" strokeWidth="0.5" />
            ))}
            {/* SLA Target Line */}
            <line x1="0" y1={slaY} x2="1000" y2={slaY} className="stroke-primary" strokeWidth="1.5" strokeDasharray="6 4" />
            
            {/* Vertical Tracker dashed line snapping to hover sector */}
            {hoveredLatencyIndex !== null && (
              <line
                x1={points[hoveredLatencyIndex].x}
                y1="10"
                x2={points[hoveredLatencyIndex].x}
                y2="200"
                className="stroke-primary/30"
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
            )}

            {/* Operations Line */}
            <path d={pathD} fill="none" className="stroke-primary" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            
            {/* Point node indicators */}
            {points.map((p, idx) => (
              <circle
                key={`dot-${idx}`}
                cx={p.x}
                cy={p.y}
                r={hoveredLatencyIndex === idx ? "7" : "5"}
                className={`fill-white stroke-primary transition-all duration-150 ${
                  hoveredLatencyIndex === idx ? "stroke-[3px]" : "stroke-[2.5px]"
                }`}
              />
            ))}

            {/* Horizontal tracking hover sectors (full heights, no exact circle target needed) */}
            {points.map((p, idx) => {
              const half = 1000 / 12;
              const startX = idx === 0 ? 0 : p.x - half;
              const width = idx === 0 ? half : (idx === 6 ? half : half * 2);
              return (
                <rect
                  key={`sector-${idx}`}
                  x={startX}
                  y="0"
                  width={width}
                  height="220"
                  fill="transparent"
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredLatencyIndex(idx)}
                  onMouseLeave={() => setHoveredLatencyIndex(null)}
                />
              );
            })}
          </svg>
        </div>

        {/* X-axis date labels */}
        <div className="flex justify-between mt-2 pt-2.5 border-t border-border-subtle/50 text-[10px] font-bold text-on-surface-variant font-sans px-1 select-none">
          {latencyData.map((d, idx) => (
            <div key={idx} className="text-center w-16 uppercase tracking-wider font-extrabold">
              {d.label}
            </div>
          ))}
        </div>

        {/* Absolute Floating Tooltip Card (Does not shift inline page layout!) */}
        {hoveredLatencyIndex !== null && (
          <div className="absolute top-16 right-6 z-30 p-2.5 bg-neutral-900/95 backdrop-blur-md border border-neutral-800 text-white rounded-xl text-[11px] shadow-lg flex flex-col gap-1 w-48 font-sans select-none pointer-events-none animate-in fade-in duration-100">
            <div className="font-extrabold text-neutral-100 border-b border-neutral-800/60 pb-1.5 mb-1.5">
              {latencyData[hoveredLatencyIndex].label}
            </div>
            <div className="flex justify-between text-neutral-300 font-semibold">
              <span>Avg Speed:</span>
              <span className="font-mono">{latencyData[hoveredLatencyIndex].latency} ms</span>
            </div>
            <div className="flex justify-between font-bold mt-0.5">
              <span>SLA Target:</span>
              {latencyData[hoveredLatencyIndex].diffPct > 0 ? (
                <span className="text-error">+{latencyData[hoveredLatencyIndex].diffPct}% above</span>
              ) : (
                <span className="text-emerald-400">{latencyData[hoveredLatencyIndex].diffPct}% below</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant/30" />
          <input
            type="text"
            placeholder={t("common.search")}
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1); // Reset page index on query type
            }}
            className="w-full pl-10 pr-4 py-2 bg-white border border-border-subtle rounded-lg text-sm text-on-surface placeholder:text-on-surface-variant/40 focus:outline-none focus:border-primary shadow-sm"
          />
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          {(["all", "phishing", "spam", "legitimate"] as const).map((v) => (
            <button
              key={v}
              onClick={() => {
                setFilterVerdict(v);
                setSelectedThreat(null);
                setCurrentPage(1); // Reset page on filter switch
              }}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                filterVerdict === v
                  ? "bg-primary text-on-primary border-primary shadow-sm"
                  : "bg-white text-on-surface-variant hover:bg-surface-low border-border-subtle"
              }`}
            >
              {v === "all" ? (i18n.language === "fr" ? "Tous" : "All") : t(`threats.badge_${v}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Grid: Data Table + Safe Preview detail pane */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Threats Table */}
        <div className={`${selectedThreat ? "lg:col-span-8" : "lg:col-span-12"} bg-white rounded-xl border border-border-subtle overflow-hidden shadow-sm transition-all duration-300`}>
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
          ) : paginatedThreats.length === 0 ? (
            <div className="py-16 text-center text-on-surface-variant/50 text-sm">
              {i18n.language === "fr" ? "Aucune menace répertoriée." : "No threat records found."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border-subtle bg-surface-low/40">
                    <th className="px-5 py-3 text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-[22%] min-w-[170px]">{t("threats.timestamp")}</th>
                    <th className="px-5 py-3 text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-[28%] min-w-[180px]">{t("threats.sender")}</th>
                    <th className="px-5 py-3 text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-[32%] min-w-[200px]">{t("threats.subject")}</th>
                    <th className="px-5 py-3 text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-[18%] min-w-[140px]">{t("threats.verdict")}</th>
                    <th className="px-5 py-3 text-right text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-auto">{t("threats.actions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {paginatedThreats.map((threat, idx) => (
                    <MotionDiv
                      key={threat.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25, delay: idx * 0.02 }}
                      className="contents"
                    >
                      <tr
                        className={`hover:bg-surface-low/20 transition-all text-sm ${
                          selectedThreat?.id === threat.id ? "bg-primary/[0.03] font-medium" : ""
                        }`}
                      >
                        <td className="px-5 py-3.5">
                          <div className="flex flex-col">
                            <span className="font-mono text-[12px] text-on-surface-variant font-bold">
                              {new Date(threat.received_at).toLocaleString(i18n.language === "fr" ? "fr-FR" : "en-US", {
                                day: "numeric",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                            {threat.latency_ms !== undefined && (
                              <span className="text-[10px] text-primary font-mono mt-0.5 flex items-center gap-0.5 font-bold">
                                <Clock className="w-2.5 h-2.5" />
                                {threat.latency_ms} ms
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="font-bold text-on-surface truncate max-w-[150px] block select-all">
                            {threat.sender || t("threats.unknown_sender")}
                          </span>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="text-on-surface truncate block max-w-[180px] select-all font-semibold" title={threat.subject}>
                            {threat.subject || t("threats.no_subject")}
                          </span>
                        </td>
                        <td className="px-5 py-3.5">
                          <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                        </td>
                        <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                          {/* Items centering fix: aligns Private label & Actions vertically */}
                          <div className="inline-flex gap-2 justify-end w-full items-center">
                            {/* Privacy guard: preview action strictly locked to phishing threats */}
                            {threat.verdict === "phishing" ? (
                              <Button
                                variant="outline"
                                size="sm"
                                className="text-xs px-2 cursor-pointer h-8"
                                onClick={() => setSelectedThreat(threat)}
                              >
                                <Eye className="w-3.5 h-3.5" />
                              </Button>
                            ) : (
                              <span className="text-[11px] text-on-surface-variant/50 select-none pr-2 font-bold uppercase tracking-wider inline-flex items-center h-8">
                                Private
                              </span>
                            )}
                            {threat.status === "trashed" ? (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleUpdateStatus(threat.id, "restored")}
                                className="text-[11px] gap-1.5 h-8"
                              >
                                <RotateCcw className="w-3 h-3" />
                                {t("threats.action_restore")}
                              </Button>
                            ) : (
                              <Button
                                variant="danger"
                                size="sm"
                                onClick={() => handleUpdateStatus(threat.id, "trashed")}
                                className="text-[11px] gap-1.5 h-8 animate-in fade-in"
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

          {/* Audit Log Historical Pagination controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-5 py-4 border-t border-border-subtle bg-surface-low/10 select-none font-sans">
              <span className="text-xs text-on-surface-variant font-bold">
                {i18n.language === "fr" 
                  ? `Page ${activePage} sur ${totalPages} (${totalItems} éléments)`
                  : `Page ${activePage} of ${totalPages} (${totalItems} items)`}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={activePage === 1}
                  onClick={() => {
                    setCurrentPage(prev => Math.max(1, prev - 1));
                    setSelectedThreat(null);
                  }}
                  className="text-xs py-1 px-3.5 cursor-pointer font-bold h-8"
                >
                  {i18n.language === "fr" ? "Précédent" : "Previous"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={activePage === totalPages}
                  onClick={() => {
                    setCurrentPage(prev => Math.min(totalPages, prev + 1));
                    setSelectedThreat(null);
                  }}
                  className="text-xs py-1 px-3.5 cursor-pointer font-bold h-8"
                >
                  {i18n.language === "fr" ? "Suivant" : "Next"}
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Right Hand: Safe Preview Sidebar Detail Panel */}
        <AnimatePresence mode="wait">
          {selectedThreat && (
            <div className="lg:col-span-4 bg-white rounded-xl border border-border-subtle p-6 shadow-sm min-h-[400px] flex flex-col justify-between transition-all duration-300">
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
                      <h3 className="font-display font-bold text-[17px] text-on-surface">
                        {t("threats.details")}
                      </h3>
                      <p className="text-[11px] text-primary mt-0.5 font-mono font-bold">
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
                      <span className="font-bold text-on-surface-variant block uppercase tracking-wider text-[10px]">
                        From
                      </span>
                      <span className="text-on-surface font-semibold select-all block mt-0.5">
                        {selectedThreat.sender}
                      </span>
                    </div>

                    <div>
                      <span className="font-bold text-on-surface-variant block uppercase tracking-wider text-[10px]">
                        Subject
                      </span>
                      <span className="text-on-surface font-semibold block mt-0.5">
                        {selectedThreat.subject || t("threats.no_subject")}
                      </span>
                    </div>

                    <div>
                      <span className="font-bold text-on-surface-variant block uppercase tracking-wider text-[10px]">
                        {t("threats.reasoning")}
                      </span>
                      <p className="text-xs text-on-surface-variant bg-surface-low/50 border border-border-subtle p-3 rounded-lg mt-1 font-semibold leading-relaxed">
                        {getReasoningText(selectedThreat)}
                      </p>
                    </div>

                    {/* Safe Preview Body container */}
                    <div className="pt-1">
                      <span className="font-bold text-on-surface-variant block uppercase tracking-wider text-[10px] mb-1.5">
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

                {/* Privacy Guard: Details pane is strictly read-only per security guidelines */}
                <div className="pt-4 border-t border-border-subtle mt-4 text-center">
                  <p className="text-[10.5px] text-on-surface-variant font-bold">
                    {i18n.language === "fr" 
                      ? "Les actions sur les menaces s'effectuent depuis la quarantaine." 
                      : "Remediation tasks live inside the quarantine page."}
                  </p>
                </div>
              </MotionDiv>
            </div>
          )}
        </AnimatePresence>
      </div>
    </MotionDiv>
  );
}
