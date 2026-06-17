import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Shield,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  Lock,
  Mail,
  Server,
  Link2,
  UserCheck,
  RotateCcw,
  CheckCircle2,
  Globe,
} from "lucide-react";
import { motion } from "framer-motion";
import serverRoomImg from "../assets/server-room.png";
import sicurreLogo from "../assets/sicurre.svg";
import { EmailGatewayAnimation } from "../components/landing/email-gateway-animation";

const MotionDiv = motion.div as any;

interface LandingRouteProps {
  onNavigateToLogin: () => void;
  onNavigateToSignUp: () => void;
}

/* ── Intersection Observer hook for scroll-triggered animations ── */
function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [isInView, setIsInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setIsInView(true); },
      { threshold },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, isInView };
}

function FadeInSection({ children, className = "", delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  const { ref, isInView } = useInView();
  return (
    <MotionDiv
      ref={ref}
      initial={{ opacity: 0, y: 32 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.55, ease: "easeOut", delay }}
      className={className}
    >
      {children}
    </MotionDiv>
  );
}

/* ── Language Switcher ── */
function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const currentLang = i18n.language;

  const toggleLang = () => {
    const newLang = currentLang === "fr" ? "en" : "fr";
    i18n.changeLanguage(newLang);
    localStorage.setItem("sicurre_lang", newLang);
  };

  return (
    <button
      onClick={toggleLang}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-low/70 hover:bg-surface-container border border-border-subtle text-[12px] font-bold text-on-surface-variant transition-all cursor-pointer select-none"
      title={currentLang === "fr" ? "Switch to English" : "Passer en français"}
    >
      <Globe className="w-3.5 h-3.5" />
      <span>{currentLang === "fr" ? "FR" : "EN"}</span>
      <span className="text-on-surface-variant/40">|</span>
      <span className="text-on-surface-variant/50">{currentLang === "fr" ? "EN" : "FR"}</span>
    </button>
  );
}

export default function LandingRoute({ onNavigateToLogin, onNavigateToSignUp }: LandingRouteProps) {
  const { t } = useTranslation();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const features = [
    {
      icon: Link2,
      title: t("landing.feat_links_title"),
      desc: t("landing.feat_links_desc"),
    },
    {
      icon: UserCheck,
      title: t("landing.feat_identity_title"),
      desc: t("landing.feat_identity_desc"),
    },
    {
      icon: RotateCcw,
      title: t("landing.feat_remediation_title"),
      desc: t("landing.feat_remediation_desc"),
    },
  ];

  const marqueeItems = [
    { icon: Shield, label: "ARCHITECTURE ZERO-TRUST" },
    { icon: ShieldAlert, label: "DÉTECTION IA AVANCÉE" },
    { icon: Lock, label: "INTÉGRATION SAML/SSO" },
    { icon: Mail, label: "SÉCURITÉ E-MAIL NATIVE" },
    { icon: ShieldCheck, label: "CONFORMITÉ RGPD" },
    { icon: Server, label: "ANALYSE TEMPS RÉEL" },
  ];

  return (
    <div className="min-h-screen font-sans select-none relative overflow-x-hidden">
      {/* ── Sticky Header ── */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-white/90 backdrop-blur-lg border-b border-border-subtle shadow-[0_1px_3px_rgba(0,0,0,0.05)] py-3"
            : "bg-transparent py-5"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre" className="w-10 h-10" />
            <span className={`font-display font-bold text-xl tracking-tight ${scrolled ? "text-on-surface" : "text-on-surface"}`}>
              Sicurre
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-[13px] font-medium text-on-surface-variant">
            <a href="#features" className="hover:text-primary transition-colors">{t("landing.nav_features")}</a>
            <a href="#pricing" className="hover:text-primary transition-colors">{t("landing.nav_pricing")}</a>
            <a href="#compliance" className="hover:text-primary transition-colors">{t("landing.nav_resources")}</a>
          </nav>

          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <button
              onClick={onNavigateToLogin}
              className="text-[13px] font-semibold text-on-surface-variant hover:text-primary transition-colors cursor-pointer hidden sm:block"
            >
              {t("landing.nav_login")}
            </button>
            <button
              onClick={onNavigateToSignUp}
              className="px-4 py-2 bg-primary hover:bg-navy-dark text-on-primary rounded-lg text-[13px] font-semibold transition-all active:scale-[0.97] cursor-pointer shadow-sm"
            >
              {t("landing.nav_cta")}
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero Section ── */}
      <section className="relative bg-white pt-28 pb-16 lg:pt-36 lg:pb-24 overflow-hidden">
        {/* Subtle grid pattern */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,56,164,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,56,164,0.03)_1px,transparent_1px)] bg-[size:4rem_4rem]" />
        {/* Soft radial glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-[radial-gradient(ellipse,rgba(27,79,204,0.06),transparent_60%)]" />

        <div className="max-w-7xl mx-auto px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start relative z-10">
          {/* Left: Copy */}
          <div className="lg:col-span-7 space-y-7 pt-6">
            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.08 }}
            >
              <h1 className="font-display font-bold text-[clamp(2rem,5vw,3.25rem)] leading-[1.1] tracking-tight text-on-surface">
                {t("landing.hero_title_1")}{" "}
                <br className="hidden lg:block" />
                {t("landing.hero_title_2")}{" "}
                <br className="hidden lg:block" />
                {t("landing.hero_title_3")}{" "}
                <span className="text-primary italic">{t("landing.hero_title_accent")}</span>
              </h1>
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.16 }}
              className="text-[17px] text-on-surface-variant leading-relaxed max-w-xl"
            >
              {t("landing.hero_desc")}
            </MotionDiv>

            {/* CTA Buttons */}
            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.24 }}
              className="flex flex-col sm:flex-row items-start gap-3 pt-2"
            >
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-7 py-3.5 bg-primary hover:bg-navy-dark text-on-primary font-semibold rounded-lg shadow-md shadow-primary/20 active:scale-[0.97] transition-all cursor-pointer text-[15px]"
              >
                <span>{t("landing.cta_trial")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={onNavigateToLogin}
                className="flex items-center gap-2 px-7 py-3.5 bg-white hover:bg-surface-low border border-border-subtle text-on-surface font-semibold rounded-lg active:scale-[0.97] transition-all cursor-pointer text-[15px]"
              >
                <span>{t("landing.cta_demo")}</span>
              </button>
            </MotionDiv>

            {/* Trust strip */}
            <MotionDiv
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="flex items-center gap-4 pt-6"
            >
              {/* Avatar stack */}
              <div className="flex -space-x-2">
                {["#6366f1", "#0ea5e9", "#10b981", "#f59e0b"].map((bg, i) => (
                  <div
                    key={i}
                    className="w-8 h-8 rounded-full ring-2 ring-white flex items-center justify-center text-white text-[10px] font-bold"
                    style={{ backgroundColor: bg }}
                  >
                    {["JD", "ML", "SB", "AK"][i]}
                  </div>
                ))}
              </div>
              <span className="text-sm text-on-surface-variant">
                {t("landing.trust_label")} <strong className="text-on-surface">{t("landing.trust_count")}</strong> {t("landing.trust_suffix")}
              </span>
            </MotionDiv>
          </div>

          {/* Right: Email Gateway Animation */}
          <div className="lg:col-span-5 flex justify-center lg:justify-end">
            <MotionDiv
              initial={{ opacity: 0, scale: 0.96, y: 24 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
            >
              <EmailGatewayAnimation />
            </MotionDiv>
          </div>
        </div>
      </section>

      {/* ── Feature Marquee ── */}
      <section className="bg-[#0B1426] border-y border-white/5 py-5 overflow-hidden">
        <div className="relative flex max-w-full">
          <div className="animate-marquee flex gap-10 whitespace-nowrap text-white/70 text-[10px] font-bold tracking-[0.15em] uppercase shrink-0">
            {[...marqueeItems, ...marqueeItems].map((item, idx) => {
              const Icon = item.icon;
              return (
                <span key={idx} className="flex items-center gap-2">
                  <Icon className="w-4 h-4" />
                  {item.label}
                </span>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Precision-Engineered Protection ── */}
      <section id="features" className="bg-white py-20 lg:py-28">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <FadeInSection className="text-center max-w-2xl mx-auto mb-16 space-y-4">
            <h2 className="font-display font-bold text-[clamp(1.5rem,3vw,2.25rem)] leading-tight tracking-tight text-on-surface">
              {t("landing.features_title")}
            </h2>
            <p className="text-on-surface-variant text-[16px] leading-relaxed">
              {t("landing.features_desc")}
            </p>
          </FadeInSection>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {features.map((feat, idx) => {
              const Icon = feat.icon;
              return (
                <FadeInSection key={idx} delay={idx * 0.08}>
                  <div className="p-7 rounded-2xl bg-white border border-border-subtle hover:border-primary/20 hover:shadow-lg hover:shadow-primary/[0.04] transition-all duration-300 text-left space-y-4 group h-full">
                    <div className="p-3 bg-surface-low border border-border-subtle text-on-surface rounded-xl w-fit group-hover:bg-primary/[0.06] group-hover:text-primary group-hover:border-primary/15 transition-all duration-300">
                      <Icon className="w-5 h-5 stroke-[1.5]" />
                    </div>
                    <h3 className="text-[17px] font-bold text-on-surface font-display">
                      {feat.title}
                    </h3>
                    <p className="text-sm text-on-surface-variant leading-relaxed">
                      {feat.desc}
                    </p>
                  </div>
                </FadeInSection>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── High-Stakes Environment — Dark section with server image ── */}
      <section className="bg-[#0B1426] text-white py-20 lg:py-28 overflow-hidden">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <FadeInSection className="space-y-8">
            <h2 className="font-display font-bold text-[clamp(1.5rem,3vw,2.25rem)] leading-tight tracking-tight">
              {t("landing.dark_title")}
            </h2>
            <p className="text-white/60 text-[16px] leading-relaxed max-w-lg">
              {t("landing.dark_desc")}
            </p>
            <ul className="space-y-4">
              {[
                t("landing.dark_check_1"),
                t("landing.dark_check_2"),
                t("landing.dark_check_3"),
              ].map((item, i) => (
                <li key={i} className="flex items-start gap-3 text-[15px] text-white/80">
                  <CheckCircle2 className="w-5 h-5 text-safe shrink-0 mt-0.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </FadeInSection>

          <FadeInSection delay={0.15} className="relative">
            <div className="rounded-2xl overflow-hidden shadow-2xl shadow-black/40 border border-white/[0.06]">
              <img
                src={serverRoomImg}
                alt="Infrastructure sécurisée de centre de données Sicurre"
                className="w-full h-auto object-cover"
                loading="lazy"
              />
            </div>
          </FadeInSection>
        </div>
      </section>

      {/* ── CTA Section ── */}
      <section className="bg-primary py-20 lg:py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(0,0,0,0.12),transparent_60%)]" />
        <div className="max-w-3xl mx-auto px-6 lg:px-8 text-center space-y-6 relative z-10">
          <FadeInSection>
            <h2 className="font-display font-bold text-[clamp(1.75rem,4vw,2.5rem)] leading-tight tracking-tight text-white">
              {t("landing.cta_section_title")}
            </h2>
          </FadeInSection>
          <FadeInSection delay={0.06}>
            <p className="text-white/80 text-[16px] leading-relaxed max-w-xl mx-auto">
              {t("landing.cta_section_desc")}
            </p>
          </FadeInSection>
          <FadeInSection delay={0.12}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-7 py-3.5 bg-white text-primary hover:bg-surface-low font-bold rounded-lg shadow-lg transition-all active:scale-[0.97] cursor-pointer text-[15px]"
              >
                <span>{t("landing.cta_section_trial")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={onNavigateToLogin}
                className="flex items-center gap-2 px-7 py-3.5 bg-white/10 hover:bg-white/15 border border-white/20 text-white font-semibold rounded-lg transition-all active:scale-[0.97] cursor-pointer text-[15px]"
              >
                <span>{t("landing.cta_section_demo")}</span>
              </button>
            </div>
            <p className="text-white/50 text-[12px] mt-4">
              {t("landing.cta_no_card")}
            </p>
          </FadeInSection>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="bg-[#05080e] text-white/70 border-t border-white/5 py-14">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-8 mb-12">
            {/* Brand Column */}
            <div className="col-span-2 md:col-span-1 space-y-4">
              <div className="flex items-center gap-2.5">
                <img src={sicurreLogo} alt="Sicurre" className="w-9 h-9" />
                <span className="font-display font-bold text-white text-[17px]">Sicurre</span>
              </div>
              <p className="text-[12px] text-white/40 leading-relaxed max-w-[200px]">
                {t("landing.footer_tagline")}
              </p>
            </div>

            {/* Product */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">{t("landing.footer_product")}</span>
              <ul className="text-[12px] space-y-2.5">
                <li><a href="#" className="hover:text-white transition-colors">{t("landing.nav_features")}</a></li>
                <li><a href="#" className="hover:text-white transition-colors">{t("landing.nav_pricing")}</a></li>
                <li><a href="#" className="hover:text-white transition-colors">{t("landing.nav_resources")}</a></li>
              </ul>
            </div>

            {/* Resources */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">{t("landing.footer_resources")}</span>
              <ul className="text-[12px] space-y-2.5">
                <li><a href="#" className="hover:text-white transition-colors">Blog</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Documentation</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Support</a></li>
                <li><a href="#" className="hover:text-white transition-colors">API</a></li>
              </ul>
            </div>

            {/* Company */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">{t("landing.footer_company")}</span>
              <ul className="text-[12px] space-y-2.5">
                <li><a href="#" className="hover:text-white transition-colors">À propos</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Contact</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Confidentialité</a></li>
                <li><a href="#" className="hover:text-white transition-colors">CGU</a></li>
              </ul>
            </div>

            {/* Trust */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">{t("landing.footer_trust")}</span>
              <div className="flex flex-wrap gap-2">
                <span className="text-[10px] font-bold text-white/60 bg-white/5 border border-white/10 px-2.5 py-1 rounded-md">SOC 2</span>
                <span className="text-[10px] font-bold text-white/60 bg-white/5 border border-white/10 px-2.5 py-1 rounded-md">RGPD</span>
              </div>
            </div>
          </div>

          {/* Bottom Bar */}
          <div className="border-t border-white/5 pt-6 flex flex-col sm:flex-row items-center justify-between text-[11px] text-white/30 gap-3">
            <span>{t("landing.footer_copyright")}</span>
            <span>{t("landing.footer_slogan")}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
