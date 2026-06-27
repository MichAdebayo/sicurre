import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import {
  Inbox,
  ShieldAlert,
  Calendar,
  X,
  Mail,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Eye,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { Button } from "../components/ui/button";
import {
  useQuarantineItems,
  useReleaseQuarantine,
  useDeleteQuarantine,
  useReleaseAndWhitelist,
  QuarantineItem,
} from "../lib/api";

const MotionDiv = motion.div as any;

export default function QuarantineRoute() {
  const { t } = useTranslation();

  // Queries & Mutations
  const { data: items, isLoading, error, refetch } = useQuarantineItems();
  const releaseMutation = useReleaseQuarantine();
  const deleteMutation = useDeleteQuarantine();
  const whitelistMutation = useReleaseAndWhitelist();

  // Selected item for the Safe Preview drawer
  const [selectedItem, setSelectedItem] = useState<QuarantineItem | null>(null);
  const [actionSuccess, setActionSuccess] = useState("");
  const [actionError, setActionError] = useState("");

  const getRemainingTime = (expiresAtStr: string) => {
    const expiry = new Date(expiresAtStr).getTime();
    const now = new Date().getTime();
    const diff = expiry - now;
    if (diff <= 0) return t("quarantine.expired") || "Expired";

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    return `${days} ${t("quarantine.days")} ${hours} ${t("quarantine.hours")}`;
  };

  const handleRelease = async (id: string) => {
    setActionError("");
    setActionSuccess("");
    try {
      const res = await releaseMutation.mutateAsync(id);
      setActionSuccess(`${t("quarantine.release_success")} (Forwarded to ${res.forwarded_to})`);
      setSelectedItem(null);
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to release email.");
    }
  };

  const handleDelete = async (id: string) => {
    setActionError("");
    setActionSuccess("");
    try {
      await deleteMutation.mutateAsync(id);
      setActionSuccess(t("quarantine.delete_success"));
      setSelectedItem(null);
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete item.");
    }
  };

  const handleWhitelist = async (id: string) => {
    setActionError("");
    setActionSuccess("");
    try {
      const res = await whitelistMutation.mutateAsync(id);
      setActionSuccess(`${t("quarantine.whitelist_success")} (Sender ${res.whitelisted_pattern} allowed)`);
      setSelectedItem(null);
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to whitelist.");
    }
  };

  // Convert raw text into safe HTML by replacing linebreaks and escaping tags
  const renderSafeHtml = (rawText: string) => {
    const escaped = rawText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
    return escaped.replace(/\n/g, "<br />");
  };

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      {/* Header */}
      <div className="pb-6 border-b border-border-subtle">
        <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight flex items-center gap-3">
          {t("quarantine.title")}
          {items && items.length > 0 && (
            <span className="inline-flex items-center bg-warning/10 text-warning text-xs font-bold px-2.5 py-1 rounded-full uppercase tracking-wider">
              {items.length} {t("quarantine.title").toLowerCase()}
            </span>
          )}
        </h1>
        <p className="text-sm text-on-surface-variant mt-1">
          {t("quarantine.subtitle")}
        </p>
      </div>

      {/* Daily Digest Status banner */}
      <div className="rounded-xl border border-primary/10 bg-primary/[0.03] p-4 text-xs font-semibold text-primary flex items-center gap-2.5 shadow-sm">
        <CheckCircle2 className="w-4.5 h-4.5 text-primary shrink-0" />
        <span>{t("quarantine.daily_digest_active")}</span>
      </div>

      {actionSuccess && (
        <div className="p-3 bg-safe/10 border border-safe/25 text-safe text-xs font-semibold rounded-lg flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="p-3 bg-error/10 border border-error/25 text-error text-xs font-semibold rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Grid container with list and safe preview pane */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Held Email List */}
        <div className="lg:col-span-8 bg-white rounded-xl border border-border-subtle overflow-hidden shadow-sm">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-surface-low rounded-xl animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="py-16 text-center flex flex-col items-center justify-center">
              <AlertCircle className="w-10 h-10 text-error/40 mb-3" />
              <p className="font-semibold text-sm text-on-surface">{t("common.error_occurred")}</p>
            </div>
          ) : !items || items.length === 0 ? (
            <div className="py-20 text-center flex flex-col items-center justify-center text-on-surface-variant/50">
              <Inbox className="w-12 h-12 text-on-surface-variant/30 mb-3" />
              <p className="text-sm font-semibold">{t("quarantine.no_items")}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border-subtle bg-surface-low/40">
                    <th className="px-5 py-3.5 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("quarantine.sender")}</th>
                    <th className="px-5 py-3.5 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("quarantine.subject")}</th>
                    <th className="px-5 py-3.5 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("quarantine.expires_in")}</th>
                    <th className="px-5 py-3.5 text-right text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">{t("quarantine.actions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {items.map((item) => {
                    const isSelected = selectedItem?.id === item.id;
                    return (
                      <tr
                        key={item.id}
                        onClick={() => setSelectedItem(item)}
                        className={`hover:bg-surface-low/20 transition-all cursor-pointer text-sm ${
                          isSelected ? "bg-primary/[0.03] font-medium" : ""
                        }`}
                      >
                        <td className="px-5 py-4">
                          <span className="font-semibold text-on-surface max-w-[200px] truncate block select-none">
                            {item.sender}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <span className="text-on-surface truncate block max-w-[250px] select-none" title={item.subject}>
                            {item.subject || t("threats.no_subject")}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <span className="inline-flex items-center gap-1 text-[12px] font-mono text-on-surface-variant/80">
                            <Calendar className="w-3.5 h-3.5 text-on-surface-variant/50" />
                            {getRemainingTime(item.expires_at)}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="inline-flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-xs px-2.5"
                              onClick={() => setSelectedItem(item)}
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="primary"
                              size="sm"
                              className="text-xs"
                              onClick={() => handleRelease(item.id)}
                            >
                              {t("quarantine.release").replace("to Inbox", "").trim()}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right Hand: Safe Preview & Quarantine Remediation Console */}
        <div className="lg:col-span-4 bg-white rounded-xl border border-border-subtle p-6 shadow-sm min-h-[400px] flex flex-col justify-between">
          <AnimatePresence mode="wait">
            {selectedItem ? (
              <MotionDiv
                key={selectedItem.id}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                className="space-y-6 flex-1 flex flex-col justify-between"
              >
                <div>
                  <div className="flex justify-between items-start border-b border-border-subtle pb-4">
                    <div>
                      <h3 className="font-display font-semibold text-[17px] text-on-surface">
                        {t("quarantine.safe_preview")}
                      </h3>
                      <p className="text-[11px] text-on-surface-variant/60 mt-0.5">
                        {t("quarantine.preview_notice")}
                      </p>
                    </div>
                    <button
                      onClick={() => setSelectedItem(null)}
                      className="p-1 rounded-md hover:bg-surface-low transition-colors cursor-pointer"
                    >
                      <X className="w-4 h-4 text-on-surface-variant" />
                    </button>
                  </div>

                  <div className="space-y-3 pt-4 text-xs">
                    <div>
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px]">
                        From
                      </span>
                      <span className="text-on-surface font-semibold select-all block mt-0.5">
                        {selectedItem.sender}
                      </span>
                    </div>

                    <div>
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px]">
                        Subject
                      </span>
                      <span className="text-on-surface font-semibold block mt-0.5">
                        {selectedItem.subject || t("threats.no_subject")}
                      </span>
                    </div>

                    <div>
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px]">
                        Risk Level (CamemBERTav2 Verdict)
                      </span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-md uppercase bg-error/15 text-error">
                          {selectedItem.safety_verdict}
                        </span>
                        <span className="font-mono text-on-surface-variant">
                          Score: {Math.round(selectedItem.composite_score * 100)}%
                        </span>
                      </div>
                    </div>

                    {/* Sandboxed Preview Frame */}
                    <div className="pt-2">
                      <span className="font-bold text-on-surface-variant/70 block uppercase tracking-wider text-[10px] mb-1.5">
                        Sanitized Content Body
                      </span>
                      <iframe
                        title="Quarantine Safe Preview Frame"
                        srcDoc={`<!DOCTYPE html><html><head><style>body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #374151; font-size: 12px; line-height: 1.6; margin: 10px; word-break: break-word; } a { color: #2563eb; pointer-events: none !important; text-decoration: underline; } img { display: none !important; }</style></head><body>${renderSafeHtml(selectedItem.body_text)}</body></html>`}
                        sandbox=""
                        className="w-full h-[240px] bg-surface-low border border-border-subtle rounded-xl select-text"
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-2 pt-4 border-t border-border-subtle mt-4">
                  <Button
                    variant="primary"
                    className="w-full gap-2 text-xs py-2.5 uppercase font-bold tracking-wider"
                    onClick={() => handleRelease(selectedItem.id)}
                  >
                    <Mail className="w-4 h-4" />
                    {t("quarantine.release")}
                  </Button>

                  <Button
                    variant="outline"
                    className="w-full gap-2 text-xs py-2.5 border-safe/30 text-safe hover:bg-safe/5 font-bold uppercase tracking-wider"
                    onClick={() => handleWhitelist(selectedItem.id)}
                  >
                    <ShieldCheck className="w-4 h-4 text-safe" />
                    {t("quarantine.whitelist")}
                  </Button>

                  <Button
                    variant="danger"
                    className="w-full gap-2 text-xs py-2.5 uppercase font-bold tracking-wider"
                    onClick={() => handleDelete(selectedItem.id)}
                  >
                    <Trash2 className="w-4 h-4" />
                    {t("quarantine.delete")}
                  </Button>
                </div>
              </MotionDiv>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center text-on-surface-variant/40 py-12">
                <Eye className="w-10 h-10 mb-2 stroke-[1.5]" />
                <p className="text-sm font-semibold">Select an Email to Inspect</p>
                <p className="text-xs max-w-[200px] mt-1">
                  Previews are loaded inside a strict sandboxed container without executing links or scripts.
                </p>
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </MotionDiv>
  );
}
