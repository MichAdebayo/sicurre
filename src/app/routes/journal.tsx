import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import { Search, ShieldAlert, MailWarning, MailCheck, Layers } from "lucide-react";
import { useThreats } from "../hooks/useThreats";
import { ThreatRow } from "../components/threats/threat-row";

const MotionDiv = motion.div as any;

type FilterVerdict = "all" | "phishing" | "spam" | "legitimate";

export default function JournalRoute() {
  const { t } = useTranslation();
  const { threats, isLoading, updateStatus } = useThreats();
  const [searchTerm, setSearchTerm] = useState("");
  const [filterVerdict, setFilterVerdict] = useState<FilterVerdict>("all");

  const allThreats = threats || [];

  const counts = {
    all: allThreats.length,
    phishing: allThreats.filter(t => t.verdict === "phishing").length,
    spam: allThreats.filter(t => t.verdict === "spam").length,
    legitimate: allThreats.filter(t => t.verdict === "legitimate").length,
  };

  const filteredThreats = allThreats.filter(threat => {
    const matchesSearch = threat.subject.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesVerdict = filterVerdict === "all" || threat.verdict === filterVerdict;
    return matchesSearch && matchesVerdict;
  });

  const handleUpdateStatus = (id: string, status: "trashed" | "restored") => {
    updateStatus.mutate({ id, status });
  };

  const tabs: { key: FilterVerdict; label: string; icon: React.ReactNode; activeClass: string }[] = [
    { key: "all", label: "Tous", icon: <Layers className="w-3.5 h-3.5" />, activeClass: "bg-slate-900 text-white" },
    { key: "phishing", label: t("threats.badge_phishing"), icon: <ShieldAlert className="w-3.5 h-3.5" />, activeClass: "bg-red-600 text-white" },
    { key: "spam", label: t("threats.badge_spam"), icon: <MailWarning className="w-3.5 h-3.5" />, activeClass: "bg-amber-500 text-white" },
    { key: "legitimate", label: t("threats.badge_legitimate"), icon: <MailCheck className="w-3.5 h-3.5" />, activeClass: "bg-green-600 text-white" },
  ];

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div>
        <h2 className="text-3xl font-display font-bold text-slate-900">{t("threats.title")}</h2>
        <p className="text-sm text-slate-500 mt-1">{t("threats.subtitle")}</p>
      </div>

      {/* Filter tabs + search bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        {/* Verdict tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl shrink-0">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilterVerdict(tab.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterVerdict === tab.key
                  ? tab.activeClass + " shadow-sm"
                  : "text-slate-500 hover:text-slate-800 hover:bg-slate-200"
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              <span className={`ml-0.5 font-mono text-[10px] ${filterVerdict === tab.key ? "opacity-80" : "text-slate-400"}`}>
                {counts[tab.key]}
              </span>
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="flex items-center gap-2.5 flex-1 bg-white border border-slate-200 rounded-xl px-4 py-2.5 shadow-sm">
          <Search className="w-4 h-4 text-slate-400 shrink-0" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder={t("threats.search_placeholder")}
            className="bg-transparent border-none outline-none text-sm w-full text-slate-800 placeholder-slate-400"
          />
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="space-y-px">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-14 bg-slate-50 animate-pulse border-b border-slate-100 last:border-0" />
            ))}
          </div>
        ) : filteredThreats.length === 0 ? (
          <div className="py-14 text-center">
            <MailCheck className="w-10 h-10 text-slate-200 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-600">Aucune menace pour ce filtre</p>
            <p className="text-xs text-slate-400 mt-1">{t("dashboard.no_threats")}</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            <AnimatePresence>
              {filteredThreats.map((threat) => (
                <ThreatRow
                  key={threat.id}
                  threat={threat}
                  onUpdateStatus={handleUpdateStatus}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </MotionDiv>
  );
}

