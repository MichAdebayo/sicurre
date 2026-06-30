import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  Bell,
  CheckCircle2,
  Trash2,
  Plus,
  Shield,
  Moon,
  History,
  AlertCircle,
  Inbox,
  Globe,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  useAlertPreferences,
  useUpdateAlertPreferences,
  useSecurityRules,
  useCreateSecurityRule,
  useDeleteSecurityRule,
  useAlertHistory,
  useDismissAlert,
} from "../lib/api";

const MotionDiv = motion.div as any;

export default function AlertsRoute() {
  const { t, i18n } = useTranslation();

  // Queries & Mutations
  const { data: preferences, isLoading: prefsLoading } = useAlertPreferences();
  const updatePrefsMutation = useUpdateAlertPreferences();

  const { data: rules, isLoading: rulesLoading } = useSecurityRules();
  const createRuleMutation = useCreateSecurityRule();
  const deleteRuleMutation = useDeleteSecurityRule();

  const { data: history, isLoading: historyLoading } = useAlertHistory();
  const dismissAlertMutation = useDismissAlert();

  // Form states
  const [notifyPhishing, setNotifyPhishing] = useState(true);
  const [notifySpam, setNotifySpam] = useState(false);
  const [quietEnabled, setQuietEnabled] = useState(false);
  const [quietStart, setQuietStart] = useState("22:00");
  const [quietEnd, setQuietEnd] = useState("07:00");

  const [ruleType, setRuleType] = useState<"whitelist" | "blocklist">("whitelist");
  const [rulePattern, setRulePattern] = useState("");

  const [prefsSuccess, setPrefsSuccess] = useState(false);
  const [prefsError, setPrefsError] = useState("");
  const [ruleError, setRuleError] = useState("");

  // Sync component state when preferences query finishes loading
  useState(() => {
    if (preferences) {
      setNotifyPhishing(preferences.notify_phishing);
      setNotifySpam(preferences.notify_spam);
      setQuietEnabled(preferences.quiet_hours_enabled);
      setQuietStart(preferences.quiet_hours_start);
      setQuietEnd(preferences.quiet_hours_end);
    }
  });

  // Sync state explicitly if query updates
  const handlePrefsSync = () => {
    if (preferences) {
      setNotifyPhishing(preferences.notify_phishing);
      setNotifySpam(preferences.notify_spam);
      setQuietEnabled(preferences.quiet_hours_enabled);
      setQuietStart(preferences.quiet_hours_start);
      setQuietEnd(preferences.quiet_hours_end);
    }
  };

  const handleSavePrefs = async (e: React.FormEvent) => {
    e.preventDefault();
    setPrefsSuccess(false);
    setPrefsError("");
    try {
      await updatePrefsMutation.mutateAsync({
        notify_phishing: notifyPhishing,
        notify_spam: notifySpam,
        quiet_hours_enabled: quietEnabled,
        quiet_hours_start: quietStart,
        quiet_hours_end: quietEnd,
      });
      setPrefsSuccess(true);
      setTimeout(() => setPrefsSuccess(false), 3000);
    } catch (err) {
      setPrefsError(err instanceof Error ? err.message : "Failed to save preferences.");
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    setRuleError("");
    if (!rulePattern.trim()) {
      setRuleError("Please enter a valid email or domain pattern.");
      return;
    }
    try {
      await createRuleMutation.mutateAsync({
        rule_type: ruleType,
        pattern: rulePattern.trim(),
      });
      setRulePattern("");
    } catch (err) {
      setRuleError(err instanceof Error ? err.message : "Failed to create rule.");
    }
  };

  const handleDeleteRule = async (id: string) => {
    try {
      await deleteRuleMutation.mutateAsync(id);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDismissAlert = async (id: string) => {
    try {
      await dismissAlertMutation.mutateAsync(id);
    } catch (err) {
      console.error(err);
    }
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
      <div className="pb-6 border-b border-border-subtle flex items-center justify-between">
        <div>
          <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
            {t("alerts.title")}
          </h1>
          <p className="text-sm text-on-surface-variant mt-1">
            {t("alerts.subtitle")}
          </p>
        </div>
        {preferences && (
          <Button variant="outline" size="sm" onClick={handlePrefsSync} className="text-xs">
            Reset Form
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Hand: Preference Controls */}
        <div className="lg:col-span-7 space-y-6">
          {/* Email Notification Toggles */}
          <form onSubmit={handleSavePrefs} className="bg-white rounded-xl border border-border-subtle p-6 space-y-6 shadow-sm">
            <div className="flex items-center gap-2.5 pb-4 border-b border-border-subtle">
              <Bell className="w-5 h-5 text-primary" />
              <h3 className="font-display font-semibold text-[17px] text-on-surface">
                {t("alerts.section_preferences")}
              </h3>
            </div>

            {prefsLoading ? (
              <div className="h-20 bg-surface-low rounded-xl animate-pulse" />
            ) : (
              <div className="space-y-4">
                <label className="flex items-start gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={notifyPhishing}
                    onChange={(e) => setNotifyPhishing(e.target.checked)}
                    className="w-4 h-4 mt-1 rounded text-primary border-border-subtle focus:ring-primary/20 accent-primary"
                  />
                  <div>
                    <span className="text-sm font-semibold text-on-surface group-hover:text-primary transition-colors">
                      {t("alerts.notify_phishing")}
                    </span>
                    <p className="text-xs text-on-surface-variant/70 mt-0.5">
                      Sends immediate push alerts to your professional mail for high-risk flags.
                    </p>
                  </div>
                </label>

                <label className="flex items-start gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={notifySpam}
                    onChange={(e) => setNotifySpam(e.target.checked)}
                    className="w-4 h-4 mt-1 rounded text-primary border-border-subtle focus:ring-primary/20 accent-primary"
                  />
                  <div>
                    <span className="text-sm font-semibold text-on-surface group-hover:text-primary transition-colors">
                      {t("alerts.notify_spam")}
                    </span>
                    <p className="text-xs text-on-surface-variant/70 mt-0.5">
                      Daily summary digest for commercial advertiser spam.
                    </p>
                  </div>
                </label>
              </div>
            )}

            {/* Quiet Hours */}
            <div className="space-y-4 pt-4 border-t border-border-subtle/50">
              <div className="flex items-center gap-2">
                <Moon className="w-4 h-4 text-primary" />
                <h4 className="text-sm font-bold text-on-surface">
                  {t("alerts.section_quiet_hours")}
                </h4>
              </div>

              <div className="space-y-3 bg-surface-low/30 rounded-xl p-4 border border-border-subtle/40">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={quietEnabled}
                    onChange={(e) => setQuietEnabled(e.target.checked)}
                    className="w-4 h-4 rounded text-primary focus:ring-primary/20 accent-primary"
                  />
                  <span className="text-sm font-semibold text-on-surface">
                    {t("alerts.quiet_hours_enabled")}
                  </span>
                </label>

                {quietEnabled && (
                  <div className="grid grid-cols-2 gap-4 pt-2">
                    <div>
                      <label className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider block mb-1">
                        {t("alerts.quiet_hours_start")}
                      </label>
                      <input
                        type="time"
                        value={quietStart}
                        onChange={(e) => setQuietStart(e.target.value)}
                        className="w-full px-3 py-2 bg-white border border-border-subtle rounded-lg text-sm outline-none focus:border-primary"
                      />
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider block mb-1">
                        {t("alerts.quiet_hours_end")}
                      </label>
                      <input
                        type="time"
                        value={quietEnd}
                        onChange={(e) => setQuietEnd(e.target.value)}
                        className="w-full px-3 py-2 bg-white border border-border-subtle rounded-lg text-sm outline-none focus:border-primary"
                      />
                    </div>
                  </div>
                )}
                <p className="text-[11px] text-on-surface-variant/60 leading-relaxed">
                  {t("alerts.quiet_hours_desc")}
                </p>
              </div>
            </div>

            {prefsSuccess && (
              <div className="p-3 bg-safe/10 border border-safe/25 text-safe text-xs font-semibold rounded-lg flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" />
                <span>{t("alerts.preferences_saved")}</span>
              </div>
            )}
            {prefsError && <p className="text-xs text-error font-semibold">{prefsError}</p>}

            <div className="flex justify-end pt-2">
              <Button type="submit" className="text-xs font-bold uppercase tracking-wider">
                {t("alerts.save_preferences")}
              </Button>
            </div>
          </form>

          {/* Filtering Rules list */}
          <div className="bg-white rounded-xl border border-border-subtle p-6 space-y-6 shadow-sm">
            <div className="flex items-center gap-2.5 pb-4 border-b border-border-subtle">
              <Shield className="w-5 h-5 text-primary" />
              <h3 className="font-display font-semibold text-[17px] text-on-surface">
                {t("alerts.section_rules")}
              </h3>
            </div>

            <form onSubmit={handleCreateRule} className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end bg-surface-low/30 rounded-xl p-4 border border-border-subtle/50">
              <div className="sm:col-span-4">
                <label className="text-[11px] font-bold text-on-surface-variant uppercase block mb-1.5">
                  {t("alerts.rule_type")}
                </label>
                <select
                  value={ruleType}
                  onChange={(e) => setRuleType(e.target.value as any)}
                  className="w-full px-3 py-2 bg-white border border-border-subtle rounded-lg text-sm focus:outline-none focus:border-primary cursor-pointer"
                >
                  <option value="whitelist">{t("alerts.whitelist")}</option>
                  <option value="blocklist">{t("alerts.blocklist")}</option>
                </select>
              </div>
              <div className="sm:col-span-6">
                <label className="text-[11px] font-bold text-on-surface-variant uppercase block mb-1.5">
                  {t("alerts.pattern")}
                </label>
                <Input
                  type="text"
                  placeholder="client@company.com or company.com"
                  value={rulePattern}
                  onChange={(e) => setRulePattern(e.target.value)}
                  className="bg-white"
                />
              </div>
              <div className="sm:col-span-2">
                <Button type="submit" className="w-full flex items-center justify-center py-2.5">
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
            </form>
            {ruleError && <p className="text-xs text-error font-semibold px-2">{ruleError}</p>}

            <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
              {rulesLoading ? (
                <div className="h-16 bg-surface-low rounded-xl animate-pulse" />
              ) : !rules || rules.length === 0 ? (
                <div className="text-center py-8 text-sm text-on-surface-variant/50">
                  {t("alerts.no_rules")}
                </div>
              ) : (
                rules.map((rule) => (
                  <div
                    key={rule.id}
                    className={`flex items-center justify-between p-3.5 rounded-xl border ${
                      rule.rule_type === "whitelist"
                        ? "bg-safe/[0.02] border-safe/10"
                        : "bg-error/[0.02] border-error/10"
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md uppercase ${
                          rule.rule_type === "whitelist" ? "bg-safe/10 text-safe" : "bg-error/10 text-error"
                        }`}>
                          {rule.rule_type === "whitelist"
                            ? (i18n.language === "fr" ? "Autoriser" : "Allow")
                            : (i18n.language === "fr" ? "Bloquer" : "Block")}
                        </span>
                        <span className="text-sm font-semibold text-on-surface select-all">
                          {rule.pattern}
                        </span>
                      </div>
                      <p className="text-[11px] text-on-surface-variant/50">
                        {rule.rule_type === "whitelist" ? t("alerts.whitelist_desc") : t("alerts.blocklist_desc")}
                      </p>
                    </div>

                    <button
                      onClick={() => handleDeleteRule(rule.id)}
                      className="p-1.5 rounded-md hover:bg-surface-low hover:text-error text-on-surface-variant/50 transition-colors cursor-pointer"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Hand: Alert History Log */}
        <div className="lg:col-span-5 bg-white rounded-xl border border-border-subtle p-6 space-y-6 shadow-sm">
          <div className="flex items-center gap-2.5 pb-4 border-b border-border-subtle">
            <History className="w-5 h-5 text-primary" />
            <h3 className="font-display font-semibold text-[17px] text-on-surface">
              {t("alerts.section_history")}
            </h3>
          </div>

          {historyLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-surface-low rounded-xl animate-pulse" />
              ))}
            </div>
          ) : !history || history.length === 0 ? (
            <div className="text-center py-12 text-sm text-on-surface-variant/50 flex flex-col items-center justify-center">
              <CheckCircle2 className="w-8 h-8 text-safe/40 mb-2" />
              <p>{t("alerts.no_history")}</p>
            </div>
          ) : (
            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
              {history.map((alert) => (
                <div
                  key={alert.id}
                  className="p-4 rounded-xl border border-border-subtle/80 bg-surface-low/30 hover:bg-surface-low/60 transition-colors flex items-start justify-between gap-3"
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-3.5 h-3.5 text-error shrink-0" />
                      <span className="font-mono text-[10px] text-on-surface-variant/60">
                        {new Date(alert.created_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>
                    <p className="text-xs font-bold text-on-surface truncate">{alert.title}</p>
                    <p className="text-[11px] text-on-surface-variant/70 leading-relaxed">{alert.message}</p>
                  </div>
                  <button
                    onClick={() => handleDismissAlert(alert.id)}
                    className="text-[10px] font-bold text-primary hover:text-primary-hover px-2 py-1 rounded bg-primary/5 hover:bg-primary/10 transition-colors cursor-pointer shrink-0"
                  >
                    {t("alerts.dismiss_alert")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </MotionDiv>
  );
}
