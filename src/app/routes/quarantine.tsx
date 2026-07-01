import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import {
  Inbox,
  Calendar,
  X,
  Mail,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Eye,
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
  const { t, i18n } = useTranslation();
  const isFR = i18n.language === "fr";

  // Queries & Mutations
  const { data: items, isLoading, error, refetch } = useQuarantineItems();
  const releaseMutation = useReleaseQuarantine();
  const deleteMutation = useDeleteQuarantine();
  const whitelistMutation = useReleaseAndWhitelist();

  // Selected item for the Zoom Modal
  const [selectedItem, setSelectedItem] = useState<QuarantineItem | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  
  // Page pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 9; // 3 columns x 3 rows

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

  const getRemainingTime = (expiresAtStr: string) => {
    if (!expiresAtStr) return "14 d";
    const expiry = new Date(expiresAtStr).getTime();
    if (isNaN(expiry)) {
      return "14 d";
    }
    const now = new Date().getTime();
    const diff = expiry - now;
    if (diff <= 0) return t("quarantine.expired") || "Expired";

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    
    if (isNaN(days) || isNaN(hours)) {
      return "14 d";
    }
    
    return `${days} d ${hours} h`;
  };

  const handleRelease = async (id: string) => {
    setActionError("");
    setActionSuccess("");
    try {
      const res = await releaseMutation.mutateAsync(id);
      setActionSuccess(
        i18n.language === "fr"
          ? `Email libéré avec succès (Transféré à ${res.forwarded_to})`
          : `Email released successfully (Forwarded to ${res.forwarded_to})`
      );
      setSelectedItem(null);
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to release email.");
    }
  };

  const handleDelete = async (id: string) => {
    setConfirmDeleteId(id);
  };

  const handleWhitelist = async (id: string) => {
    setActionError("");
    setActionSuccess("");
    try {
      const res = await whitelistMutation.mutateAsync(id);
      setActionSuccess(
        i18n.language === "fr"
          ? `Email marqué comme sain et expéditeur (${res.whitelisted_pattern}) ajouté à la liste blanche.`
          : `Email marked as safe and sender (${res.whitelisted_pattern}) added to whitelist.`
      );
      setSelectedItem(null);
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to whitelist.");
    }
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

  // Only phishing emails should be inside the quarantine page list
  const phishingItems = items
    ? items.filter((item) => item.safety_verdict === "phishing")
    : [];

  // Paginated columns items
  const totalItems = phishingItems.length;
  const totalPages = Math.ceil(totalItems / itemsPerPage) || 1;
  const activePage = Math.min(currentPage, totalPages);
  const paginatedItems = phishingItems.slice(
    (activePage - 1) * itemsPerPage,
    activePage * itemsPerPage
  );

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-8 animate-in fade-in duration-200"
    >
      {/* Header */}
      <div className="pb-6 border-b border-border-subtle">
        <h1 className="app-h1 flex items-center gap-3">
          {t("quarantine.title")}
          {phishingItems.length > 0 && (
            <span className="inline-flex items-center bg-error/10 text-error text-xs font-bold px-2.5 py-1 rounded-full uppercase tracking-wider">
              {phishingItems.length} {i18n.language === "fr" ? "Menaces en quarantaine" : "Threats Quarantined"}
            </span>
          )}
        </h1>
        <p className="app-body-sub mt-1">
          {t("quarantine.subtitle")}
        </p>
      </div>

      {actionSuccess && (
        <div className="p-3.5 bg-safe/10 border border-safe/25 text-safe text-xs font-semibold rounded-lg flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="p-3.5 bg-error/10 border border-error/25 text-error text-xs font-semibold rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Grid container representing items as cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-44 bg-surface-low rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="py-20 text-center flex flex-col items-center justify-center">
          <AlertCircle className="w-10 h-10 text-error/40 mb-3" />
          <p className="font-semibold text-sm text-on-surface">{t("common.error_occurred")}</p>
        </div>
      ) : phishingItems.length === 0 ? (
        <div className="py-20 text-center flex flex-col items-center justify-center text-on-surface-variant/50">
          <Inbox className="w-12 h-12 text-on-surface-variant/30 mb-3" />
          <p className="text-sm font-semibold">{t("quarantine.no_items")}</p>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {paginatedItems.map((item) => (
              <div
                key={item.id}
                className="bg-white border border-border-subtle rounded-2xl p-5 hover:-translate-y-1 hover:shadow-md hover:border-primary/20 transition-all duration-200 flex flex-col justify-between h-44 cursor-default group relative shadow-sm"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-on-surface-variant/80 text-xs block truncate max-w-[70%] select-none" title={item.sender}>
                      {item.sender}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold font-sans text-error bg-error/10 px-2 py-0.5 rounded-full select-none shrink-0">
                      Phishing
                    </span>
                  </div>
                  
                  <h3 className="font-bold text-sm text-on-surface mt-2.5 line-clamp-2 select-text" title={item.subject}>
                    {item.subject || t("threats.no_subject")}
                  </h3>
                </div>

                <div className="flex items-center justify-between border-t border-border-subtle/50 pt-3 mt-2 select-none">
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold text-on-surface-variant font-sans">
                    <Calendar className="w-3.5 h-3.5 text-on-surface-variant/50" />
                    {getRemainingTime(item.expires_at)}
                  </span>
                  
                  {/* Eyeball icon color changes only when the modal is open or active */}
                  <Button
                    variant={selectedItem?.id === item.id ? "primary" : "outline"}
                    size="sm"
                    className={`text-xs px-2.5 cursor-pointer h-8 transition-colors ${
                      selectedItem?.id === item.id ? "" : "text-on-surface-variant hover:text-primary hover:border-primary"
                    }`}
                    onClick={() => setSelectedItem(item)}
                  >
                    <Eye className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>

          {/* Grid pagination control buttons (rendered unconditionally for page 1 of 1) */}
          {totalPages >= 1 && (
            <div className="flex items-center justify-between px-2 py-4 border-t border-border-subtle/50 font-sans select-none pt-6 mt-2">
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
                    setCurrentPage((prev) => Math.max(1, prev - 1));
                    setSelectedItem(null);
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
                    setCurrentPage((prev) => Math.min(totalPages, prev + 1));
                    setSelectedItem(null);
                  }}
                  className="text-xs py-1 px-3.5 cursor-pointer font-bold h-8"
                >
                  {i18n.language === "fr" ? "Suivant" : "Next"}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Floating zoom modal backdrop overlay with background blur */}
      <AnimatePresence>
        {selectedItem && (
          <div className="fixed inset-0 z-50 bg-neutral-900/60 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto select-none">
            <MotionDiv
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className="bg-white border border-border-subtle rounded-2xl p-6 w-full max-w-2xl shadow-2xl relative max-h-[90vh] overflow-y-auto flex flex-col justify-between font-sans select-text"
            >
              <div>
                <div className="flex justify-between items-start border-b border-border-subtle pb-4 select-none">
                  <div>
                    <h3 className="app-h2 text-on-surface">
                      {t("quarantine.safe_preview")}
                    </h3>
                    <p className="app-body-sub mt-0.5">
                      {t("quarantine.preview_notice")}
                    </p>
                  </div>
                  <button
                    onClick={() => setSelectedItem(null)}
                    className="p-1 rounded-md hover:bg-surface-low transition-colors cursor-pointer"
                  >
                    <X className="w-4.5 h-4.5 text-on-surface-variant" />
                  </button>
                </div>

                <div className="space-y-4 pt-4 text-xs">
                  <div>
                    <span className="app-label-tiny block text-on-surface-variant/80 font-bold text-xs">
                      From
                    </span>
                    <span className="text-[14px] font-medium text-on-surface select-all block mt-1">
                      {selectedItem.sender}
                    </span>
                  </div>

                  <div>
                    <span className="app-label-tiny block text-on-surface-variant/80 font-bold text-xs">
                      Subject
                    </span>
                    <span className="text-[14px] font-medium text-on-surface block mt-1">
                      {selectedItem.subject || t("threats.no_subject")}
                    </span>
                  </div>

                  <div>
                    <span className="app-label-tiny block text-on-surface-variant/80 font-bold text-xs">
                      Quarantined Risk Analysis
                    </span>
                    <div className="flex items-center gap-2 mt-1.5 select-none">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-error/15 text-error">
                        {selectedItem.safety_verdict}
                      </span>
                      <span className="text-xs font-sans text-on-surface-variant font-medium">
                        Score: {Math.round(selectedItem.composite_score * 100)}%
                      </span>
                    </div>
                  </div>

                  {/* Sandboxed Preview Frame */}
                  <div className="pt-2">
                    <iframe
                      title="Quarantine Safe Preview Frame"
                      srcDoc={`<!DOCTYPE html><html><head><style>body { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #374151; font-size: 13.5px; line-height: 1.6; margin: 10px; word-break: break-word; } a { color: #2563eb; pointer-events: none !important; text-decoration: underline; } img { display: none !important; }</style></head><body>${renderSafeHtml(selectedItem.body_text)}</body></html>`}
                      sandbox=""
                      className="w-full h-[240px] bg-surface-low border border-border-subtle rounded-xl select-text"
                    />
                  </div>
                </div>
              </div>

              {/* Action task buttons in the footer modal */}
              <div className="pt-5 border-t border-border-subtle mt-5">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 select-none">
                  <Button
                    variant="primary"
                    className="w-full gap-2 text-xs py-2.5 font-bold"
                    onClick={() => handleRelease(selectedItem.id)}
                  >
                    <Mail className="w-4 h-4" />
                    {t("quarantine.release")}
                  </Button>

                  <Button
                    variant="outline"
                    className="w-full gap-2 text-xs py-2.5 border-safe/30 text-safe hover:bg-safe/5 font-bold"
                    onClick={() => handleWhitelist(selectedItem.id)}
                  >
                    <ShieldCheck className="w-4 h-4 text-safe" />
                    {t("quarantine.whitelist")}
                  </Button>

                  <Button
                    variant="danger"
                    className="w-full gap-2 text-xs py-2.5 font-bold"
                    onClick={() => handleDelete(selectedItem.id)}
                  >
                    <Trash2 className="w-4 h-4" />
                    {t("quarantine.delete")}
                  </Button>
                </div>
                
                <p className="text-[11px] text-on-surface-variant/70 mt-3.5 leading-normal italic text-center select-none">
                  {isFR
                    ? "Note : Libérer transfère l'e-mail dans votre boîte. Autoriser l'expéditeur l'ajoute à votre liste blanche pour contourner les prochains scans."
                    : "Note: Release forwards the email to your inbox. Whitelist adds the sender to your allowlist to bypass future scans."}
                </p>
              </div>
            </MotionDiv>
          </div>
        )}
      </AnimatePresence>

      {/* Confirmation Modal */}
      {confirmDeleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm select-none">
          <div className="bg-white border border-border-subtle rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-error/10 text-error rounded-xl">
                <AlertCircle className="w-5 h-5" />
              </div>
              <h4 className="font-display font-bold text-base text-on-surface">
                {isFR ? "Confirmer la suppression" : "Confirm Deletion"}
              </h4>
            </div>
            <p className="text-xs font-semibold text-on-surface-variant leading-relaxed">
              {isFR
                ? "Cette action est irréversible. L'e-mail en quarantaine sera définitivement effacé."
                : "This action is irreversible. The quarantined email will be permanently deleted."}
            </p>
            <div className="flex justify-end gap-2.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmDeleteId(null)}
                className="font-bold text-xs"
              >
                {isFR ? "Annuler" : "Cancel"}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={async () => {
                  const id = confirmDeleteId;
                  setConfirmDeleteId(null);
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
                }}
                className="font-bold text-xs"
              >
                {isFR ? "Supprimer" : "Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* footer text note */}
      <div className="pt-8 border-t border-border-subtle select-none">
        <p className="text-[12px] text-on-surface-variant font-medium leading-relaxed italic">
          Note: {t("quarantine.daily_digest_active")}
        </p>
      </div>
    </MotionDiv>
  );
}
