import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  User,
  Save,
  CheckCircle2,
  ShieldCheck,
  Link,
  Settings,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { CloudflareIntegrator } from "../components/common/cloudflare-integrator";
import cloudflareLogo from "../assets/cloudflare-svgrepo-com.svg";
import {
  AuthSession,
  getStoredAuthProvider,
  useChangePassword,
  useUpdateProfile,
} from "../lib/api";

const MotionDiv = motion.div as any;

interface SettingsRouteProps {
  session: AuthSession;
}

export default function SettingsRoute({ session }: SettingsRouteProps) {
  const { i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<"profile" | "security" | "preferences" | "cloudflare">(
    session.onboarding_required ? "cloudflare" : "profile",
  );
  const [name, setName] = useState(session.display_name);
  const [email, setEmail] = useState(session.email);
  const [saveStatus, setSaveStatus] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [lang, setLang] = useState(localStorage.getItem("sicurre_lang") || "fr");
  const [theme, setTheme] = useState(localStorage.getItem("sicurre_theme") || "light");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const updateProfileMutation = useUpdateProfile();
  const changePasswordMutation = useChangePassword();
  const authProvider = getStoredAuthProvider();

  useEffect(() => {
    setName(session.display_name);
    setEmail(session.email);
    if (session.onboarding_required) {
      setActiveTab("cloudflare");
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
      setPasswordError("Tous les champs sont obligatoires.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("Les nouveaux mots de passe ne correspondent pas.");
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError("Le nouveau mot de passe doit contenir au moins 8 caractères.");
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
      setPasswordError(error instanceof Error ? error.message : "Impossible de modifier le mot de passe.");
    }
  };

  const saveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError("");
    try {
      await updateProfileMutation.mutateAsync({ display_name: name });
      setSaveStatus(true);
      setTimeout(() => setSaveStatus(false), 3000);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Impossible d'enregistrer le profil.");
    }
  };

  const tabs = [
    { id: "profile", label: "Mon Profil", icon: User },
    { id: "security", label: "Sécurité", icon: ShieldCheck },
    { id: "preferences", label: "Préférences", icon: Settings },
    { id: "cloudflare", label: "Intégrations", icon: Link },
  ];

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

      {/* Two-Column Split Layout */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
        {/* Left Column: Navigation Sidebar */}
        <div className="col-span-12 md:col-span-3 space-y-1.5 bg-white border border-border-subtle rounded-xl p-3.5">
          {tabs.map((tab) => {
            const IconComp = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer text-left border-l-2 outline-none ${
                  isActive
                    ? "bg-primary/[0.04] text-primary border-primary"
                    : "text-on-surface-variant hover:bg-surface-low hover:text-on-surface border-transparent"
                }`}
              >
                <IconComp className={`w-4 h-4 ${isActive ? "text-primary" : "text-on-surface-variant/70"}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Right Column: Tab Content */}
        <div className="col-span-12 md:col-span-9 space-y-6">
          {/* Profile Tab */}
          {activeTab === "profile" && (
            <div className="bg-white rounded-xl border border-border-subtle p-6">
              <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
                <User className="w-5 h-5 text-primary" />
                <h3 className="font-display font-semibold text-[17px] text-on-surface">Personal Information</h3>
              </div>
              <form onSubmit={saveSettings} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Input label="Full Name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
                  <Input label="Email Address" type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled />
                </div>

                <div className="rounded-xl border border-border-subtle bg-surface-low/40 px-4 py-3 text-sm text-on-surface-variant">
                  <p>
                    Rôle actuel : <span className="font-semibold text-on-surface">{session.is_platform_admin ? "Sicurre Admin" : "Owner du workspace"}</span>
                  </p>
                  <p className="mt-1">
                    Cette session ne doit voir que ses propres données et intégrations.
                  </p>
                </div>

                {saveStatus && (
                  <div className="p-3 bg-safe/[0.06] border border-safe/15 text-safe text-sm rounded-lg font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>Modifications enregistrées avec succès.</span>
                  </div>
                )}
                {saveError && <p className="text-xs text-error font-semibold">{saveError}</p>}

                <div className="flex justify-end pt-2">
                  <Button type="submit" className="gap-2 uppercase tracking-wider text-[12px] font-bold">
                    <Save className="w-4 h-4" />
                    Update Profile
                  </Button>
                </div>
              </form>
            </div>
          )}

          {/* Security Tab */}
          {activeTab === "security" && (
            <div className="bg-white rounded-xl border border-border-subtle p-6">
              <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
                <ShieldCheck className="w-5 h-5 text-primary" />
                <h3 className="font-display font-semibold text-[17px] text-on-surface">Sécurité du compte</h3>
              </div>

              {authProvider === "google" ? (
                <div className="p-4 bg-primary/[0.04] border border-primary/10 rounded-xl space-y-2">
                  <p className="text-sm font-semibold text-primary">Connexion via Google Workspace</p>
                  <p className="text-xs text-on-surface-variant leading-relaxed">
                    Votre compte Sicurre est authentifié via votre espace Google. La gestion de votre mot de passe et des paramètres d'authentification à double facteur (MFA) est directement gérée par Google Workspace.
                  </p>
                </div>
              ) : (
                <form onSubmit={handlePasswordChange} className="space-y-4">
                  <Input
                    label="Mot de passe actuel"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  <Input
                    label="Nouveau mot de passe"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  <Input
                    label="Confirmer le nouveau mot de passe"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  {passwordError && (
                    <p className="text-xs text-error font-semibold">{passwordError}</p>
                  )}
                  {passwordSuccess && (
                    <div className="p-3 bg-safe/[0.06] border border-safe/15 text-safe text-sm rounded-lg font-medium flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 shrink-0" />
                      <span>Mot de passe mis à jour avec succès.</span>
                    </div>
                  )}
                  <div className="flex justify-end pt-2">
                    <Button type="submit" className="uppercase tracking-wider text-[12px] font-bold" disabled={changePasswordMutation.isPending}>
                      Mettre à jour le mot de passe
                    </Button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Preferences Tab */}
          {activeTab === "preferences" && (
            <div className="bg-white rounded-xl border border-border-subtle p-6">
              <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
                <Settings className="w-5 h-5 text-primary" />
                <h3 className="font-display font-semibold text-[17px] text-on-surface">Préférences de l'application</h3>
              </div>
              <div className="space-y-6">
                <div className="flex items-center justify-between py-2 border-b border-border-subtle/50">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-body-md font-semibold text-on-surface">Langue de l'interface</span>
                    <span className="text-body-sm text-on-surface-variant/70">Sélectionnez la langue d'affichage des menus et tableaux de bord.</span>
                  </div>
                  <select
                    value={lang}
                    onChange={(e) => handleLanguageChange(e.target.value)}
                    className="px-3.5 py-2 bg-surface-lowest border border-border-subtle rounded-lg text-body-md text-on-surface focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none cursor-pointer"
                  >
                    <option value="fr">Français</option>
                    <option value="en">English</option>
                  </select>
                </div>

                <div className="flex items-center justify-between py-2">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-body-md font-semibold text-on-surface">Thème visuel</span>
                    <span className="text-body-sm text-on-surface-variant/70">Basculez entre l'interface claire et l'interface sombre.</span>
                  </div>
                  <select
                    value={theme}
                    onChange={(e) => handleThemeChange(e.target.value)}
                    className="px-3.5 py-2 bg-surface-lowest border border-border-subtle rounded-lg text-body-md text-on-surface focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none cursor-pointer"
                  >
                    <option value="light">Mode Clair</option>
                    <option value="dark">Mode Sombre</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {activeTab === "cloudflare" && (
            <div className="space-y-5">
              {session.onboarding_required && (
                <div className="rounded-xl border border-primary/15 bg-primary/[0.04] p-4 text-sm text-on-surface">
                  <p className="font-semibold text-primary">Étape suivante recommandée</p>
                  <p className="mt-1 text-on-surface-variant">
                    Aucun domaine n'est encore protégé pour ce compte. Configurez Cloudflare ci-dessous pour démarrer les premiers scans entrants.
                  </p>
                </div>
              )}
              <div className="bg-white rounded-xl border border-border-subtle p-6">
                <div className="flex items-center justify-between mb-1 pb-4 border-b border-border-subtle">
                  <div className="flex items-center gap-2.5">
                    <img src={cloudflareLogo} className="w-5 h-5 object-contain" />
                    <div>
                      <h3 className="font-display font-semibold text-[17px] text-on-surface">Cloudflare</h3>
                      <p className="text-[11px] text-on-surface-variant mt-0.5">
                        Configuration de la passerelle d'interception et de routage.
                      </p>
                    </div>
                  </div>
                </div>
                <div className="pt-4">
                  <CloudflareIntegrator userEmail={session.email} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </MotionDiv>
  );
}
