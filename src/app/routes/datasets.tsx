import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { RefreshCw, Database, FileText, BarChart3 } from "lucide-react";
import { useDatasets, useRunPipeline, useKPIStats } from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";

const MotionDiv = motion.div as any;

export default function DatasetsRoute() {
  const { t } = useTranslation();
  const { data: datasets, isLoading: datasetsLoading } = useDatasets();
  const { data: stats, isLoading: statsLoading } = useKPIStats();
  const runPipeline = useRunPipeline();

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-3xl font-display font-bold text-slate-900">{t("datasets.title")}</h2>
          <p className="text-sm text-slate-500 mt-1">{t("datasets.subtitle")}</p>
        </div>

        <Button
          onClick={() => runPipeline.mutate()}
          disabled={runPipeline.isPending}
          variant="primary"
          className="active:scale-[0.98] transition-all"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${runPipeline.isPending ? "animate-spin" : ""}`} />
          <span>{runPipeline.isPending ? t("datasets.pipeline_running") : t("datasets.pipeline_run")}</span>
        </Button>
      </div>

      {/* KPI Cards Row (Corrected to show the real dataset items) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {t("dashboard.kpi_raw")}
              </span>
              <FileText className="w-4 h-4 text-slate-400" />
            </div>
            <p className="text-3xl font-display font-bold text-slate-900">
              {statsLoading ? "..." : stats?.raw_records_count?.toLocaleString() || "0"}
            </p>
          </div>
          <p className="text-xs text-slate-400 mt-2">Total des données brutes</p>
        </Card>

        <Card className="flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {t("dashboard.kpi_normalized")}
              </span>
              <BarChart3 className="w-4 h-4 text-slate-400" />
            </div>
            <p className="text-3xl font-display font-bold text-slate-900">
              {statsLoading ? "..." : stats?.normalized_messages_count?.toLocaleString() || "0"}
            </p>
          </div>
          <p className="text-xs text-slate-400 mt-2">Flux normalisé</p>
        </Card>

        <Card className="flex flex-col justify-between border-primary/20 bg-gradient-to-br from-primary-light to-white">
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-semibold text-primary uppercase tracking-wider">
                {t("dashboard.kpi_dataset")}
              </span>
              <Database className="w-4 h-4 text-primary" />
            </div>
            <p className="text-3xl font-display font-bold text-slate-900">
              {statsLoading ? "..." : stats?.dataset_items_count?.toLocaleString() || "0"}
            </p>
          </div>
          <p className="text-xs text-slate-400 mt-2">Éléments réels exportés dans le dataset</p>
        </Card>
      </div>

      {/* Dataset Version Table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        {datasetsLoading ? (
          <div className="p-8 text-center text-sm text-slate-400">{t("common.loading")}</div>
        ) : !datasets || datasets.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">Aucun jeu de données disponible.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t("datasets.table_version")}</th>
                  <th className="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t("datasets.table_items")}</th>
                  <th className="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t("datasets.table_status")}</th>
                  <th className="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t("datasets.table_published")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {datasets.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="p-4 text-sm font-medium text-slate-900 font-mono">{d.version_tag}</td>
                    <td className="p-4 text-sm text-slate-700 font-mono">{d.item_count.toLocaleString()}</td>
                    <td className="p-4 text-sm">
                      <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                        d.status === "frozen" ? "bg-green-50 border-green-200 text-green-700" : "bg-blue-50 border-blue-200 text-blue-700"
                      }`}>
                        {d.status === "frozen" ? t("datasets.status_frozen") : t("datasets.status_draft")}
                      </span>
                    </td>
                    <td className="p-4 text-sm text-slate-500">
                      {d.published_at ? new Date(d.published_at).toLocaleString("fr-FR") : t("datasets.not_published")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </MotionDiv>
  );
}
