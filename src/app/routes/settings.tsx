import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  User,
  Key,
  Bell,
  Trash2,
  Plus,
  Save,
  CheckCircle2,
  RefreshCw,
  ShieldCheck,
  Fingerprint,
  Smartphone,
  Clock,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Toggle } from "../components/ui/toggle";

const MotionDiv = motion.div as any;

export default function SettingsRoute() {
  const { t } = useTranslation();
  const [name, setName] = useState(localStorage.getItem("sicurre_user_name") || "Michael");
  const [email, setEmail] = useState("admin@sicurre.fr");
  const [jobTitle, setJobTitle] = useState("Directeur Sécurité / CISO");
  const [department, setDepartment] = useState("Network Operations (NetOps)");
  const [saveStatus, setSaveStatus] = useState(false);

  const [apiKeys, setApiKeys] = useState([
    { id: "1", label: "SIEM_Integration_Main", keyPreview: "pk_live_49f8...", created: "2026-03-12", scopes: ["read", "logs"] },
    { id: "2", label: "Automation_Bot_01", keyPreview: "pk_live_92z2...", created: "2026-05-01", scopes: ["read", "write"] },
  ]);

  const [criticalAlerts, setCriticalAlerts] = useState(true);
  const [weeklySummary, setWeeklySummary] = useState(true);
  const [heartbeatLogs, setHeartbeatLogs] = useState(false);

  const saveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    localStorage.setItem("sicurre_user_name", name);
    setSaveStatus(true);
    setTimeout(() => setSaveStatus(false), 3000);
  };

  const deleteKey = (id: string) => setApiKeys(apiKeys.filter((k) => k.id !== id));

  const generateNewKey = () => {
    setApiKeys([...apiKeys, {
      id: String(apiKeys.length + 1),
      label: `Clé_Secours_${apiKeys.length + 1}`,
      keyPreview: `pk_live_${Math.random().toString(36).slice(2, 6)}...`,
      created: new Date().toISOString().split("T")[0],
      scopes: ["read"],
    }]);
  };

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="pb-6 border-b border-border-subtle">
        <h1 className="font-display font-bold text-[28px] text-on-surface tracking-tight leading-tight">
          Paramètres Utilisateur
        </h1>
        <p className="text-sm text-on-surface-variant mt-1">
          Gérez votre identité, protocoles de sécurité et préférences d'intégration.
        </p>
      </div>

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Security Health */}
        <div className="lg:col-span-4 space-y-6">
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            {/* Top accent bar */}
            <div className="h-1 w-full bg-primary rounded-full mb-5" />

            <div className="flex items-center justify-between mb-1">
              <h3 className="font-display font-semibold text-[17px] text-on-surface">
                Account Security Health
              </h3>
              <span className="text-[9px] font-bold text-safe bg-safe/[0.08] px-2 py-0.5 rounded uppercase tracking-[0.12em]">
                Shield Active
              </span>
            </div>
            <p className="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-[0.12em] mb-6">
              Real-time Analysis
            </p>

            {/* Gauge */}
            <div className="flex flex-col items-center mb-6">
              <div className="relative w-32 h-32 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90">
                  <circle cx="64" cy="64" r="54" className="stroke-surface-container" strokeWidth="8" fill="transparent" />
                  <circle
                    cx="64" cy="64" r="54"
                    className="stroke-safe transition-all duration-1000"
                    strokeWidth="8" fill="transparent"
                    strokeDasharray={339.3}
                    strokeDashoffset={339.3 - (339.3 * 85) / 100}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute flex flex-col items-center">
                  <span className="font-display font-bold text-[28px] text-on-surface leading-none">85</span>
                  <span className="text-[9px] font-bold text-safe uppercase tracking-[0.12em] mt-0.5">Strength</span>
                </div>
              </div>
            </div>

            {/* Health Items */}
            <div className="space-y-3 pt-4 border-t border-border-subtle">
              <div className="flex items-center gap-2.5 text-sm">
                <CheckCircle2 className="w-4 h-4 text-safe shrink-0" />
                <span className="text-on-surface-variant">MFA Enabled (FIDO2/WebAuthn)</span>
              </div>
              <div className="flex items-center gap-2.5 text-sm">
                <CheckCircle2 className="w-4 h-4 text-safe shrink-0" />
                <span className="text-on-surface-variant">Last password change: 22 days ago</span>
              </div>
              <div className="flex items-center gap-2.5 text-sm">
                <Clock className="w-4 h-4 text-secondary shrink-0" />
                <span className="text-on-surface-variant">3 inactive API keys detected</span>
              </div>
            </div>

            <button className="w-full mt-6 py-2.5 bg-primary text-on-primary font-bold rounded-lg text-[13px] flex items-center justify-center gap-2 transition-all hover:bg-navy-dark active:scale-[0.97] cursor-pointer uppercase tracking-wider">
              <RefreshCw className="w-4 h-4" />
              Run Security Audit
            </button>
          </div>
        </div>

        {/* Right: Settings Sections */}
        <div className="lg:col-span-8 space-y-6">
          {/* Personal Information */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
              <User className="w-5 h-5 text-primary" />
              <h3 className="font-display font-semibold text-[17px] text-on-surface">Personal Information</h3>
            </div>
            <form onSubmit={saveSettings} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input label="Full Name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
                <Input label="Email Address" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input label="Job Title" type="text" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
                <Input label="Department" type="text" value={department} onChange={(e) => setDepartment(e.target.value)} />
              </div>

              {saveStatus && (
                <div className="p-3 bg-safe/[0.06] border border-safe/15 text-safe text-sm rounded-lg font-medium flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>Modifications enregistrées avec succès.</span>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <Button type="submit" className="gap-2 uppercase tracking-wider text-[12px] font-bold">
                  <Save className="w-4 h-4" />
                  Update Profile
                </Button>
              </div>
            </form>
          </div>

          {/* Security & MFA */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
              <ShieldCheck className="w-5 h-5 text-primary" />
              <h3 className="font-display font-semibold text-[17px] text-on-surface">Security & MFA</h3>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-4 bg-surface-low/50 border border-border-subtle rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-primary/[0.06] rounded-lg">
                    <Fingerprint className="w-5 h-5 text-primary stroke-[1.5]" />
                  </div>
                  <div>
                    <p className="font-bold text-sm text-on-surface">Hardware Security Key</p>
                    <p className="text-[12px] text-on-surface-variant/60">YubiKey 5C NFC • Active</p>
                  </div>
                </div>
                <button className="text-[11px] font-bold text-primary uppercase tracking-wider hover:text-navy-dark transition-colors cursor-pointer">
                  Manage
                </button>
              </div>
              <div className="flex items-center justify-between p-4 bg-surface-low/50 border border-border-subtle rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-primary/[0.06] rounded-lg">
                    <Smartphone className="w-5 h-5 text-primary stroke-[1.5]" />
                  </div>
                  <div>
                    <p className="font-bold text-sm text-on-surface">Authenticator App</p>
                    <p className="text-[12px] text-on-surface-variant/60">Google Authenticator • Active</p>
                  </div>
                </div>
                <button className="text-[11px] font-bold text-primary uppercase tracking-wider hover:text-navy-dark transition-colors cursor-pointer">
                  Replace
                </button>
              </div>
              <div className="flex items-center justify-between pt-3">
                <div className="flex items-center gap-2 text-sm text-on-surface-variant">
                  <Clock className="w-4 h-4" />
                  <span>Active Login Sessions: <strong className="text-on-surface">3</strong></span>
                </div>
                <button className="text-[11px] font-bold text-error uppercase tracking-wider hover:text-error/80 transition-colors cursor-pointer">
                  Sign Out All Other Devices
                </button>
              </div>
            </div>
          </div>

          {/* API Access Keys */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <div className="flex items-center justify-between mb-5 pb-4 border-b border-border-subtle">
              <div className="flex items-center gap-2.5">
                <Key className="w-5 h-5 text-primary" />
                <h3 className="font-display font-semibold text-[17px] text-on-surface">API Access Keys</h3>
              </div>
              <Button onClick={generateNewKey} variant="outline" size="sm" className="gap-1.5 text-[12px] font-bold uppercase tracking-wider">
                <Plus className="w-3.5 h-3.5" />
                Generate Key
              </Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border-subtle">
                    <th className="pb-3 pr-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Key Label</th>
                    <th className="pb-3 px-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Permissions</th>
                    <th className="pb-3 px-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Created</th>
                    <th className="pb-3 pl-4 text-center text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.12em]">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle text-sm">
                  {apiKeys.map((key) => (
                    <tr key={key.id} className="hover:bg-surface-low/30 transition-colors">
                      <td className="py-3.5 pr-4">
                        <div>
                          <p className="font-bold text-on-surface">{key.label}</p>
                          <p className="text-[11px] font-mono text-on-surface-variant/50">{key.keyPreview}</p>
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="flex gap-1.5">
                          {key.scopes.map((scope) => (
                            <span
                              key={scope}
                              className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                                scope === "write"
                                  ? "bg-secondary/10 text-secondary"
                                  : "bg-primary/[0.06] text-primary"
                              }`}
                            >
                              {scope}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-on-surface-variant/70 font-mono text-[12px]">{key.created}</td>
                      <td className="py-3.5 pl-4 text-center">
                        <button
                          onClick={() => deleteKey(key.id)}
                          className="p-1.5 text-on-surface-variant/40 hover:text-error hover:bg-error/[0.06] rounded-lg transition-all cursor-pointer"
                          title="Révoquer cette clé"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Notification Preferences */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
              <Bell className="w-5 h-5 text-primary" />
              <h3 className="font-display font-semibold text-[17px] text-on-surface">Notification Preferences</h3>
            </div>
            <div className="space-y-5">
              <Toggle
                checked={criticalAlerts}
                onChange={setCriticalAlerts}
                label="Critical Security Alerts"
                description="Immediate SMS and Email for Tier 1 incidents."
              />
              <Toggle
                checked={weeklySummary}
                onChange={setWeeklySummary}
                label="Weekly Security Summaries"
                description="Email report of overall network performance."
              />
              <Toggle
                checked={heartbeatLogs}
                onChange={setHeartbeatLogs}
                label="API Log Heartbeats"
                description="Browser push notifications for integration activity."
              />
            </div>
          </div>
        </div>
      </div>
    </MotionDiv>
  );
}
