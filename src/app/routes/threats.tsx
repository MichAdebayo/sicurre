import { useDeferredValue, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  Search,
  Download,
  Copy,
  AlertTriangle,
  Eye,
  EyeOff,
} from "lucide-react";
import { useReportAddress, useSetThreatVisibility, useThreatLogs, useThreatPage } from "../lib/api";
import { VerdictBadge } from "../components/threats/verdict-badge";
import { Button } from "../components/ui/button";
import { AppToast } from "../components/common/app-toast";
import { useActiveDomain } from "../contexts/active-domain";

const MotionDiv = motion.div as any;

export default function ThreatsRoute() {
  const { t, i18n } = useTranslation();
  const { activeDomain } = useActiveDomain();
  const { data: reportAddressData } = useReportAddress();

  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearch = useDeferredValue(searchQuery);
  const [filterVerdict, setFilterVerdict] = useState<string>("all");

  // Date range filters ("all", "today", "7d", "month")
  const [dateFilter, setDateFilter] = useState<"all" | "today" | "7d" | "month" | "last_month">("all");
  const [showHidden, setShowHidden] = useState(false);

  // Latency chart hover state
  const [hoveredLatencyIndex, setHoveredLatencyIndex] = useState<number | null>(null);

  // Table pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { data: threatPage, isLoading, error } = useThreatPage(activeDomain, {
    page: currentPage,
    pageSize: itemsPerPage,
    verdict: filterVerdict as "all" | "phishing" | "spam" | "legitimate",
    dateRange: dateFilter,
    search: deferredSearch,
    hidden: showHidden,
  });
  const { data: chartThreats } = useThreatLogs(activeDomain);
  const visibilityMutation = useSetThreatVisibility(activeDomain);
  const threats = threatPage?.items ?? [];

  const [actionSuccess, setActionSuccess] = useState("");
  const reportAddress = reportAddressData?.address ?? "";

  const copyReportAddress = async () => {
    if (!reportAddress) return;
    await navigator.clipboard.writeText(reportAddress);
    setActionSuccess(t("threats.report_address_copied"));
  };

  useEffect(() => {
    setCurrentPage(1);
    setSelectedIds(new Set());
  }, [activeDomain, deferredSearch, filterVerdict, dateFilter, showHidden]);

  const updateSelection = (id: string, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      checked ? next.add(id) : next.delete(id);
      return next;
    });
  };

  const updateVisibility = async () => {
    if (selectedIds.size === 0) return;
    await visibilityMutation.mutateAsync({ ids: [...selectedIds], hidden: !showHidden });
    setSelectedIds(new Set());
    setActionSuccess(showHidden ? t("threats.restore_success") : t("threats.hide_success"));
  };

  const handleExportCSV = () => {
    if (threats.length === 0) return;
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
    link.setAttribute("download", `sicurre_historical_report_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const getLatencyData = () => {
    const threatsList = chartThreats || [];
    const days = [];
    const now = new Date();

    if (dateFilter === "all") {
      const groups = new Map<string, typeof threatsList>();
      threatsList.forEach((threat) => {
        const key = new Date(threat.received_at).toISOString().slice(0, 10);
        groups.set(key, [...(groups.get(key) ?? []), threat]);
      });
      [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)).forEach(([key, events]) => {
        const measured = events.filter((event) => (event.latency_ms ?? 0) > 0);
        days.push({
          label: new Date(`${key}T12:00:00`).toLocaleDateString(i18n.language === "fr" ? "fr-FR" : "en-US", { month: "short", day: "numeric" }),
          latency: measured.length
            ? Math.round(measured.reduce((sum, event) => sum + (event.latency_ms ?? 0), 0) / measured.length)
            : 0,
          emails_count: events.length,
          measured_count: measured.length,
        });
      });
    } else if (dateFilter === "today") {
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

        const measuredThreats = hourlyThreats.filter((threat) => (threat.latency_ms ?? 0) > 0);
        const emails_count = hourlyThreats.length;
        const latency = measuredThreats.length > 0
          ? Math.round(measuredThreats.reduce((sum, threat) => sum + (threat.latency_ms ?? 0), 0) / measuredThreats.length)
          : 0;

        days.push({ label, latency, emails_count, measured_count: measuredThreats.length });
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

        const measuredThreats = dailyThreats.filter((threat) => (threat.latency_ms ?? 0) > 0);
        const emails_count = dailyThreats.length;
        const latency = measuredThreats.length > 0
          ? Math.round(measuredThreats.reduce((sum, threat) => sum + (threat.latency_ms ?? 0), 0) / measuredThreats.length)
          : 0;

        days.push({ label, latency, emails_count, measured_count: measuredThreats.length });
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

        const measuredThreats = dailyThreats.filter((threat) => (threat.latency_ms ?? 0) > 0);
        const emails_count = dailyThreats.length;
        const latency = measuredThreats.length > 0
          ? Math.round(measuredThreats.reduce((sum, threat) => sum + (threat.latency_ms ?? 0), 0) / measuredThreats.length)
          : 0;

        days.push({ label, latency, emails_count, measured_count: measuredThreats.length });
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

        const measuredThreats = dailyThreats.filter((threat) => (threat.latency_ms ?? 0) > 0);
        const emails_count = dailyThreats.length;
        const latency = measuredThreats.length > 0
          ? Math.round(measuredThreats.reduce((sum, threat) => sum + (threat.latency_ms ?? 0), 0) / measuredThreats.length)
          : 0;

        days.push({ label, latency, emails_count, measured_count: measuredThreats.length });
      }
    }
    return days;
  };

  const latencyData = getLatencyData();
  const measuredLatencyData = latencyData.filter((point) => point.measured_count > 0);
  const maxLatencyVal = Math.max(...measuredLatencyData.map((d) => d.latency), 1);
  const chartMax = Math.ceil((maxLatencyVal * 1.15) / 100) * 100 || 100;

  // SVG coordinates
  const points = measuredLatencyData.map((d) => {
    const dataIndex = latencyData.indexOf(d);
    const x = 64 + (dataIndex / (latencyData.length - 1 || 1)) * 916;
    const y = 180 - (d.latency / chartMax) * 150;
    return { x, y, data: d };
  });
  const pathD = points.length > 0 ? `M ${points.map((p) => `${p.x} ${p.y}`).join(" L ")}` : "";

  // Pagination bounds
  const totalItems = threatPage?.total ?? 0;
  const totalPages = threatPage?.pages ?? 1;
  const activePage = Math.min(currentPage, totalPages);
  const paginatedThreats = threats;

  return (
    <MotionDiv
      initial={false}
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
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="app-h1">
              {t("threats.title")}
            </h1>
          </div>
          <p className="app-body-sub mt-1">
            {t("threats.subtitle")}
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-3 self-start sm:w-auto sm:self-center">
          {/* Date range filter dropdown */}
          <select
            value={dateFilter}
            onChange={(e) => {
              setDateFilter(e.target.value as any);
              setCurrentPage(1);
            }}
            className="px-3 py-2 bg-white border border-border-subtle rounded-lg text-xs font-bold text-on-surface focus:outline-none focus:border-primary cursor-pointer shadow-sm h-9"
          >
            <option value="all">{t("threats.range_all")}</option>
            <option value="today">{t("threats.range_today")}</option>
            <option value="7d">{t("threats.range_7d")}</option>
            <option value="month">{t("threats.range_month")}</option>
            <option value="last_month">{t("threats.range_last_month")}</option>
          </select>

          <button
            onClick={handleExportCSV}
            className="flex h-9 items-center gap-2 rounded-lg border border-border-subtle bg-white px-4 py-2 text-[13px] font-semibold transition-colors hover:bg-surface-low"
          >
            <Download className="w-4 h-4 text-on-surface-variant" />
            <span>{t("threats.export_report")}</span>
          </button>
        </div>
      </div>

      <section className="relative min-h-[320px] border-b border-border-subtle py-6">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
          <div>
            <h3 className="font-display font-bold text-[17px] text-on-surface">
              {t("threats.latency_title")}
            </h3>
            <p className="text-sm text-on-surface-variant mt-1">
              {t("threats.latency_description")}
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-semibold text-on-surface-variant">
            <span className="h-0.5 w-6 rounded-full bg-primary" />
            <span>{t("threats.latency_measure")}</span>
          </div>
        </div>

        {points.length === 0 ? (
          <div className="flex h-56 items-center justify-center border-y border-border-subtle/60 text-center">
            <p className="max-w-md text-sm text-on-surface-variant">{t("threats.latency_empty")}</p>
          </div>
        ) : (
          <div
            className="relative h-64 w-full overflow-hidden"
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              const cursorX = ((event.clientX - rect.left) / rect.width) * 1040;
              const closest = points.reduce(
                (best, point, index) =>
                  Math.abs(point.x - cursorX) < best.distance
                    ? { index, distance: Math.abs(point.x - cursorX) }
                    : best,
                { index: 0, distance: Number.POSITIVE_INFINITY },
              );
              setHoveredLatencyIndex(closest.index);
            }}
            onMouseLeave={() => setHoveredLatencyIndex(null)}
          >
            <svg className="h-[220px] w-full" viewBox="0 0 1040 220" preserveAspectRatio="none" role="img">
              <title>{t("threats.latency_title")}</title>
              {[30, 67.5, 105, 142.5, 180].map((y, index) => (
                <g key={y}>
                  <line x1="64" y1={y} x2="980" y2={y} className="stroke-border-subtle" strokeWidth="0.7" />
                  <text x="54" y={y + 4} textAnchor="end" className="fill-on-surface-variant text-[10px]">
                    {Math.round(chartMax * (1 - index / 4))}
                  </text>
                </g>
              ))}
              <text x="12" y="105" transform="rotate(-90 12 105)" textAnchor="middle" className="fill-on-surface-variant text-[10px]">
                ms
              </text>
              {hoveredLatencyIndex !== null && (
                <line
                  x1={points[hoveredLatencyIndex].x}
                  y1="20"
                  x2={points[hoveredLatencyIndex].x}
                  y2="180"
                  className="stroke-primary/50"
                  strokeWidth="1.5"
                  strokeDasharray="4 4"
                />
              )}
              <path d={pathD} fill="none" className="stroke-primary" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              {points.map((point, index) => (
                <circle
                  key={point.data.label}
                  cx={point.x}
                  cy={point.y}
                  r={hoveredLatencyIndex === index ? 6 : 4}
                  className="fill-white stroke-primary"
                  strokeWidth="2.5"
                />
              ))}
            </svg>
            {hoveredLatencyIndex !== null && (
              <div
                className="pointer-events-none absolute top-3 z-30 w-44 -translate-x-1/2 rounded-lg border border-border-subtle bg-white p-3 text-xs text-on-surface shadow-md"
                style={{ left: `${Math.min(90, Math.max(12, points[hoveredLatencyIndex].x / 10.4))}%` }}
              >
                <p className="mb-2 font-semibold text-on-surface">{points[hoveredLatencyIndex].data.label}</p>
                <div className="flex justify-between gap-3 text-on-surface-variant">
                  <span>{t("threats.latency_average")}</span>
                  <strong className="font-mono text-on-surface">{points[hoveredLatencyIndex].data.latency} ms</strong>
                </div>
                <div className="mt-1 flex justify-between gap-3 text-on-surface-variant">
                  <span>{t("threats.email_count")}</span>
                  <strong className="font-mono text-on-surface">{points[hoveredLatencyIndex].data.emails_count}</strong>
                </div>
              </div>
            )}
            <div className="absolute bottom-0 left-16 right-4 flex justify-between border-t border-border-subtle pt-2 text-[10px] font-semibold text-on-surface-variant">
              {latencyData
                .filter((_, index) => latencyData.length <= 7 || index === 0 || index === latencyData.length - 1 || index % 5 === 0)
                .map((point) => <span key={point.label}>{point.label}</span>)}
            </div>
          </div>
        )}
      </section>

      {reportAddress && (
        <details className="group border-y border-border-subtle py-4">
          <summary className="cursor-pointer list-none text-sm font-semibold text-on-surface marker:hidden">
            <span className="inline-flex items-center gap-2">
              {t("threats.report_missed_title")}
              <span aria-hidden="true" className="text-on-surface-variant transition-transform group-open:rotate-180">⌄</span>
            </span>
          </summary>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-3xl break-words text-sm text-on-surface-variant">
              {t("threats.report_missed_description", { address: reportAddress })}
            </p>
            <Button variant="outline" size="sm" onClick={() => void copyReportAddress()} className="shrink-0">
              <Copy className="h-4 w-4" />
              <span>{t("threats.copy_address")}</span>
            </Button>
          </div>
        </details>
      )}

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

        <div className="flex w-full flex-wrap gap-2 sm:w-auto">
          {(["all", "phishing", "spam", "legitimate"] as const).map((v) => (
            <button
              key={v}
              onClick={() => {
                setFilterVerdict(v);
                setCurrentPage(1);
              }}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${filterVerdict === v
                  ? "bg-navy-dark text-on-primary border-navy-dark shadow-sm"
                  : "bg-white text-on-surface-variant hover:bg-surface-low border-border-subtle"
                }`}
            >
              {v === "all" ? t("threats.all") : t(`threats.badge_${v}`)}
            </button>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowHidden((current) => !current)}
            className="gap-2"
          >
            {showHidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            {showHidden ? t("threats.show_visible") : t("threats.show_hidden")}
          </Button>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-y border-border-subtle py-3">
          <span className="text-sm font-semibold text-on-surface">
            {t("threats.selected_count", { count: selectedIds.size })}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void updateVisibility()}
            disabled={visibilityMutation.isPending}
          >
            {showHidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            {showHidden ? t("threats.restore_selected") : t("threats.hide_selected")}
          </Button>
        </div>
      )}

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
            {t("threats.no_records")}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse font-sans">
              <thead>
                <tr className="border-b border-border-subtle bg-surface-low/40">
                  <th className="w-12 px-4 py-3">
                    <input
                      type="checkbox"
                      aria-label={t("threats.select_page")}
                      checked={paginatedThreats.length > 0 && paginatedThreats.every((threat) => selectedIds.has(threat.id))}
                      onChange={(event) => {
                        const checked = event.target.checked;
                        setSelectedIds((current) => {
                          const next = new Set(current);
                          paginatedThreats.forEach((threat) => checked ? next.add(threat.id) : next.delete(threat.id));
                          return next;
                        });
                      }}
                      className="h-4 w-4 accent-primary"
                    />
                  </th>
                  <th className="min-w-[210px] px-5 py-3 text-xs font-bold text-on-surface-variant">{t("threats.processed_item")}</th>
                  <th className="min-w-[150px] px-5 py-3 text-xs font-bold text-on-surface-variant">{t("threats.timestamp")}</th>
                  <th className="min-w-[140px] px-5 py-3 text-xs font-bold text-on-surface-variant">{t("threats.verdict")}</th>
                  <th className="whitespace-nowrap px-5 py-3 text-xs font-bold text-on-surface-variant">{t("threats.phishing_risk")}</th>
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
                      <td className="px-4 py-3.5">
                        <input
                          type="checkbox"
                          aria-label={t("threats.select_item", { reference: threat.privacy_reference })}
                          checked={selectedIds.has(threat.id)}
                          onChange={(event) => updateSelection(threat.id, event.target.checked)}
                          className="h-4 w-4 accent-primary"
                        />
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="block font-semibold text-on-surface">
                          {t("threats.processed_reference", { reference: threat.privacy_reference.replace("MSG-", "") })}
                        </span>
                        <span className="mt-0.5 block text-[11px] text-on-surface-variant">
                          {threat.content_redacted ? t("threats.content_discarded") : t("threats.content_quarantined")}
                        </span>
                      </td>
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
                        <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} showRisk={false} />
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-sm font-semibold text-on-surface">
                          {Math.round(threat.confidence * 100)} %
                        </span>
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
          <div className="flex flex-col gap-3 border-t border-border-subtle bg-surface-low/10 px-5 py-4 font-sans sm:flex-row sm:items-center sm:justify-between">
            <span className="text-xs text-on-surface-variant font-bold">
              {t("threats.pagination", {
                page: activePage,
                pages: totalPages,
                count: totalItems,
              })}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={activePage === 1}
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                className="text-xs py-1 px-3.5 cursor-pointer font-bold h-8"
              >
                {t("common.previous")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={activePage === totalPages}
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                className="text-xs py-1 px-3.5 cursor-pointer font-bold h-8"
              >
                {t("common.next")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </MotionDiv>
  );
}
