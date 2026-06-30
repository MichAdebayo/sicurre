import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  User,
  Save,
  CheckCircle2,
  ShieldCheck,
  Globe,
  Trash2,
  AlertTriangle,
  Plus,
  CreditCard,
  Settings,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { CloudflareIntegrator } from "../components/common/cloudflare-integrator";
import {
  AuthSession,
  getStoredAuthProvider,
  useChangePassword,
  useUpdateProfile,
  useCloudflareList,
  useTeardownCloudflare,
} from "../lib/api";

const MotionDiv = motion.div as any;

interface SettingsRouteProps {
  session: AuthSession;
}

export default function SettingsRoute({ session }: SettingsRouteProps) {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<"profile" | "security" | "preferences" | "domains" | "billing">(
    session.onboarding_required ? "domains" : "profile"
  );

  // Split Display Name into First Name & Last Name
  const nameParts = session.display_name.trim().split(/\s+/);
  const initialFirst = nameParts[0] || "";
  const initialLast = nameParts.slice(1).join(" ") || "";

  const [firstName, setFirstName] = useState(initialFirst);
  const [lastName, setLastName] = useState(initialLast);
  const [email, setEmail] = useState(session.email);

  // New Profile fields
  const [title, setTitle] = useState(localStorage.getItem("sicurre_profile_title") || "Founder & CEO");
  const [company, setCompany] = useState(localStorage.getItem("sicurre_profile_company") || "Vinse");
  const [role, setRole] = useState(localStorage.getItem("sicurre_profile_role") || "owner");

  const [saveStatus, setSaveStatus] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [lang, setLang] = useState(localStorage.getItem("sicurre_lang") || "fr");
  const [theme, setTheme] = useState(localStorage.getItem("sicurre_theme") || "light");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  // Queries for multi-domain setup and integrations
  const { data: domains, isLoading: domainsLoading, refetch: refetchDomains } = useCloudflareList();
  const teardownMutation = useTeardownCloudflare();
  const [showIntegrator, setShowIntegrator] = useState(false);
  const [integrationSuccess, setIntegrationSuccess] = useState("");
  const [integrationError, setIntegrationError] = useState("");

  const updateProfileMutation = useUpdateProfile();
  const changePasswordMutation = useChangePassword();
  const authProvider = getStoredAuthProvider();

  // Apply theme class on mount to ensure light/dark variables resolve
  useEffect(() => {
    const savedTheme = localStorage.getItem("sicurre_theme") || "light";
    if (savedTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, []);

  useEffect(() => {
    const parts = session.display_name.trim().split(/\s+/);
    setFirstName(parts[0] || "");
    setLastName(parts.slice(1).join(" ") || "");
    setEmail(session.email);
    if (session.onboarding_required) {
      setActiveTab("domains");
    }
  }, [session.display_name, session.email, session.onboarding_required]);

  const handleLanguageChange = (newLang: string) => {
    setLang(newLang);
    localStorage.setItem("sicurre_lang", newLang);
    i18n.changeLanguage(newLang);
  };

  const handleThemeChange = (newTheme: string) => {
    setTheme(newTheme);
    localStorage.setItem("sicurre_theme", newTheme);
    if (newTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setPasswordSuccess(false);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError(lang === "fr" ? "Tous les champs sont obligatoires." : "All fields are required.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(lang === "fr" ? "Les nouveaux mots de passe ne correspondent pas." : "New passwords do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError(lang === "fr" ? "Le mot de passe doit faire au moins 8 caractères." : "Password must be at least 8 characters.");
      return;
    }

    try {
      await changePasswordMutation.mutateAsync({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : "Failed to update password.");
    }
  };

  const saveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError("");
    try {
      const combinedName = `${firstName.trim()} ${lastName.trim()}`.trim();
      await updateProfileMutation.mutateAsync({ display_name: combinedName });

      // Save local fields
      localStorage.setItem("sicurre_profile_title", title);
      localStorage.setItem("sicurre_profile_company", company);
      localStorage.setItem("sicurre_profile_role", role);

      setSaveStatus(true);
      setTimeout(() => setSaveStatus(false), 3000);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Failed to save profile.");
    }
  };

  const handleRemoveDomain = async (id: string) => {
    setIntegrationError("");
    setIntegrationSuccess("");
    try {
      await teardownMutation.mutateAsync({ cf_api_token: "MOCK_TEARDOWN_TOKEN" });
      setIntegrationSuccess(lang === "fr" ? "Domaine dissocié avec succès." : "Domain disconnected successfully.");
      refetchDomains();
    } catch (error) {
      setIntegrationError(error instanceof Error ? error.message : "Failed to remove domain.");
    }
  };

  const tabs = [
    { id: "profile", label: t("settings.tab_profile"), icon: User },
    { id: "security", label: t("settings.tab_security"), icon: ShieldCheck },
    { id: "preferences", label: t("settings.tab_preferences"), icon: Settings },
    { id: "domains", label: t("settings.tab_domains"), icon: Globe },
    { id: "billing", label: t("settings.tab_billing"), icon: CreditCard },
  ] as const;

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-6 animate-in fade-in duration-200"
    >
      {/* Header */}
      <div className="pb-6 border-b border-border-subtle">
        <h1 className="app-h1">
          {t("settings.title")}
        </h1>
        <p className="app-body-sub mt-1">
          {t("settings.subtitle")}
        </p>
      </div>

      {/* Two-Column Split Layout */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
        {/* Left Column: Navigation Sidebar */}
        <div className="col-span-12 md:col-span-3 space-y-1.5 bg-surface-lowest border border-border-subtle rounded-xl p-3.5 shadow-sm">
          {tabs.map((tab) => {
            const IconComp = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id as any);
                  setShowIntegrator(false);
                }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-bold transition-all cursor-pointer text-left border-l-2 outline-none ${isActive
                    ? "bg-primary/[0.04] text-primary border-primary"
                    : "text-on-surface-variant hover:bg-surface-low hover:text-on-surface border-transparent"
                  }`}
              >
                <IconComp className={`w-4.5 h-4.5 ${isActive ? "text-primary" : "text-on-surface-variant/70"}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Right Column: Tab Content */}
        <div className="col-span-12 md:col-span-9 space-y-6">
          {/* Profile Tab */}
          {activeTab === "profile" && (
            <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm">
              <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
                <User className="w-5 h-5 text-primary" />
                <h3 className="font-display font-semibold text-[17px] text-on-surface">
                  {t("settings.tab_profile")}
                </h3>
              </div>
              <form onSubmit={saveSettings} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Input label={lang === "fr" ? "Prénom" : "First Name"} type="text" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
                  <Input label={lang === "fr" ? "Nom" : "Last Name"} type="text" value={lastName} onChange={(e) => setLastName(e.target.value)} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Input label={lang === "fr" ? "Titre / Fonction" : "Current Title"} type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
                  <Input label={lang === "fr" ? "Nom de l'entreprise" : "Company Name"} type="text" value={company} onChange={(e) => setCompany(e.target.value)} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Input label={lang === "fr" ? "Adresse e-mail" : "Email Address"} type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled />

                  {/* Default User Role Dropdown */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-label-caps text-on-surface-variant font-semibold">
                      {lang === "fr" ? "Rôle de l'utilisateur" : "User Role"}
                    </label>
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      className="w-full px-4 py-2.5 bg-surface-lowest border border-border-subtle rounded-lg text-body-md text-on-surface focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none cursor-pointer h-[44px] font-semibold"
                    >
                      <option value="owner">Owner</option>
                      <option value="admin">Administrator</option>
                      <option value="member">Member</option>
                    </select>
                  </div>
                </div>

                {saveStatus && (
                  <div className="p-3 bg-safe/[0.06] border border-safe/15 text-safe text-xs rounded-lg font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>{t("settings.save_success")}</span>
                  </div>
                )}
                {saveError && <p className="text-xs text-error font-semibold">{saveError}</p>}

                <div className="flex justify-end pt-2">
                  <Button type="submit" className="gap-2 uppercase tracking-wider text-[11px] font-bold cursor-pointer">
                    <Save className="w-4 h-4" />
                    {t("common.save")}
                  </Button>
                </div>
              </form>
            </div>
          )}

          {/* Security Tab */}
          {activeTab === "security" && (
            <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm">
              <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
                <ShieldCheck className="w-5 h-5 text-primary" />
                <h3 className="font-display font-semibold text-[17px] text-on-surface">
                  {t("settings.tab_security")}
                </h3>
              </div>

              {authProvider === "google" ? (
                <div className="p-4 bg-primary/[0.04] border border-primary/10 rounded-xl space-y-2">
                  <p className="text-sm font-semibold text-primary">
                    {lang === "fr" ? "Connexion Google Workspace active" : "Google Workspace login active"}
                  </p>
                  <p className="text-xs text-on-surface-variant font-medium leading-relaxed">
                    {lang === "fr"
                      ? "La gestion de votre mot de passe et MFA s'effectue directement au sein de votre console Google."
                      : "Your credentials and two-factor authentication are verified directly through Google Workspace OAuth."}
                  </p>
                </div>
              ) : (
                <form onSubmit={handlePasswordChange} className="space-y-4">
                  <Input
                    label={lang === "fr" ? "Mot de passe actuel" : "Current password"}
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  <Input
                    label={lang === "fr" ? "Nouveau mot de passe" : "New password"}
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  <Input
                    label={lang === "fr" ? "Confirmer le nouveau mot de passe" : "Confirm new password"}
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  {passwordError && (
                    <p className="text-xs text-error font-semibold">{passwordError}</p>
                  )}
                  {passwordSuccess && (
                    <div className="p-3 bg-safe/[0.06] border border-safe/15 text-safe text-xs rounded-lg font-medium flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 shrink-0" />
                      <span>
                        {lang === "fr" ? "Mot de passe mis à jour." : "Password updated successfully."}
                      </span>
                    </div>
                  )}
                  <div className="flex justify-end pt-2">
                    <Button type="submit" className="uppercase tracking-wider text-[11px] font-bold cursor-pointer" disabled={changePasswordMutation.isPending}>
                      {lang === "fr" ? "Mettre à jour" : "Update Password"}
                    </Button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Preferences Tab */}
          {activeTab === "preferences" && (
            <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm">
              <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
                <Settings className="w-5 h-5 text-primary" />
                <h3 className="font-display font-semibold text-[17px] text-on-surface">
                  {t("settings.tab_preferences")}
                </h3>
              </div>
              <div className="space-y-6">
                <div className="flex items-center justify-between py-2 border-b border-border-subtle/50">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm font-bold text-on-surface">
                      {lang === "fr" ? "Langue de l'interface" : "Interface Language"}
                    </span>
                    <span className="text-xs font-semibold text-on-surface-variant">
                      {lang === "fr" ? "Sélectionnez la langue d'affichage des menus." : "Choose language toggle for client dashboard."}
                    </span>
                  </div>
                  <select
                    value={lang}
                    onChange={(e) => handleLanguageChange(e.target.value)}
                    className="px-3.5 py-2 bg-surface-lowest border border-border-subtle rounded-lg text-sm text-on-surface focus:outline-none focus:border-primary outline-none cursor-pointer font-semibold"
                  >
                    <option value="fr">Français</option>
                    <option value="en">English</option>
                  </select>
                </div>

                <div className="flex items-center justify-between py-2">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm font-bold text-on-surface">
                      {lang === "fr" ? "Thème visuel" : "Visual Theme"}
                    </span>
                    <span className="text-xs font-semibold text-on-surface-variant">
                      {lang === "fr" ? "Basculez entre l'interface claire et l'interface sombre." : "Switch between light and dark console modes."}
                    </span>
                  </div>
                  <select
                    value={theme}
                    onChange={(e) => handleThemeChange(e.target.value)}
                    className="px-3.5 py-2 bg-surface-lowest border border-border-subtle rounded-lg text-sm text-on-surface focus:outline-none focus:border-primary outline-none cursor-pointer font-semibold"
                  >
                    <option value="light">{lang === "fr" ? "Mode Clair" : "Light"}</option>
                    <option value="dark">{lang === "fr" ? "Mode Sombre" : "Dark"}</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Connected Domains Tab */}
          {activeTab === "domains" && (
            <div className="space-y-6">
              {session.onboarding_required && (
                <div className="rounded-xl border border-primary/15 bg-primary/[0.04] p-4 text-xs text-on-surface font-semibold flex gap-2">
                  <AlertTriangle className="w-4.5 h-4.5 text-primary shrink-0" />
                  <div>
                    <p className="text-primary">{lang === "fr" ? "Configuration requise" : "Onboarding required"}</p>
                    <p className="mt-0.5 text-on-surface-variant font-normal">
                      {lang === "fr"
                        ? "Connectez votre premier domaine via le wizard Cloudflare pour activer le routage e-mail."
                        : "Configure your email routing zone using Cloudflare below to start protecting your inbox."}
                    </p>
                  </div>
                </div>
              )}

              {integrationSuccess && (
                <div className="p-3 bg-safe/10 border border-safe/25 text-safe text-xs font-semibold rounded-lg flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{integrationSuccess}</span>
                </div>
              )}
              {integrationError && (
                <div className="p-3 bg-error/10 border border-error/25 text-error text-xs font-semibold rounded-lg flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  <span>{integrationError}</span>
                </div>
              )}

              <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm space-y-6">
                <div className="flex justify-between items-center border-b border-border-subtle pb-4">
                  <div className="flex items-center gap-2.5">
                    <Globe className="w-5 h-5 text-primary" />
                    <div>
                      <h3 className="font-display font-semibold text-[17px] text-on-surface">
                        {t("settings.domains_title")}
                      </h3>
                      {/* Improved subtext colors and size readability */}
                      <p className="text-sm font-semibold text-on-surface-variant">
                        {t("settings.domains_desc")}
                      </p>
                    </div>
                  </div>
                  {!showIntegrator && (
                    <Button onClick={() => setShowIntegrator(true)} className="text-xs font-bold gap-1 cursor-pointer">
                      <Plus className="w-3.5 h-3.5" />
                      {t("settings.add_domain")}
                    </Button>
                  )}
                </div>

                {showIntegrator ? (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center bg-surface-low/50 p-3 rounded-lg border border-border-subtle/50">
                      <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider">
                        {lang === "fr" ? "Nouveau domaine Cloudflare" : "New Cloudflare Integration"}
                      </span>
                      <Button variant="outline" size="sm" onClick={() => setShowIntegrator(false)} className="text-xs cursor-pointer">
                        {lang === "fr" ? "Annuler" : "Cancel"}
                      </Button>
                    </div>
                    <div className="border border-border-subtle rounded-xl p-4 bg-surface-lowest">
                      <CloudflareIntegrator
                        userEmail={session.email}
                        onSuccess={() => {
                          setShowIntegrator(false);
                          setIntegrationSuccess(lang === "fr" ? "Domaine ajouté avec succès !" : "Domain added successfully!");
                          refetchDomains();
                        }}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {domainsLoading ? (
                      <div className="h-16 bg-surface-low rounded-xl animate-pulse" />
                    ) : !domains || domains.length === 0 ? (
                      <div className="py-12 text-center text-sm text-on-surface-variant/50 flex flex-col items-center justify-center">
                        <Globe className="w-10 h-10 text-on-surface-variant/30 mb-2" />
                        <p>{t("settings.no_domains")}</p>
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        {/* Standardized table columns typography layout to match standard sans fonts */}
                        <table className="w-full text-left border-collapse text-xs font-sans">
                          <thead>
                            <tr className="border-b border-border-subtle bg-surface-low/30 text-on-surface-variant uppercase font-bold">
                              <th className="px-4 py-3">{t("settings.domain_name")}</th>
                              <th className="px-4 py-3">{t("settings.domain_status")}</th>
                              <th className="px-4 py-3">{t("settings.domain_recipient")}</th>
                              <th className="px-4 py-3 text-right">{t("settings.domain_actions")}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border-subtle/50 font-sans">
                            {domains.map((dom) => (
                              <tr key={dom.id} className="hover:bg-surface-low/20 transition-colors">
                                <td className="px-4 py-3 font-semibold text-on-surface">{dom.zone_name}</td>
                                <td className="px-4 py-3">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${dom.status === "active"
                                      ? "bg-safe/10 text-safe"
                                      : dom.status === "error"
                                        ? "bg-error/10 text-error"
                                        : "bg-warning/10 text-warning"
                                    }`}>
                                    {dom.status === "active"
                                      ? t("settings.active_setup")
                                      : dom.status === "error"
                                        ? t("settings.error_setup")
                                        : t("settings.verify_setup")}
                                  </span>
                                </td>
                                <td className="px-4 py-3 font-semibold text-on-surface-variant">{dom.destination_email}</td>
                                <td className="px-4 py-3 text-right">
                                  <button
                                    onClick={() => dom.id && handleRemoveDomain(dom.id)}
                                    className="p-1.5 rounded hover:bg-surface-low hover:text-error text-on-surface-variant/50 transition-colors cursor-pointer"
                                    title={lang === "fr" ? "Dissocier" : "Disconnect"}
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Billing Tab */}
          {activeTab === "billing" && (
            <div className="space-y-6">
              {/* Current usage progress gauge */}
              <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm space-y-4">
                <div className="flex items-center gap-2.5 pb-4 border-b border-border-subtle">
                  <CreditCard className="w-5 h-5 text-primary" />
                  <h3 className="font-display font-bold text-[19px] text-on-surface">
                    {t("settings.billing_usage")}
                  </h3>
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="font-bold text-on-surface">{t("settings.usage_emails")}</span>
                    <span className="font-bold text-on-surface-variant">
                      86 / 250 {lang === "fr" ? "emails scannés" : "emails analyzed"}
                    </span>
                  </div>
                  <div className="w-full h-2 bg-surface-container rounded-full overflow-hidden">
                    <div className="h-full bg-primary rounded-full" style={{ width: "34.4%" }} />
                  </div>
                  <p className="text-sm font-semibold text-on-surface-variant leading-normal">
                    {lang === "fr"
                      ? "Votre abonnement gratuit se réinitialise le 1er du mois. Upgradez pour augmenter vos quotas."
                      : "Usage resets on the 1st of each month. Upgrade to lift monthly volumetric ingestion limits."}
                  </p>
                </div>
              </div>

              {/* Pricing Cards Grid */}
              <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm space-y-6">
                <div>
                  <h3 className="font-display font-bold text-[19px] text-on-surface">
                    {t("settings.billing_upgrade")}
                  </h3>
                  <p className="text-sm font-semibold text-on-surface-variant mt-1">
                    {lang === "fr"
                      ? "Sélectionnez l'offre adaptée à votre activité de freelance ou PME."
                      : "Choose the package matching your operations count and freelance workflow."}
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Free Tier (Includes Popular Badge) */}
                  <div className="border border-primary rounded-xl p-5 flex flex-col justify-between hover:shadow-md transition-all relative overflow-hidden bg-primary/[0.01]">
                    <div className="absolute top-0 right-0 bg-primary text-on-primary text-[10px] font-bold px-2.5 py-0.5 rounded-bl uppercase">
                      Popular
                    </div>
                    <div className="space-y-3">
                      <span className="text-xs font-bold text-primary uppercase tracking-wider block">
                        {t("settings.billing_free")}
                      </span>
                      <div className="flex items-baseline gap-1">
                        <span className="font-display font-bold text-3xl text-on-surface">€0</span>
                        <span className="text-xs font-bold text-on-surface-variant">/{t("settings.price_per_month")}</span>
                      </div>
                      <p className="text-sm font-medium text-on-surface-variant leading-normal">
                        {t("settings.billing_free_desc")}
                      </p>
                      <ul className="text-xs space-y-2 text-on-surface pt-3 border-t border-border-subtle/50 font-semibold">
                        <li>• 1 Protected Domain</li>
                        <li>• 250 analyzed emails/mo</li>
                        <li>• Phishing email auto-trash</li>
                      </ul>
                    </div>
                    <Button variant="outline" disabled className="w-full text-xs mt-6 font-bold">
                      {lang === "fr" ? "Plan Actuel" : "Current Plan"}
                    </Button>
                  </div>

                  {/* Growth Tier (Coming Soon) */}
                  <div className="border border-border-subtle rounded-xl p-5 flex flex-col justify-between hover:border-primary/30 transition-all bg-surface-low/10">
                    <div className="space-y-3">
                      <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider block">
                        {t("settings.billing_growth")}
                      </span>
                      <div className="flex items-baseline gap-1">
                        <span className="font-display font-bold text-3xl text-on-surface">€19</span>
                        <span className="text-xs font-bold text-on-surface-variant">/{t("settings.price_per_month")}</span>
                      </div>
                      <p className="text-sm font-medium text-on-surface-variant leading-normal">
                        {t("settings.billing_growth_desc")}
                      </p>
                      <ul className="text-xs space-y-2 text-on-surface pt-3 border-t border-border-subtle/50 font-semibold">
                        <li>• <strong>Up to 3 domains</strong></li>
                        <li>• 10,000 emails/mo</li>
                        <li>• Live AI priority scans</li>
                        <li>• Quiet hours & rules</li>
                        <li>• Quarantine Queue</li>
                      </ul>
                    </div>
                    <Button variant="outline" disabled className="w-full text-xs mt-6 font-bold">
                      {lang === "fr" ? "Bientôt disponible" : "Coming Soon"}
                    </Button>
                  </div>

                  {/* Business Tier (Coming Soon) */}
                  <div className="border border-border-subtle rounded-xl p-5 flex flex-col justify-between hover:border-primary/30 transition-all bg-surface-low/10">
                    <div className="space-y-3">
                      <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider block">
                        {t("settings.billing_business")}
                      </span>
                      <div className="flex items-baseline gap-1">
                        <span className="font-display font-bold text-3xl text-on-surface">€49</span>
                        <span className="text-xs font-bold text-on-surface-variant">/{t("settings.price_per_month")}</span>
                      </div>
                      <p className="text-sm font-medium text-on-surface-variant leading-normal">
                        {t("settings.billing_business_desc")}
                      </p>
                      <ul className="text-xs space-y-2 text-on-surface pt-3 border-t border-border-subtle/50 font-semibold">
                        <li>• <strong>Up to 10 domains</strong></li>
                        <li>• 100,000 emails/mo</li>
                        <li>• Custom white/blacklists</li>
                        <li>• Loops SMTP integration</li>
                        <li>• Dedicated slack support</li>
                      </ul>
                    </div>
                    <Button variant="outline" disabled className="w-full text-xs mt-6 font-bold">
                      {lang === "fr" ? "Bientôt disponible" : "Coming Soon"}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </MotionDiv>
  );
}
