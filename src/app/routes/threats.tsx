import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  Search,
  Download,
  Trash2,
  RotateCcw,
  Flag,
  AlertTriangle,
} from "lucide-react";
import {
  useThreatLogs,
  useUpdateThreatStatus,
  useCreateFeedback,
  AuthSession,
} from "../lib/api";
import { VerdictBadge } from "../components/threats/verdict-badge";
import { Button } from "../components/ui/button";
import { AppToast } from "../components/common/app-toast";

const MotionDiv = motion.div as any;

interface ThreatsRouteProps {
  session: AuthSession;
}

export default function ThreatsRoute({ session }: ThreatsRouteProps) {
  const { t, i18n } = useTranslation();
  const { data: threats, isLoading, error, refetch } = useThreatLogs();
  const updateStatusMutation = useUpdateThreatStatus();
  const feedbackMutation = useCreateFeedback();

  const [searchQuery, setSearchQuery] = useState("");
  const [filterVerdict, setFilterVerdict] = useState<string>("all");
  
  // Date range filters ("all", "today", "7d", "month")
  const [dateFilter, setDateFilter] = useState<"today" | "7d" | "month" | "last_month">("7d");
  
  // Latency chart hover state
  const [hoveredLatencyIndex, setHoveredLatencyIndex] = useState<number | null>(null);
  
  // Table pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const [actionSuccess, setActionSuccess] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (!actionSuccess) return;
    const t = setTimeout(() => setActionSuccess(""), 4000);
    return () => clearTimeout(t);
  }, [actionSuccess]);

  useEffect(() => {
    if (!actionError) return;
    const t = setTimeout(() => setActionError(""), 4000);
    return () => clearTimeout(t);
  }, [actionError]);

  const handleUpdateStatus = async (id: string, newStatus: "trashed" | "restored") => {
    setActionSuccess("");
    setActionError("");
    try {
      await updateStatusMutation.mutateAsync({ id, status: newStatus });
      setActionSuccess(
        newStatus === "trashed"
          ? (i18n.language === "fr" ? "Menace mise en quarantaine." : "Threat quarantined.")
          : (i18n.language === "fr" ? "Menace restaurée." : "Threat restored.")
      );
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to update status.");
    }
  };

  const handleReportFalseNegative = async (id: string) => {
    setActionSuccess("");
    setActionError("");
    try {
      await feedbackMutation.mutateAsync({
        event_id: id,
        feedback_type: "false_negative",
        corrected_verdict: "phishing",
        reporter_note:
          i18n.language === "fr"
            ? "Signalé depuis le journal des menaces comme phishing non intercepté."
            : "Reported from threat log as missed phishing.",
      });
      setActionSuccess(
        i18n.language === "fr"
          ? "Signalement reçu. Nous l'utiliserons pour améliorer la détection."
          : "Report received. We will use it to improve detection."
      );
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to submit feedback.");
    }
  };

  // Date filtering logic
  const matchesDateFilter = (receivedAtStr: string) => {
    const received = new Date(receivedAtStr);
    const now = new Date();

    if (dateFilter === "today") {
      const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
      return received >= start;
    }
    if (dateFilter === "7d") {
      const start = new Date();
      start.setDate(now.getDate() - 7);
      return received >= start;
    }
    if (dateFilter === "month") {
      const start = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0);
      return received >= start;
    }
    if (dateFilter === "last_month") {
      const start = new Date(now.getFullYear(), now.getMonth() - 1, 1, 0, 0, 0, 0);
      const end = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59, 999);
      return received >= start && received <= end;
    }
    return true;
  };

  const filteredThreats = threats
    ? threats.filter((threat) => {
        const query = searchQuery.toLowerCase();
        const matchesSearch =
          threat.subject?.toLowerCase().includes(query) ||
          threat.sender?.toLowerCase().includes(query);
        const matchesFilter =
          filterVerdict === "all" ||
          threat.verdict === filterVerdict ||
          (filterVerdict === "phishing" && threat.verdict === "quarantine");
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
    const threatsList = threats || [];
    const days = [];
    const now = new Date();
    
    if (dateFilter === "today") {
      // 24 hourly points (from 23 hours ago to current hour)
      for (let i = 23; i >= 0; i--) {
        const d = new Date();
        d.setHours(d.getHours() - i, 0, 0, 0);
        const label = d.toLocaleTimeString(i18n.language === "fr" ? "fr-FR" : "en-US", { hour: "2-digit", minute: "2-digit" });
        
        const startOfHour = d;
        const endOfHour = new Date(d.getTime() + 59 * 60 * 1000 + 59 * 1000 + 999);

        const hourlyThreats = threatsList.filter((t) => {
          const rDate = new Date(t.received_at);
          return rDate >= startOfHour && rDate <= endOfHour;
        });

        const emails_count = hourlyThreats.length;
        const latency = emails_count > 0
          ? Math.round(hourlyThreats.reduce((sum, t) => sum + (t.latency_ms || 0), 0) / emails_count)
          : 0;

        const diffPct = latency > 0 ? Math.round(((latency - slaLimit) / slaLimit) * 100) : 0;
        days.push({ label, latency, diffPct, emails_count });
      }
    } else if (dateFilter === "7d") {
      for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const label = d.toLocaleDateString(i18n.language === "fr" ? "fr-FR" : "en-US", { weekday: "short", day: "numeric" });
        
        const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
        const endOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

        const dailyThreats = threatsList.filter((t) => {
          const rDate = new Date(t.received_at);
          return rDate >= startOfDay && rDate <= endOfDay;
        });

        const emails_count = dailyThreats.length;
        const latency = emails_count > 0
          ? Math.round(dailyThreats.reduce((sum, t) => sum + (t.latency_ms || 0), 0) / emails_count)
          : 0;

        const diffPct = latency > 0 ? Math.round(((latency - slaLimit) / slaLimit) * 100) : 0;
        days.push({ label, latency, diffPct, emails_count });
      }
    } else if (dateFilter === "month") {
      const currentDay = now.getDate();
      for (let i = currentDay - 1; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const label = d.toLocaleDateString(i18n.language === "fr" ? "fr-FR" : "en-US", { month: "short", day: "numeric" });
        
        const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
        const endOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

        const dailyThreats = threatsList.filter((t) => {
          const rDate = new Date(t.received_at);
          return rDate >= startOfDay && rDate <= endOfDay;
        });

        const emails_count = dailyThreats.length;
        const latency = emails_count > 0
          ? Math.round(dailyThreats.reduce((sum, t) => sum + (t.latency_ms || 0), 0) / emails_count)
          : 0;

        const diffPct = latency > 0 ? Math.round(((latency - slaLimit) / slaLimit) * 100) : 0;
        days.push({ label, latency, diffPct, emails_count });
      }
    } else {
      // last_month
      const y = now.getFullYear();
      const m = now.getMonth();
      const daysInPrevMonth = new Date(y, m, 0).getDate();
      for (let i = daysInPrevMonth - 1; i >= 0; i--) {
        const d = new Date(y, m - 1, daysInPrevMonth - i);
        const label = d.toLocaleDateString(i18n.language === "fr" ? "fr-FR" : "en-US", { month: "short", day: "numeric" });
        
        const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
        const endOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

        const dailyThreats = threatsList.filter((t) => {
          const rDate = new Date(t.received_at);
          return rDate >= startOfDay && rDate <= endOfDay;
        });

        const emails_count = dailyThreats.length;
        const latency = emails_count > 0
          ? Math.round(dailyThreats.reduce((sum, t) => sum + (t.latency_ms || 0), 0) / emails_count)
          : 0;

        const diffPct = latency > 0 ? Math.round(((latency - slaLimit) / slaLimit) * 100) : 0;
        days.push({ label, latency, diffPct, emails_count });
      }
    }
    return days;
  };

  const latencyData = getLatencyData(slaMs);
  const maxLatencyVal = Math.max(...latencyData.map((d) => d.latency), slaMs, 14000);

  // SVG coordinates
  const points = latencyData.map((d, idx) => {
    const x = (idx / (latencyData.length - 1 || 1)) * 1000;
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
      <AppToast
        tone="success"
        message={actionSuccess}
        visible={!!actionSuccess}
        onClose={() => setActionSuccess("")}
      />
      <AppToast
        tone="error"
        message={actionError}
        visible={!!actionError}
        onClose={() => setActionError("")}
      />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="app-h1">
              {t("threats.title")}
            </h1>
          </div>
          <p className="app-body-sub mt-1">
            {i18n.language === "fr" 
              ? "Historique global des classifications d'e-mails"
              : "Global historical log of analyzed email classifications"}
          </p>
        </div>
        <div className="flex items-center gap-3 self-start sm:self-center">
          {/* Date range filter dropdown */}
          <select
            value={dateFilter}
            onChange={(e) => {
              setDateFilter(e.target.value as any);
              setCurrentPage(1);
            }}
            className="px-3 py-2 bg-white border border-border-subtle rounded-lg text-xs font-bold text-on-surface focus:outline-none focus:border-primary cursor-pointer shadow-sm h-9"
          >
            <option value="today">{i18n.language === "fr" ? "Aujourd'hui" : "Today"}</option>
            <option value="7d">{i18n.language === "fr" ? "7 derniers jours" : "Last 7 Days"}</option>
            <option value="month">{i18n.language === "fr" ? "Ce mois-ci" : "This Month"}</option>
            <option value="last_month">{i18n.language === "fr" ? "Le mois dernier" : "Last Month"}</option>
          </select>

          <button
            onClick={handleExportCSV}
            className="flex items-center gap-2 px-4 py-2 bg-white hover:bg-surface-low border border-border-subtle text-[13px] font-semibold rounded-lg transition-colors cursor-pointer shadow-sm h-9"
          >
            <Download className="w-4 h-4 text-on-surface-variant" />
            <span>{t("threats.export_report")}</span>
          </button>
        </div>
      </div>

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
          {/* Spacing gap set to gap-8 between SLA and Operations legend */}
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

          {/* Absolute Floating Tooltip Card (Rendered in-place snapping above the hovered point, displays Total Emails) */}
          {hoveredLatencyIndex !== null && (
            <div
              className="absolute z-30 p-3 bg-white border border-border-subtle text-on-surface rounded-xl text-xs shadow-xl flex flex-col gap-1.5 w-48 font-sans select-none pointer-events-none animate-in fade-in duration-100 -translate-x-1/2"
              style={{
                left: `${points[hoveredLatencyIndex].x / 10}%`,
                top: `${points[hoveredLatencyIndex].y - 95}px`,
              }}
            >
              <div className="text-center font-extrabold border-b border-border-subtle/60 pb-1 text-primary text-[11px] uppercase tracking-wider mb-0.5">
                {latencyData[hoveredLatencyIndex].label}
              </div>
              <div className="flex justify-between text-on-surface-variant font-bold">
                <span>Avg Latency:</span>
                <span className="font-mono text-primary">{latencyData[hoveredLatencyIndex].latency} ms</span>
              </div>
              <div className="flex justify-between text-on-surface-variant font-bold">
                <span>Total Emails:</span>
                <span className="font-mono text-primary">{latencyData[hoveredLatencyIndex].emails_count}</span>
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
        <div className="relative w-[96%] mx-auto h-6 mt-2 pt-2.5 border-t border-border-subtle/50 text-[10px] font-bold text-on-surface-variant font-sans select-none">
          {latencyData.map((d, idx) => {
            const shouldShowLabel = latencyData.length <= 7 || idx % 5 === 0 || idx === latencyData.length - 1;
            if (!shouldShowLabel) return null;
            return (
              <div
                key={idx}
                className="absolute text-center uppercase tracking-wider font-extrabold -translate-x-1/2"
                style={{ left: `${(idx / (latencyData.length - 1 || 1)) * 100}%` }}
              >
                {d.label}
              </div>
            );
          })}
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
            <table className="w-full text-left border-collapse font-sans">
              <thead>
                <tr className="border-b border-border-subtle bg-surface-low/40">
                  <th className="px-5 py-3 text-xs font-bold text-on-surface-variant tracking-wide w-[22%] min-w-[170px]">{t("threats.timestamp")}</th>
                  <th className="px-5 py-3 text-xs font-bold text-on-surface-variant tracking-wide w-[28%] min-w-[180px]">{t("threats.sender")}</th>
                  <th className="px-5 py-3 text-xs font-bold text-on-surface-variant tracking-wide w-[35%] min-w-[220px]">{t("threats.subject")}</th>
                  <th className="px-5 py-3 text-xs font-bold text-on-surface-variant tracking-wide w-[15%] min-w-[140px]">{t("threats.verdict")}</th>
                  <th className="px-5 py-3 text-xs font-bold text-on-surface-variant tracking-wide min-w-[180px]">{t("threats.actions")}</th>
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
                    <tr className="hover:bg-surface-low/20 transition-all text-xs">
                      <td className="px-5 py-3.5">
                        <span className="text-xs text-on-surface-variant font-medium">
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
                          {threat.verdict !== "phishing" && threat.verdict !== "quarantine"
                            ? "[Masqué par Sicurre]"
                            : (threat.sender || t("threats.unknown_sender"))}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="text-on-surface truncate block max-w-[220px] select-all font-semibold" title={threat.subject}>
                          {threat.verdict !== "phishing" && threat.verdict !== "quarantine"
                            ? "[Masqué par Sicurre]"
                            : (threat.subject || t("threats.no_subject"))}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                      </td>
                      <td className="px-5 py-3.5">
                        {threat.verdict === "phishing" || threat.verdict === "quarantine" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={updateStatusMutation.isPending}
                            onClick={() =>
                              handleUpdateStatus(
                                threat.id,
                                threat.status === "trashed" ? "restored" : "trashed",
                              )
                            }
                            className="h-8 text-[11px]"
                          >
                            {threat.status === "trashed" ? (
                              <RotateCcw className="w-3.5 h-3.5" />
                            ) : (
                              <Trash2 className="w-3.5 h-3.5" />
                            )}
                            <span>
                              {threat.status === "trashed"
                                ? t("threats.action_restore")
                                : t("threats.action_trash")}
                            </span>
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={feedbackMutation.isPending}
                            onClick={() => handleReportFalseNegative(threat.id)}
                            className="h-8 text-[11px]"
                          >
                            <Flag className="w-3.5 h-3.5" />
                            <span>{i18n.language === "fr" ? "Signaler phishing" : "Report phishing"}</span>
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
