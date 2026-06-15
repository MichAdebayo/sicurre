import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ShieldAlert,
  ShieldCheck,
  MailWarning,
  Trash2,
  RotateCcw,
  LayoutDashboard,
  FileText,
  Mail,
  Database,
  Settings,
  LogOut,
  Search,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Eye,
  EyeOff
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

const MotionDiv = motion.div as any;
import {
  useKPIStats,
  useThreatLogs,
  useUpdateThreatStatus,
  useDatasets,
  useRunPipeline,
  ThreatLog
} from "./lib/api";

// --- CUSTOM VERDICT BADGE COMPONENT ---
function VerdictBadge({ verdict, confidence }: { verdict: "phishing" | "spam" | "legitimate"; confidence: number }) {
  const { t } = useTranslation();
  
  let bgClass = "bg-green-50 text-green-700 border-green-200";
  let Icon = ShieldCheck;
  let label = t("threats.badge_legitimate");

  if (verdict === "phishing") {
    bgClass = "bg-amber-50 text-amber-700 border-amber-200";
    Icon = ShieldAlert;
    label = t("threats.badge_phishing");
  } else if (verdict === "spam") {
    bgClass = "bg-yellow-50 text-yellow-700 border-yellow-200";
    Icon = MailWarning;
    label = t("threats.badge_spam");
  }

  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${bgClass}`}>
      <Icon className="w-3.5 h-3.5 stroke-[1.5]" />
      <span>{label}</span>
      <span className="font-mono opacity-85 ml-0.5">{(confidence * 100).toFixed(0)} %</span>
    </div>
  );
}

export default function App() {
  const { t } = useTranslation();
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem("sicurre_session_token"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState(false);
  
  const [activeTab, setActiveTab] = useState<"dashboard" | "threats" | "smail" | "datasets" | "settings">("dashboard");

  // Handle Login
  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (email === "admin@sicurre.fr" && password === "sicurre2026") {
      localStorage.setItem("sicurre_session_token", "mock-token-12345");
      localStorage.setItem("sicurre_user_name", "Administrateur Sicurre");
      setIsLoggedIn(true);
      setLoginError(false);
    } else {
      setLoginError(true);
    }
  };

  // Handle Logout
  const handleLogout = () => {
    localStorage.removeItem("sicurre_session_token");
    localStorage.removeItem("sicurre_user_name");
    setIsLoggedIn(false);
  };

  if (!isLoggedIn) {
    // --- SLEEK SAAS LOGIN SCREEN (Inspired by ShieldProX / Hexon) ---
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0B0F19] relative overflow-hidden">
        {/* Subtle geometric neon lines backdrop */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f293710_1px,transparent_1px),linear-gradient(to_bottom,#1f293710_1px,transparent_1px)] bg-[size:4rem_4rem]"></div>
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-[120px] pointer-events-none"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[120px] pointer-events-none"></div>

        <MotionDiv 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          className="w-full max-w-md p-8 bg-[#111827]/90 border border-slate-800 rounded-2xl shadow-2xl relative z-10 backdrop-blur-md"
        >
          <div className="flex flex-col items-center mb-8">
            <div className="w-12 h-12 bg-primary/20 rounded-xl flex items-center justify-center border border-primary/30 mb-3">
              <ShieldAlert className="w-6 h-6 text-primary" />
            </div>
            <h1 className="text-3xl font-display font-bold text-white tracking-tight">Sicurre</h1>
            <p className="text-sm text-slate-400 mt-1">{t("login.subtitle")}</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                {t("login.email_label")}
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nom@entreprise.fr"
                className="w-full px-4 py-3 bg-slate-900 border border-slate-700 text-white rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary text-sm transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                {t("login.password_label")}
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-700 text-white rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary text-sm transition-all pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3.5 text-slate-400 hover:text-white transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {loginError && (
              <MotionDiv 
                initial={{ opacity: 0 }} 
                animate={{ opacity: 1 }} 
                className="p-3 bg-red-950/40 border border-red-800 text-red-400 text-xs rounded-lg"
              >
                {t("login.error_invalid")}
              </MotionDiv>
            )}

            <button
              type="submit"
              className="w-full py-3 bg-accent hover:bg-accent-dark text-slate-950 font-semibold rounded-lg shadow-lg hover:shadow-accent/20 active:scale-[0.98] transition-all text-sm mt-2 cursor-pointer"
            >
              {t("login.button")}
            </button>
          </form>
        </MotionDiv>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex">
      {/* --- SIDEBAR LAYOUT (Glassmorphic Midnight Style) --- */}
      <aside className="w-64 bg-[#0B0F19] border-r border-slate-800 flex flex-col justify-between shrink-0">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-8 h-8 bg-primary/20 rounded-lg flex items-center justify-center border border-primary/30">
              <ShieldAlert className="w-4.5 h-4.5 text-primary" />
            </div>
            <span className="text-lg font-display font-bold text-white">Sicurre</span>
          </div>

          <nav className="space-y-1">
            <SidebarButton
              icon={<LayoutDashboard />}
              label={t("common.dashboard")}
              active={activeTab === "dashboard"}
              onClick={() => setActiveTab("dashboard")}
            />
            <SidebarButton
              icon={<FileText />}
              label={t("common.threat_log")}
              active={activeTab === "threats"}
              onClick={() => setActiveTab("threats")}
            />
            <SidebarButton
              icon={<Mail />}
              label={t("common.smail_simulator")}
              active={activeTab === "smail"}
              onClick={() => setActiveTab("smail")}
            />
            <SidebarButton
              icon={<Database />}
              label={t("common.datasets")}
              active={activeTab === "datasets"}
              onClick={() => setActiveTab("datasets")}
            />
            <SidebarButton
              icon={<Settings />}
              label={t("common.settings")}
              active={activeTab === "settings"}
              onClick={() => setActiveTab("settings")}
            />
          </nav>
        </div>

        <div className="p-6 border-t border-slate-800 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-slate-800 rounded-full flex items-center justify-center text-xs font-semibold text-white">
              A
            </div>
            <div>
              <p className="text-xs text-slate-400">{t("sidebar.connected_as")}</p>
              <p className="text-sm font-semibold text-white truncate max-w-[140px]">
                {localStorage.getItem("sicurre_user_name") || "Admin"}
              </p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-3 py-2 bg-slate-900 hover:bg-red-950/30 border border-slate-800 text-slate-300 hover:text-red-400 rounded-lg text-xs font-medium transition-all cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
            <span>{t("common.logout")}</span>
          </button>
        </div>
      </aside>

      {/* --- MAIN CONTENT AREA --- */}
      <main className="flex-1 overflow-y-auto p-10 bg-slate-50">
        <AnimatePresence mode="wait">
          {activeTab === "dashboard" && <DashboardView />}
          {activeTab === "threats" && <ThreatsView />}
          {activeTab === "smail" && <SmailView />}
          {activeTab === "datasets" && <DatasetsView />}
          {activeTab === "settings" && <SettingsView />}
        </AnimatePresence>
      </main>
    </div>
  );
}

// --- SIDEBAR BUTTON HELPER ---
function SidebarButton({
  icon,
  label,
  active,
  onClick
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 cursor-pointer relative ${
        active 
          ? "text-white bg-primary/20 border border-primary/20" 
          : "text-slate-400 hover:text-white hover:bg-slate-800/40 border border-transparent"
      }`}
    >
      {active && (
        <MotionDiv 
          layoutId="sidebar-active"
          className="absolute left-0 w-1 h-5 bg-primary rounded-r"
        />
      )}
      <span className="stroke-[1.5]">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

// --- VIEW COMPONENTS ---

// 1. Dashboard View
function DashboardView() {
  const { t } = useTranslation();
  const { data: kpis, isLoading: kpisLoading } = useKPIStats();
  const { data: threats, isLoading: threatsLoading } = useThreatLogs();

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-3xl font-display font-bold text-slate-900">
          {t("dashboard.welcome")} {localStorage.getItem("sicurre_user_name") || "Utilisateur"}
        </h2>
        <p className="text-sm text-slate-500 mt-1">{t("dashboard.subtitle")}</p>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-3 gap-6">
        <KPICard
          title={t("dashboard.kpi_raw")}
          value={kpisLoading ? "..." : kpis?.raw_records_count?.toLocaleString() || "0"}
          description="Total des données brutes"
          accent
        />
        <KPICard
          title={t("dashboard.kpi_normalized")}
          value={kpisLoading ? "..." : kpis?.normalized_messages_count?.toLocaleString() || "0"}
          description="Flux normalisé"
        />
        <KPICard
          title={t("dashboard.kpi_dataset")}
          value={kpisLoading ? "..." : kpis?.dataset_items_count?.toLocaleString() || "0"}
          description="Éléments exportés"
        />
      </div>

      <div className="grid grid-cols-3 gap-8">
        {/* Recent Activity */}
        <div className="col-span-2 bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="text-base font-semibold text-slate-900">{t("dashboard.recent_activity")}</h3>
          
          {threatsLoading ? (
            <p className="text-sm text-slate-400">{t("common.loading")}</p>
          ) : !threats || threats.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">{t("dashboard.no_threats")}</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {threats.slice(0, 5).map((threat) => (
                <div key={threat.id} className="py-3.5 flex items-center justify-between gap-4">
                  <div className="truncate">
                    <p className="text-sm font-medium text-slate-900 truncate">{threat.subject}</p>
                    <p className="text-xs text-slate-500 mt-0.5">Reçu le {new Date(threat.received_at).toLocaleDateString("fr-FR")}</p>
                  </div>
                  <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Verdict Distribution Panel */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="text-base font-semibold text-slate-900">{t("dashboard.verdict_distribution")}</h3>
          {kpisLoading ? (
            <p className="text-sm text-slate-400">{t("common.loading")}</p>
          ) : (
            <div className="space-y-4 pt-2">
              <DistributionBar
                label={t("threats.badge_phishing")}
                count={kpis?.threats_phishing_count || 0}
                total={kpis?.normalized_messages_count || 1}
                colorClass="bg-amber-500"
              />
              <DistributionBar
                label={t("threats.badge_spam")}
                count={kpis?.threats_spam_count || 0}
                total={kpis?.normalized_messages_count || 1}
                colorClass="bg-yellow-500"
              />
              <DistributionBar
                label={t("threats.badge_legitimate")}
                count={kpis?.threats_legitimate_count || 0}
                total={kpis?.normalized_messages_count || 1}
                colorClass="bg-green-500"
              />
            </div>
          )}
        </div>
      </div>
    </MotionDiv>
  );
}

function KPICard({ title, value, description, accent }: { title: string; value: string; description: string; accent?: boolean }) {
  return (
    <div className={`p-6 rounded-xl border shadow-sm ${
      accent 
        ? "bg-gradient-to-br from-primary-light to-white border-primary-light/40" 
        : "bg-white border-slate-200"
    }`}>
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{title}</p>
      <p className="text-3xl font-display font-bold text-slate-900 mt-2">{value}</p>
      <p className="text-xs text-slate-400 mt-1">{description}</p>
    </div>
  );
}

function DistributionBar({ label, count, total, colorClass }: { label: string; count: number; total: number; colorClass: string }) {
  const percentage = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs font-medium">
        <span className="text-slate-600">{label}</span>
        <span className="text-slate-900 font-mono">{count} ({percentage.toFixed(0)}%)</span>
      </div>
      <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${percentage}%` }}></div>
      </div>
    </div>
  );
}

// 2. Threats View
function ThreatsView() {
  const { t } = useTranslation();
  const { data: threats, isLoading } = useThreatLogs();
  const updateStatus = useUpdateThreatStatus();
  
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filteredThreats = threats?.filter(t => 
    t.subject.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];

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

      <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl px-4 py-3 shadow-sm max-w-md">
        <Search className="w-4 h-4 text-slate-400" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder={t("threats.search_placeholder")}
          className="bg-transparent border-none outline-none text-sm w-full text-slate-800 placeholder-slate-400"
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-sm text-slate-400">{t("common.loading")}</div>
        ) : filteredThreats.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">{t("dashboard.no_threats")}</div>
        ) : (
          <div className="divide-y divide-slate-100">
            <AnimatePresence>
              {filteredThreats.map((threat) => (
                <div key={threat.id} className="p-4 space-y-3">
                  <div className="flex items-center justify-between gap-4">
                    <div 
                      className="flex-1 cursor-pointer flex items-center gap-2 truncate"
                      onClick={() => setExpandedId(expandedId === threat.id ? null : threat.id)}
                    >
                      {expandedId === threat.id ? <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />}
                      <span className="text-sm font-medium text-slate-900 truncate hover:text-primary transition-colors">
                        {threat.subject}
                      </span>
                    </div>

                    <div className="flex items-center gap-4 shrink-0">
                      <VerdictBadge verdict={threat.verdict} confidence={threat.confidence} />
                      <span className="text-xs text-slate-500">{new Date(threat.received_at).toLocaleDateString("fr-FR")}</span>
                      
                      {threat.status === "trashed" ? (
                        <button
                          onClick={() => updateStatus.mutate({ id: threat.id, status: "restored" })}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-green-50 hover:bg-green-100 border border-green-200 text-green-700 rounded-lg text-xs font-semibold cursor-pointer transition-colors"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>{t("threats.action_restore")}</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => updateStatus.mutate({ id: threat.id, status: "trashed" })}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 hover:bg-red-100 border border-red-200 text-red-700 rounded-lg text-xs font-semibold cursor-pointer transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span>{t("threats.action_trash")}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {expandedId === threat.id && (
                    <MotionDiv
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="text-xs text-slate-600 bg-slate-50 rounded-lg p-3 border border-slate-100 leading-relaxed font-sans"
                    >
                      {threat.body_preview || "Aucun contenu de prévisualisation disponible."}
                    </MotionDiv>
                  )}
                </div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </MotionDiv>
  );
}

// 3. Smail Simulation View (Smail Simulator)
function SmailView() {
  const { t } = useTranslation();
  const [emails, setEmails] = useState<ThreatLog[]>([
    {
      id: "sim-1",
      message_id: "msg-11",
      subject: "⚠ URGET : Mise à jour de votre abonnement Simplon",
      body_preview: "Cher affilié, votre compte a expiré. Veuillez mettre à jour vos coordonnées de paiement en urgence sur le lien sous 24h.",
      verdict: "phishing",
      confidence: 0.98,
      status: "active",
      received_at: new Date().toISOString()
    },
    {
      id: "sim-2",
      message_id: "msg-22",
      subject: "Félicitations, vous avez gagné un chèque cadeau de 500€",
      body_preview: "Cliquez ici pour récupérer votre bon d'achat Amazon gratuit immédiatement.",
      verdict: "spam",
      confidence: 0.82,
      status: "active",
      received_at: new Date().toISOString()
    },
    {
      id: "sim-3",
      message_id: "msg-33",
      subject: "Rapport d'activité mensuel - Sicurre SAS",
      body_preview: "Bonjour Michael, voici le récapitulatif complet de vos statistiques de filtrage pour le mois dernier. N'hésitez pas à nous contacter.",
      verdict: "legitimate",
      confidence: 0.99,
      status: "active",
      received_at: new Date().toISOString()
    }
  ]);

  const [selectedId, setSelectedId] = useState<string>("sim-1");
  const selectedEmail = emails.find(e => e.id === selectedId);

  const reclassify = (id: string, newVerdict: "phishing" | "spam" | "legitimate") => {
    setEmails(prev => prev.map(e => {
      if (e.id === id) {
        return { ...e, verdict: newVerdict, confidence: 1.0 };
      }
      return e;
    }));
  };

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-6 h-full"
    >
      <div>
        <h2 className="text-3xl font-display font-bold text-slate-900">{t("smail.title")}</h2>
        <p className="text-sm text-slate-500 mt-1">{t("smail.subtitle")}</p>
      </div>

      <div className="grid grid-cols-3 gap-8 h-[550px] items-stretch">
        {/* Email Inbox Sidebar */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-y-auto divide-y divide-slate-100">
          {emails.map((e) => (
            <div
              key={e.id}
              onClick={() => setSelectedId(e.id)}
              className={`p-4 cursor-pointer transition-colors ${selectedId === e.id ? "bg-primary-light/30" : "hover:bg-slate-50"}`}
            >
              <p className="text-sm font-medium text-slate-900 truncate">{e.subject}</p>
              <div className="flex justify-between items-center mt-2.5">
                <span className="text-[10px] text-slate-400">Reçu à l'instant</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold border ${
                  e.verdict === "phishing" ? "bg-amber-50 border-amber-200 text-amber-700" :
                  e.verdict === "spam" ? "bg-yellow-50 border-yellow-200 text-yellow-700" :
                  "bg-green-50 border-green-200 text-green-700"
                }`}>
                  {e.verdict}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Email Content Panel */}
        <div className="col-span-2 bg-white border border-slate-200 rounded-xl shadow-sm p-6 flex flex-col justify-between">
          {selectedEmail ? (
            <div className="space-y-6 flex-1 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="border-b border-slate-100 pb-4">
                  <h3 className="text-base font-semibold text-slate-900">{selectedEmail.subject}</h3>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-xs text-slate-500">Expéditeur: inconnu</span>
                    <VerdictBadge verdict={selectedEmail.verdict} confidence={selectedEmail.confidence} />
                  </div>
                </div>

                <div className="text-sm text-slate-700 bg-slate-50 border border-slate-100 rounded-lg p-5 leading-relaxed min-h-[150px] font-sans">
                  {selectedEmail.body_preview}
                </div>

                {/* Status bar */}
                <div className="p-3 bg-slate-50 rounded-lg flex items-center gap-2 border border-slate-100">
                  <span className="text-xs font-semibold text-slate-500">Classification Sicurre:</span>
                  <span className="text-xs text-slate-700">
                    {selectedEmail.verdict === "phishing" ? t("smail.verdict_phishing_desc") :
                     selectedEmail.verdict === "spam" ? t("smail.verdict_spam_desc") :
                     t("smail.verdict_safe_desc")}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3 pt-4 border-t border-slate-100">
                <button
                  onClick={() => reclassify(selectedEmail.id, "phishing")}
                  className="flex-1 py-2.5 bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-700 font-semibold rounded-lg text-xs transition-colors cursor-pointer"
                >
                  {t("smail.report_phishing")}
                </button>
                <button
                  onClick={() => reclassify(selectedEmail.id, "spam")}
                  className="flex-1 py-2.5 bg-yellow-50 hover:bg-yellow-100 border border-yellow-200 text-yellow-700 font-semibold rounded-lg text-xs transition-colors cursor-pointer"
                >
                  {t("smail.report_spam")}
                </button>
                <button
                  onClick={() => reclassify(selectedEmail.id, "legitimate")}
                  className="flex-1 py-2.5 bg-green-50 hover:bg-green-100 border border-green-200 text-green-700 font-semibold rounded-lg text-xs transition-colors cursor-pointer"
                >
                  {t("smail.mark_safe")}
                </button>
              </div>
            </div>
          ) : (
            <div className="text-center text-sm text-slate-400 py-12">{t("smail.empty_inbox")}</div>
          )}
        </div>
      </div>
    </MotionDiv>
  );
}

// 4. Datasets View
function DatasetsView() {
  const { t } = useTranslation();
  const { data: datasets, isLoading } = useDatasets();
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

        <button
          onClick={() => runPipeline.mutate()}
          disabled={runPipeline.isPending}
          className="flex items-center gap-2 px-4 py-2.5 bg-accent hover:bg-accent-dark text-slate-950 rounded-lg text-sm font-semibold shadow-lg hover:shadow-accent/20 cursor-pointer disabled:opacity-50 transition-all active:scale-[0.98]"
        >
          <RefreshCw className={`w-4 h-4 ${runPipeline.isPending ? "animate-spin" : ""}`} />
          <span>{runPipeline.isPending ? t("datasets.pipeline_running") : t("datasets.pipeline_run")}</span>
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-sm text-slate-400">{t("common.loading")}</div>
        ) : !datasets || datasets.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">Aucun jeu de données disponible.</div>
        ) : (
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
                  <td className="p-4 text-sm text-slate-700">{d.item_count.toLocaleString()}</td>
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
        )}
      </div>
    </MotionDiv>
  );
}

// 5. Settings View
function SettingsView() {
  const { t } = useTranslation();
  const [apiKey, setApiKey] = useState("48750ed5c9beabfc28bd085dbdff9de6264962d94dc235c98cfff7849c88dd45");
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
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-4">
          <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-2">
            {t("settings.section_api")}
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">{t("settings.api_key_label")}</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">{t("settings.api_url_label")}</label>
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all font-mono"
              />
            </div>
          </div>
        </div>

        {/* In-App Scheduler Settings Section */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-4">
          <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-2">
            {t("settings.section_scheduler")}
          </h3>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="block text-xs font-medium text-slate-600">{t("settings.scheduler_enabled")}</label>
                <p className="text-[10px] text-slate-400 mt-0.5">Met en marche le daemon d'ingestion automatique.</p>
              </div>
              <input
                type="checkbox"
                checked={schedulerEnabled}
                onChange={(e) => setSchedulerEnabled(e.target.checked)}
                className="w-4 h-4 border-slate-300 text-primary focus:ring-primary"
              />
            </div>

            {schedulerEnabled && (
              <MotionDiv
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="pt-2"
              >
                <label className="block text-xs font-medium text-slate-600 mb-1.5">{t("settings.scheduler_interval")}</label>
                <input
                  type="number"
                  value={schedulerInterval}
                  onChange={(e) => setSchedulerInterval(Number(e.target.value))}
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                />
              </MotionDiv>
            )}
          </div>
        </div>

        {saveStatus && (
          <MotionDiv
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="p-3 bg-green-50 border border-green-200 text-green-700 text-xs rounded-lg font-medium"
          >
            {t("settings.save_success")}
          </MotionDiv>
        )}

        <button
          type="submit"
          className="px-5 py-2.5 bg-primary hover:bg-primary-dark text-white rounded-lg text-sm font-semibold shadow-md hover:shadow-primary/20 active:scale-[0.98] transition-all cursor-pointer"
        >
          {t("common.save")}
        </button>
      </form>
    </MotionDiv>
  );
}
