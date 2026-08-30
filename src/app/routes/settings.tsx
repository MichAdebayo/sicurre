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
  Settings,
  Eye,
  EyeOff,
  Puzzle,
  Info,
  Loader2,
  RefreshCw,
  Bell,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { CloudflareIntegrator } from "../components/common/cloudflare-integrator";
import { AppToast } from "../components/common/app-toast";
import AlertsRoute from "./alerts";
import cloudflareLogo from "../assets/cloudflare-svgrepo-com.svg";
import { useTheme } from "../lib/theme";
import {
  AuthSession,
  getStoredAuthProvider,
  useChangePassword,
  useUpdateProfile,
  useCloudflareList,
  useSetupCloudflare,
  useTeardownCloudflare,
  useWorkspaceCloudflareToken,
  useSaveWorkspaceCloudflareToken,
  useDeleteWorkspaceCloudflareToken,
} from "../lib/api";

const MotionDiv = motion.div as any;

interface SettingsRouteProps {
  session: AuthSession;
  initialTab?: string;
}

export default function SettingsRoute({ session, initialTab }: SettingsRouteProps) {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<"profile" | "security" | "preferences" | "notifications" | "domains" | "integrations">(
    (initialTab as any) || (session.onboarding_required ? "domains" : "profile")
  );

  // Split Display Name into First Name & Last Name
  const nameParts = session.display_name.trim().split(/\s+/);
  const initialFirst = nameParts[0] || "";
  const initialLast = nameParts.slice(1).join(" ") || "";

  const [firstName, setFirstName] = useState(initialFirst);
  const [lastName, setLastName] = useState(initialLast);
  const [email, setEmail] = useState(session.email);

  // New Profile fields
  const [title, setTitle] = useState(localStorage.getItem("sicurre_profile_title") || "");
  const [company, setCompany] = useState(localStorage.getItem("sicurre_profile_company") || "");
  const [role, setRole] = useState(localStorage.getItem("sicurre_profile_role") || "owner");

  const [saveStatus, setSaveStatus] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [lang, setLang] = useState(localStorage.getItem("sicurre_lang") || "fr");
  const [theme, setTheme] = useTheme();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  // Queries for multi-domain setup and integrations
  const { data: domains, isLoading: domainsLoading, refetch: refetchDomains } = useCloudflareList();
  const teardownMutation = useTeardownCloudflare();
  const retrySetupMutation = useSetupCloudflare();
  const [showIntegrator, setShowIntegrator] = useState(false);
  const [integrationSuccess, setIntegrationSuccess] = useState("");
  const [integrationError, setIntegrationError] = useState("");
  const [retryingDomainId, setRetryingDomainId] = useState<string | null>(null);
  const [visibleTokens, setVisibleTokens] = useState<Record<string, boolean>>({});

  // Workspace-level global Cloudflare Token management
  const { data: wsTokenData, refetch: refetchWsToken } = useWorkspaceCloudflareToken();
  const saveWsTokenMutation = useSaveWorkspaceCloudflareToken();
  const deleteWsTokenMutation = useDeleteWorkspaceCloudflareToken();
  const [cfTokenInput, setCfTokenInput] = useState("");
  const [isEditingToken, setIsEditingToken] = useState(false);
  const [workspaceTokenVisible, setWorkspaceTokenVisible] = useState(false);
  const [integrationsError, setIntegrationsError] = useState("");
  const [integrationsSuccess, setIntegrationsSuccess] = useState("");
  const [deleteTokenConfirmVisible, setDeleteTokenConfirmVisible] = useState(false);
  const [removeDomainConfirmId, setRemoveDomainConfirmId] = useState<string | null>(null);
  const [selectedIntegrationDomainId, setSelectedIntegrationDomainId] = useState<string>("");

  useEffect(() => {
    if (domains && domains.length > 0 && !selectedIntegrationDomainId) {
      setSelectedIntegrationDomainId(domains[0].id || "");
    }
  }, [domains, selectedIntegrationDomainId]);

  const updateProfileMutation = useUpdateProfile();
  const changePasswordMutation = useChangePassword();
  const authProvider = getStoredAuthProvider();

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
    setTheme(newTheme === "dark" ? "dark" : "light");
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setPasswordSuccess(false);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError(t("settings.password_required"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t("settings.password_mismatch"));
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError(t("settings.password_minimum"));
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
      setPasswordError(error instanceof Error ? error.message : t("settings.password_update_failed"));
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
      setSaveError(error instanceof Error ? error.message : t("settings.profile_save_failed"));
    }
  };

  const handleRemoveDomain = async (id: string) => {
    setRemoveDomainConfirmId(id);
  };

  const executeRemoveDomain = async (id: string) => {
    setRemoveDomainConfirmId(null);
    setIntegrationError("");
    setIntegrationSuccess("");
    try {
      await teardownMutation.mutateAsync({ integration_id: id });
      await refetchDomains();
      setIntegrationSuccess(t("settings.domain_disconnected"));
    } catch (error) {
      setIntegrationError(
        error instanceof Error
          ? error.message
          : t("settings.domain_disconnect_failed"),
      );
    }
  };

  const handleRetryDomain = async (domain: NonNullable<typeof domains>[number]) => {
    if (!domain.zone_name || !domain.destination_email) return;
    setIntegrationError("");
    setIntegrationSuccess("");
    setRetryingDomainId(domain.id || null);
    try {
      await retrySetupMutation.mutateAsync({
        zone_name: domain.zone_name,
        destination_email: domain.destination_email,
      });
      await refetchDomains();
      setIntegrationSuccess(t("settings.retry_started"));
    } catch (error) {
      setIntegrationError(
        error instanceof Error
          ? error.message
          : t("settings.retry_failed"),
      );
    } finally {
      setRetryingDomainId(null);
    }
  };

  const handleSaveToken = async (e: React.FormEvent) => {
    e.preventDefault();
    setIntegrationsError("");
    setIntegrationsSuccess("");
    if (!cfTokenInput.trim()) {
      setIntegrationsError(t("settings.token_required"));
      return;
    }
    try {
      await saveWsTokenMutation.mutateAsync(cfTokenInput.trim());
      setIntegrationsSuccess(t("settings.token_saved"));
      setIsEditingToken(false);
      setCfTokenInput("");
      refetchWsToken();
      refetchDomains();
    } catch (err: any) {
      setIntegrationsError(err?.message || t("settings.token_save_failed"));
    }
  };

  const handleDeleteToken = async () => {
    setDeleteTokenConfirmVisible(true);
  };

  const executeDeleteToken = async () => {
    setDeleteTokenConfirmVisible(false);
    setIntegrationsError("");
    setIntegrationsSuccess("");
    try {
      await deleteWsTokenMutation.mutateAsync();
      setIntegrationsSuccess(t("settings.token_deleted"));
      refetchWsToken();
      refetchDomains();
    } catch (err: any) {
      setIntegrationsError(err?.message || t("settings.token_delete_failed"));
    }
  };

  const tabs = [
    { id: "profile", label: t("settings.tab_profile"), icon: User },
    { id: "security", label: t("settings.tab_security"), icon: ShieldCheck },
    { id: "preferences", label: t("settings.tab_preferences"), icon: Settings },
    { id: "notifications", label: t("settings.tab_notifications"), icon: Bell },
    { id: "domains", label: t("settings.tab_domains"), icon: Globe },
    { id: "integrations", label: t("settings.tab_integrations"), icon: Puzzle },
  ] as const;
  const toastError = saveError || integrationError || integrationsError;
  const toastSuccess = saveStatus
    ? t("settings.save_success")
    : integrationSuccess || integrationsSuccess;
  const failedDomain = domains?.find((domain) => domain.status === "error");

  const clearToast = () => {
    setSaveStatus(false);
    setSaveError("");
    setIntegrationSuccess("");
    setIntegrationError("");
    setIntegrationsSuccess("");
    setIntegrationsError("");
  };

  return (
    <MotionDiv
      initial={false}
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
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-x-10 gap-y-6 items-start">
        {/* Left Column: settings sub-navigation.
            Rendered as a plain column rather than a bordered card so the page
            reads rail → section list → content, instead of nesting three
            levels of chrome. */}
        <nav
          aria-label={t("settings.title")}
          className="col-span-12 flex gap-1 overflow-x-auto border-b border-border-subtle pb-3 lg:col-span-3 lg:block lg:space-y-1 lg:overflow-visible lg:border-b-0 lg:border-r lg:pb-1 lg:pr-8"
        >
          {tabs.map((tab) => {
            const IconComp = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                aria-current={isActive ? "page" : undefined}
                onClick={() => {
                  setActiveTab(tab.id as any);
                  setShowIntegrator(false);
                }}
                className={`flex shrink-0 items-center gap-3 rounded-lg px-3.5 py-3 text-left text-[15px] leading-6 transition-colors lg:w-full ${isActive
                  ? "bg-surface-low text-on-surface font-semibold"
                  : "text-on-surface-variant font-medium hover:bg-surface-low/60 hover:text-on-surface"
                  }`}
              >
                <IconComp
                  aria-hidden="true"
                  className={`h-[18px] w-[18px] shrink-0 stroke-[1.5] ${isActive ? "text-primary" : "text-on-surface-variant/70"}`}
                />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Column: Tab Content */}
        <div className="col-span-12 lg:col-span-9 space-y-6">
          {/* Profile Tab */}
          {activeTab === "profile" && (
            <section className="bg-surface-lowest rounded-xl border border-border-subtle p-7 shadow-sm">
              <header className="mb-6 flex items-start justify-between gap-6">
                <div>
                  <h2 className="app-h2">{t("settings.tab_profile")}</h2>
                  <p className="app-body-sub mt-1">{t("settings.profile_desc")}</p>
                </div>
                <Button type="submit" form="settings-profile-form" className="gap-2 shrink-0 cursor-pointer">
                  <Save className="w-4 h-4" aria-hidden="true" />
                  {t("common.save")}
                </Button>
              </header>
              <form id="settings-profile-form" onSubmit={saveSettings} className="space-y-5">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <Input label={t("settings.first_name")} type="text" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
                  <Input label={t("settings.last_name")} type="text" value={lastName} onChange={(e) => setLastName(e.target.value)} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <Input label={t("settings.job_title")} type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
                  <Input label={t("settings.company")} type="text" value={company} onChange={(e) => setCompany(e.target.value)} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <Input label={t("settings.email")} type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled />

                  {/* Default User Role Dropdown */}
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="settings-user-role" className="text-label-caps text-on-surface-variant font-semibold">
                      {t("settings.user_role")}
                    </label>
                    <select
                      id="settings-user-role"
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
              </form>
            </section>
          )}

          {/* Security Tab */}
          {activeTab === "security" && (
            <section className="bg-surface-lowest rounded-xl border border-border-subtle p-7 shadow-sm">
              <header className="mb-6">
                <h2 className="app-h2">{t("settings.tab_security")}</h2>
                <p className="app-body-sub mt-1">{t("settings.security_desc")}</p>
              </header>

              {authProvider === "google" ? (
                <div className="p-4 bg-primary/[0.04] border border-primary/10 rounded-xl space-y-2">
                  <p className="text-sm font-semibold text-primary">
                    {t("settings.google_login_active")}
                  </p>
                  <p className="text-xs text-on-surface-variant font-medium leading-relaxed">
                    {t("settings.google_login_desc")}
                  </p>
                </div>
              ) : (
                <form onSubmit={handlePasswordChange} className="space-y-4">
                  <Input
                    label={t("settings.current_password")}
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  <Input
                    label={t("settings.new_password")}
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  <Input
                    label={t("settings.confirm_password")}
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
                        {t("settings.password_updated")}
                      </span>
                    </div>
                  )}
                  <div className="flex justify-end pt-2">
                    <Button type="submit" className="text-xs font-bold cursor-pointer" disabled={changePasswordMutation.isPending}>
                      {t("settings.update_password")}
                    </Button>
                  </div>
                </form>
              )}
            </section>
          )}

          {/* Preferences Tab */}
          {activeTab === "preferences" && (
            <section className="bg-surface-lowest rounded-xl border border-border-subtle p-7 shadow-sm">
              <header className="mb-6">
                <h2 className="app-h2">{t("settings.tab_preferences")}</h2>
                <p className="app-body-sub mt-1">{t("settings.preferences_desc")}</p>
              </header>
              <div className="space-y-6">
                <div className="flex items-center justify-between py-2 border-b border-border-subtle/50">
                  <div className="flex flex-col gap-0.5">
                    <span id="settings-language-label" className="text-sm font-bold text-on-surface">
                      {t("settings.interface_language")}
                    </span>
                    <span className="text-xs font-semibold text-on-surface-variant">
                      {t("settings.interface_language_desc")}
                    </span>
                  </div>
                  <select
                    aria-labelledby="settings-language-label"
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
                    <span id="settings-theme-label" className="text-sm font-bold text-on-surface">
                      {t("settings.visual_theme")}
                    </span>
                    <span className="text-xs font-semibold text-on-surface-variant">
                      {t("settings.visual_theme_desc")}
                    </span>
                  </div>
                  <select
                    aria-labelledby="settings-theme-label"
                    value={theme}
                    onChange={(e) => handleThemeChange(e.target.value)}
                    className="px-3.5 py-2 bg-surface-lowest border border-border-subtle rounded-lg text-sm text-on-surface focus:outline-none focus:border-primary outline-none cursor-pointer font-semibold"
                  >
                    <option value="light">{t("settings.theme_light")}</option>
                    <option value="dark">{t("settings.theme_dark")}</option>
                  </select>
                </div>
              </div>
            </section>
          )}

          {activeTab === "notifications" && <AlertsRoute mode="settings" />}

          {/* Connected Domains Tab */}
          {activeTab === "domains" && (
            <div className="space-y-6">
              {session.onboarding_required && (
                <div className="flex gap-2 rounded-xl border border-warning/25 bg-warning-bg p-4 text-xs font-semibold text-on-surface">
                  <AlertTriangle className="w-4.5 h-4.5 shrink-0 text-warning" />
                  <div>
                    <p className="text-on-surface">{t("settings.onboarding_required")}</p>
                    <p className="mt-0.5 text-on-surface-variant font-normal">
                      {failedDomain
                        ? t("settings.onboarding_retry", { domain: failedDomain.zone_name })
                        : t("settings.onboarding_add_domain")}
                    </p>
                  </div>
                </div>
              )}

              <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm space-y-6">
                <div className="flex justify-between items-center border-b border-border-subtle pb-4">
                  <div className="flex items-center gap-2.5">
                    <Globe className="w-5 h-5 text-primary" />
                    <div>
                      <h2 className="app-h2">
                        {t("settings.domains_title")}
                      </h2>
                      <p className="app-body-sub mt-1">
                        {t("settings.domains_desc")}
                      </p>
                    </div>
                  </div>
                  {!showIntegrator && (
                    <Button onClick={() => setShowIntegrator(true)} className="text-xs font-bold gap-1 cursor-pointer">
                      <Plus className="w-3.5 h-3.5" />
                      {domains?.length ? t("settings.add_another_domain") : t("settings.add_domain")}
                    </Button>
                  )}
                </div>

                {showIntegrator ? (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center bg-surface-low/50 p-3 rounded-lg border border-border-subtle/50">
                      <span className="font-display font-semibold text-sm text-on-surface">
                        {t("settings.new_cloudflare_domain")}
                      </span>
                      <button
                        onClick={() => setShowIntegrator(false)}
                        className="text-xs font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white cursor-pointer transition-colors duration-200"
                      >
                        {t("common.cancel")}
                      </button>
                    </div>
                    <div className="border border-border-subtle rounded-xl p-4 bg-surface-lowest">
                      <CloudflareIntegrator
                        userEmail={session.email}
                        onSuccess={() => {
                          setShowIntegrator(false);
                          setIntegrationSuccess(t("settings.domain_added"));
                          refetchDomains();
                        }}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {domainsLoading ? (
                      <div className="h-16 bg-surface-low rounded-xl motion-safe:animate-pulse" />
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
                            <tr className="border-b border-border-subtle bg-surface-low/30 text-on-surface-variant font-bold text-xs tracking-wide">
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
                                  <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${dom.status === "active"
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
                                  <div className="inline-flex items-center gap-1">
                                    {dom.status === "error" && (
                                      <button
                                        onClick={() => void handleRetryDomain(dom)}
                                        disabled={retrySetupMutation.isPending}
                                        className="inline-grid h-10 w-10 place-items-center rounded-md text-primary transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-wait disabled:opacity-50 cursor-pointer"
                                        title={t("settings.retry_configuration")}
                                        aria-label={t("settings.retry_domain", { domain: dom.zone_name })}
                                      >
                                        {retrySetupMutation.isPending && retryingDomainId === dom.id
                                          ? <Loader2 className="w-4 h-4 animate-spin" />
                                          : <RefreshCw className="w-4 h-4" />}
                                      </button>
                                    )}
                                    <button
                                      onClick={() => dom.id && handleRemoveDomain(dom.id)}
                                      className="inline-grid h-10 w-10 place-items-center rounded-md text-on-surface-variant transition-colors hover:bg-error/10 hover:text-error focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error cursor-pointer"
                                      title={t("settings.disconnect")}
                                      aria-label={t("settings.disconnect_domain_named", { domain: dom.zone_name })}
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </button>
                                  </div>
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

          {/* Integrations Tab */}
          {activeTab === "integrations" && (
            <div className="space-y-6 animate-in fade-in duration-200">
              {/* Global Integrations Card */}
              <div className="bg-surface-lowest rounded-xl border border-border-subtle p-6 shadow-sm space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border-subtle pb-4">
                  <div className="flex items-center gap-3">
                    <Puzzle className="w-5 h-5 text-primary shrink-0" />
                    <div>
                      <h2 className="app-h2">
                        {t("settings.integrations_title")}
                      </h2>
                      <p className="app-body-sub mt-1">
                        {t("settings.integrations_desc")}
                      </p>
                    </div>
                  </div>

                  {/* Connected domains selector dropdown next to the title */}
                  {!domainsLoading && domains && domains.length > 0 && (
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs font-semibold text-on-surface-variant">
                        {t("settings.domain_label")}
                      </span>
                      <select
                        value={selectedIntegrationDomainId}
                        onChange={(e) => setSelectedIntegrationDomainId(e.target.value)}
                        className="bg-surface-low border border-border-subtle rounded-lg text-xs font-bold px-3 py-1.5 focus:outline-none focus:border-primary text-on-surface cursor-pointer"
                      >
                        {domains.map((dom) => (
                          <option key={dom.id} value={dom.id}>
                            {dom.zone_name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                {/* Setup or Token Details */}
                {isEditingToken ? (
                  <form onSubmit={handleSaveToken} className="space-y-4 max-w-xl">
                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-on-surface-variant">
                        {t("settings.cloudflare_token")}
                      </label>
                      <div className="relative">
                        <Input
                          type={workspaceTokenVisible ? "text" : "password"}
                          placeholder="e.g. 8x_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                          value={cfTokenInput}
                          onChange={(e) => setCfTokenInput(e.target.value)}
                          className="pr-10 font-mono text-xs"
                        />
                        <button
                          type="button"
                          onClick={() => setWorkspaceTokenVisible(!workspaceTokenVisible)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                        >
                          {workspaceTokenVisible ? (
                            <EyeOff className="w-4 h-4" />
                          ) : (
                            <Eye className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                      <p className="text-[11px] text-on-surface-variant font-semibold leading-normal">
                        {t("settings.cloudflare_token_desc")}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 pt-2">
                      <Button
                        type="submit"
                        disabled={saveWsTokenMutation.isPending}
                        className="bg-primary hover:bg-primary/90 text-on-primary text-xs font-bold px-4 py-2 rounded-lg cursor-pointer h-9 transition-all"
                      >
                        {saveWsTokenMutation.isPending
                          ? t("settings.verifying")
                          : t("settings.save_integration")}
                      </Button>

                      <button
                        type="button"
                        onClick={() => {
                          setIsEditingToken(false);
                          setCfTokenInput("");
                        }}
                        className="bg-surface-low border border-border-subtle text-on-surface hover:bg-surface-low/80 text-xs font-bold px-4 py-2 rounded-lg cursor-pointer h-9 transition-all"
                      >
                        {t("common.cancel")}
                      </button>
                    </div>
                  </form>
                ) : wsTokenData?.configured ? (
                  <div className="border border-border-subtle rounded-xl bg-surface-low/10 divide-y divide-border-subtle/50 hover:shadow-sm transition-all overflow-hidden">
                    {/* Top Row: Integration Status & Token Info + Actions */}
                    <div className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-6">
                      <div className="flex items-start gap-4 grow">
                        <div className="p-2.5 bg-primary/[0.04] border border-primary/10 rounded-xl shrink-0">
                          <img src={cloudflareLogo} alt="Cloudflare" className="w-8 h-8" />
                        </div>
                        <div className="space-y-1 grow">
                          <h4 className="flex items-center gap-2 text-sm font-bold text-on-surface">
                            <span>Cloudflare</span>
                            <span className="rounded-full border border-safe/25 bg-safe-bg px-2.5 py-1 text-xs font-semibold text-safe">
                              {t("settings.connected")}
                            </span>
                          </h4>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 sm:self-center shrink-0">
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => {
                            setCfTokenInput("");
                            setIsEditingToken(true);
                          }}
                          className="font-bold text-xs h-9 cursor-pointer"
                        >
                          {t("settings.edit_token")}
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={handleDeleteToken}
                          className="font-bold text-xs h-9 cursor-pointer"
                        >
                          {t("settings.revoke_access")}
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-6 text-center text-xs font-semibold text-on-surface-variant w-full">
                    {t("settings.no_active_integration")}
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* UI Confirmation Modal for Token Deletion */}
      {deleteTokenConfirmVisible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm select-none animate-in fade-in duration-200">
          <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-error/10 text-error rounded-xl">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <h4 className="font-display font-bold text-base text-on-surface">
                {t("settings.revoke_api_title")}
              </h4>
            </div>
            <p className="text-xs font-semibold text-on-surface-variant leading-relaxed">
              {t("settings.revoke_api_desc")}
            </p>
            <div className="flex justify-end gap-2.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteTokenConfirmVisible(false)}
                className="font-bold text-xs"
              >
                {t("common.cancel")}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={executeDeleteToken}
                className="font-bold text-xs"
              >
                {t("settings.revoke")}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* UI Confirmation Modal for Domain Deletion */}
      {removeDomainConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm select-none animate-in fade-in duration-200">
          <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-error/10 text-error rounded-xl">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <h4 className="font-display font-bold text-base text-on-surface">
                {t("settings.disconnect_domain")}
              </h4>
            </div>
            <p className="text-xs font-semibold text-on-surface-variant leading-relaxed">
              {t("settings.disconnect_domain_desc")}
            </p>
            <div className="flex justify-end gap-2.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setRemoveDomainConfirmId(null)}
                className="font-bold text-xs"
              >
                {t("common.cancel")}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => executeRemoveDomain(removeDomainConfirmId)}
                className="font-bold text-xs"
              >
                {t("settings.remove")}
              </Button>
            </div>
          </div>
        </div>
      )}
      <AppToast
        tone={toastError ? "error" : "success"}
        message={toastError || toastSuccess}
        visible={Boolean(toastError || toastSuccess)}
        onClose={clearToast}
      />
    </MotionDiv>
  );
}
