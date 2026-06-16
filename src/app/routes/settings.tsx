import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Settings2, ShieldCheck, Save } from "lucide-react";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";

const MotionDiv = motion.div as any;

export default function SettingsRoute() {
  const { t } = useTranslation();
  const [apiKey, setApiKey] = useState("");
  const [apiUrl, setApiUrl] = useState("http://localhost:8000/v1/classify");
  const [schedulerEnabled, setSchedulerEnabled] = useState(false);
  const [schedulerInterval, setSchedulerInterval] = useState(604800);
  const [saveStatus, setSaveStatus] = useState(false);

  const saveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    setSaveStatus(true);
    setTimeout(() => setSaveStatus(false), 3000);
  };

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-6 max-w-2xl"
    >
      <div>
        <h2 className="text-3xl font-display font-bold text-slate-900">{t("settings.title")}</h2>
        <p className="text-sm text-slate-500 mt-1">{t("settings.subtitle")}</p>
      </div>

      <form onSubmit={saveSettings} className="space-y-6">
        {/* API Settings Section */}
        <Card className="space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Settings2 className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-slate-900">
              {t("settings.section_api")}
            </h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">
                {t("settings.api_key_label")}
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">
                {t("settings.api_url_label")}
              </label>
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all font-mono"
              />
            </div>
          </div>
        </Card>

        {/* In-App Scheduler Settings Section */}
        <Card className="space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <ShieldCheck className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-slate-900">
              {t("settings.section_scheduler")}
            </h3>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="block text-xs font-medium text-slate-700">{t("settings.scheduler_enabled")}</label>
                <p className="text-[10px] text-slate-400 mt-0.5">Met en marche le daemon d'ingestion automatique.</p>
              </div>
              <input
                type="checkbox"
                checked={schedulerEnabled}
                onChange={(e) => setSchedulerEnabled(e.target.checked)}
                className="w-4 h-4 rounded border-slate-300 text-primary focus:ring-primary cursor-pointer"
              />
            </div>

            {schedulerEnabled && (
              <MotionDiv
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="pt-2"
              >
                <label className="block text-xs font-medium text-slate-700 mb-1.5">{t("settings.scheduler_interval")}</label>
                <input
                  type="number"
                  value={schedulerInterval}
                  onChange={(e) => setSchedulerInterval(Number(e.target.value))}
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                />
              </MotionDiv>
            )}
          </div>
        </Card>

        {saveStatus && (
          <MotionDiv
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="p-3 bg-green-50 border border-green-200 text-green-700 text-xs rounded-lg font-medium"
          >
            {t("settings.save_success")}
          </MotionDiv>
        )}

        <Button
          type="submit"
          variant="primary"
          className="flex items-center gap-2 px-5 py-2.5 shadow-md"
        >
          <Save className="w-4 h-4" />
          <span>{t("common.save")}</span>
        </Button>
      </form>
    </MotionDiv>
  );
}
