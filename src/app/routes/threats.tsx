import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  Search,
  Download,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import {
  useThreatLogs,
  useUpdateThreatStatus,
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

  const [searchQuery, setSearchQuery] = useState("");
  const [filterVerdict, setFilterVerdict] = useState<string>("all");
  
  // Date range filters ("all", "today", "7d", "month")
  const [dateFilter, setDateFilter] = useState<"all" | "today" | "7d" | "month">("all");
  
  // Latency chart hover state
  const [hoveredLatencyIndex, setHoveredLatencyIndex] = useState<number | null>(null);
  
  // Table pagination state
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
          ? (i18n.language === "fr" ? "Menace mise à la corbeille." : "Threat moved to trash.")
          : (i18n.language === "fr" ? "Menace restaurée." : "Threat restored.")
      );
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to update status.");
    }
  };

  // Date filtering logic
  const matchesDateFilter = (receivedAtStr: string) => {
    if (dateFilter === "all") return true;
    const receivedTime = new Date(receivedAtStr).getTime();
    const now = new Date().getTime();
    
    if (dateFilter === "today") {
      const todayStart = new Date();
      todayStart.setHours(0, 0, 0, 0);
      return receivedTime >= todayStart.getTime();
    }
    if (dateFilter === "7d") {
      const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
      return receivedTime >= sevenDaysAgo;
    }
    if (dateFilter === "month") {
      const thisMonthStart = new Date();
      thisMonthStart.setDate(1);
      thisMonthStart.setHours(0, 0, 0, 0);
      return receivedTime >= thisMonthStart.getTime();
    }
    return true;
  };

  const filteredThreats = threats
    ? threats.filter((threat) => {
        const query = searchQuery.toLowerCase();
        const matchesSearch =
          threat.subject?.toLowerCase().includes(query) ||
          threat.sender?.toLowerCase().includes(query);
        const matchesFilter = filterVerdict === "all" || threat.verdict === filterVerdict;
        const matchesDate = matchesDateFilter(threat.received_at);
        return matchesSearch && matchesFilter && matchesDate;
      })
    : [];

  const handleExportCSV = () => {
    if (!threats || threats.length === 0) return;
    const headers = "Date,Sender,Subject,Verdict,Confidence,Status\n";
    const rows = threats
      .map(
        (t) =>
          `"${t.received_at}","${t.sender}","${t.subject}","${t.verdict}","${t.confidence}","${t.status}"`
      )
      .join("\n");
    const blob = new Blob([headers + rows], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.setAttribute("download", `sicurre_historical_report_${new Date().toISOString().slice(0,10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
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

  // SVG coordinates
  const points = latencyData.map((d, idx) => {
    const x = (idx / 6) * 1000;
    const y = 180 - (d.latency / maxLatencyVal) * 140;
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
            {i18n.language === "fr" 
              ? "Historique global des classifications d'e-mails"
              : "Global historical log of analyzed email classifications"}
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
          {/* Spacing gap increased to gap-8 between SLA and Operations legend */}
          <div className="flex items-center gap-8 text-xs font-bold text-on-surface-variant">
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

        {/* Unified Font X/Y Axis Chart */}
        <div className="w-[96%] mx-auto h-56 pt-2 relative">
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

            {/* Horizontal tracking hover sectors */}
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

          {/* Absolute Floating Tooltip Card (Rendered in-place snapping above the hovered point, no date line) */}
          {hoveredLatencyIndex !== null && (
            <div
              className="absolute z-30 p-2.5 bg-white border border-border-subtle text-on-surface rounded-xl text-[11px] shadow-xl flex flex-col gap-1 w-40 font-sans select-none pointer-events-none animate-in fade-in duration-100 -translate-x-1/2"
              style={{
                left: `${points[hoveredLatencyIndex].x / 10}%`,
                top: `${points[hoveredLatencyIndex].y - 65}px`,
              }}
            >
              <div className="flex justify-between text-on-surface-variant font-bold">
                <span>Avg Latency:</span>
                <span className="font-mono text-primary">{latencyData[hoveredLatencyIndex].latency} ms</span>
              </div>
              <div className="flex justify-between font-bold mt-0.5">
                <span>SLA Diff:</span>
                {latencyData[hoveredLatencyIndex].diffPct > 0 ? (
                  <span className="text-error">+{latencyData[hoveredLatencyIndex].diffPct}%</span>
                ) : (
                  <span className="text-safe">{latencyData[hoveredLatencyIndex].diffPct}%</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* X-axis date labels */}
        <div className="w-[96%] mx-auto flex justify-between mt-2 pt-2.5 border-t border-border-subtle/50 text-[10px] font-bold text-on-surface-variant font-sans px-1 select-none">
          {latencyData.map((d, idx) => (
            <div key={idx} className="text-center w-16 uppercase tracking-wider font-extrabold">
              {d.label}
            </div>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
          {/* Text search */}
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant/30" />
            <input
              type="text"
              placeholder={t("common.search")}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full pl-10 pr-4 py-2 bg-white border border-border-subtle rounded-lg text-sm text-on-surface placeholder:text-on-surface-variant/40 focus:outline-none focus:border-primary shadow-sm"
            />
          </div>

          {/* Date range filter dropdown */}
          <select
            value={dateFilter}
            onChange={(e) => {
              setDateFilter(e.target.value as any);
              setCurrentPage(1);
            }}
            className="px-3 py-2 bg-white border border-border-subtle rounded-lg text-sm font-semibold text-on-surface focus:outline-none focus:border-primary cursor-pointer shadow-sm"
          >
            <option value="all">{i18n.language === "fr" ? "Toutes les dates" : "All Time"}</option>
            <option value="today">{i18n.language === "fr" ? "Aujourd'hui" : "Today"}</option>
            <option value="7d">{i18n.language === "fr" ? "7 derniers jours" : "Last 7 Days"}</option>
            <option value="month">{i18n.language === "fr" ? "Ce mois" : "This Month"}</option>
          </select>
        </div>

        <div className="flex gap-2 w-full sm:w-auto">
          {(["all", "phishing", "spam", "legitimate"] as const).map((v) => (
            <button
              key={v}
              onClick={() => {
                setFilterVerdict(v);
                setCurrentPage(1);
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

      {/* Threats Table (Spans full width unconditionally) */}
      <div className="bg-white rounded-xl border border-border-subtle overflow-hidden shadow-sm">
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
                  <th className="px-5 py-3 text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-[25%] min-w-[170px]">{t("threats.timestamp")}</th>
                  <th className="px-5 py-3 text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-[30%] min-w-[180px]">{t("threats.sender")}</th>
                  <th className="px-5 py-3 text-[11px] font-extrabold text-on-surface-variant uppercase tracking-[0.12em] w-[35%] min-w-[200px]">{t("threats.subject")}</th>
                  {/* Verdict header label matches translated key */}
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
                    <tr className="hover:bg-surface-low/20 transition-all text-sm">
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-[12px] text-on-surface-variant font-bold">
                          {new Date(threat.received_at).toLocaleString(i18n.language === "fr" ? "fr-FR" : "en-US", {
                            day: "numeric",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-bold text-on-surface truncate max-w-[180px] block select-all">
                          {threat.sender || t("threats.unknown_sender")}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="text-on-surface truncate block max-w-[220px] select-all font-semibold" title={threat.subject}>
                          {threat.subject || t("threats.no_subject")}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                      </td>
                      <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="inline-flex gap-2 justify-end w-full items-center">
                          {threat.status === "trashed" ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleUpdateStatus(threat.id, "restored")}
                              className="text-[11px] gap-1.5 h-8 font-bold"
                            >
                              Restore
                            </Button>
                          ) : (
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => handleUpdateStatus(threat.id, "trashed")}
                              className="text-[11px] gap-1.5 h-8 font-bold"
                            >
                              <Trash2 className="w-3 h-3" />
                              Delete
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

        {/* Log table pagination controls */}
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
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                className="text-xs py-1 px-3.5 cursor-pointer font-bold h-8"
              >
                {i18n.language === "fr" ? "Précédent" : "Previous"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={activePage === totalPages}
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                className="text-xs py-1 px-3.5 cursor-pointer font-bold h-8"
              >
                {i18n.language === "fr" ? "Suivant" : "Next"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </MotionDiv>
  );
}
