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

function LanguageSwitcher({ scrolled }: { scrolled: boolean }) {
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
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-[14px] font-medium transition-all cursor-pointer select-none ${
        scrolled
          ? "bg-slate-50 hover:bg-slate-100 border-slate-200 text-slate-700"
          : "bg-white/5 hover:bg-white/10 border-white/10 text-white/80"
      }`}
      title={currentLang === "fr" ? "Switch to English" : "Passer en français"}
    >
      <span>{currentLang === "fr" ? "🇫🇷" : "🇬🇧"}</span>
      <span className="opacity-30">|</span>
      <span className="opacity-50 grayscale hover:grayscale-0 transition-all">{currentLang === "fr" ? "🇬🇧" : "🇫🇷"}</span>
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
      icon: ShieldCheck,
      title: t("landing.feat_ai_title"),
      desc: t("landing.feat_ai_desc"),
    },
    {
      icon: RotateCcw,
      title: t("landing.feat_remediation_title"),
      desc: t("landing.feat_remediation_desc"),
    },
    {
      icon: Lock,
      title: t("landing.feat_dmarc_title"),
      desc: t("landing.feat_dmarc_desc"),
    },
  ];

  const marqueeItems = [
    { icon: Shield, label: "ARCHITECTURE ZERO-TRUST" },
    { icon: ShieldCheck, label: "DÉTECTION IA AVANCÉE" },
    { icon: Lock, label: "INTÉGRATION GMAIL NATIVE" },
    { icon: Mail, label: "SÉCURITÉ E-MAIL FR SOUVERAIN" },
    { icon: ShieldCheck, label: "CONFORMITÉ RGPD" },
    { icon: Server, label: "ANALYSE TEMPS RÉEL" },
  ];

  return (
    <div className="min-h-screen font-sans select-none relative overflow-x-hidden bg-white text-slate-900">
      
      {/* ── Scroll-Dependent Sticky Header ── */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-white/90 backdrop-blur-lg border-b border-slate-200/80 shadow-[0_1px_3px_rgba(0,0,0,0.05)] py-3"
            : "bg-transparent py-5"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-12 h-12" />
            <span className={`font-display font-bold text-2xl tracking-tight ${scrolled ? "text-slate-900" : "text-white"}`}>
              Sicurre
            </span>
          </div>

          <nav className={`hidden md:flex items-center gap-8 text-[13px] font-semibold transition-colors ${
            scrolled ? "text-slate-600 hover:text-primary" : "text-white/70 hover:text-white"
          }`}>
            <a href="#features" className="transition-colors">{t("landing.nav_features")}</a>
            <a href="#cta" className="transition-colors">Sécuriser</a>
          </nav>

          <div className="flex items-center gap-4">
            <LanguageSwitcher scrolled={scrolled} />
            <button
              onClick={onNavigateToLogin}
              className={`text-[13px] font-semibold transition-colors cursor-pointer hidden sm:block ${
                scrolled ? "text-slate-600 hover:text-primary" : "text-white/80 hover:text-white"
              }`}
            >
              {t("landing.nav_login")}
            </button>
            <button
              onClick={onNavigateToSignUp}
              className={`px-4.5 py-2 rounded-lg text-[13px] font-bold transition-all active:scale-[0.97] cursor-pointer shadow-sm ${
                scrolled 
                  ? "bg-primary hover:bg-navy-dark text-on-primary"
                  : "bg-white hover:bg-white/90 text-primary"
              }`}
            >
              {t("landing.nav_cta")}
            </button>
          </div>
        </div>
      </header>

      {/* ── 100vh Hero Section (Dark Theme Visual Anchor) ── */}
      <section className="relative w-full h-screen min-h-[600px] max-h-[850px] flex flex-col justify-between bg-black text-white overflow-hidden">
        {/* Subtle grid layout */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.012)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.012)_1px,transparent_1px)] bg-[size:4rem_4rem]" />
        
        {/* Top Right Silk Wave */}
        <div className="absolute top-0 right-0 w-[55%] h-[65%] select-none pointer-events-none opacity-40 z-0">
          <svg className="w-full h-full" viewBox="0 0 600 600" fill="none" preserveAspectRatio="none">
            <defs>
              <linearGradient id="landing-silk-1" x1="100%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.12" />
                <stop offset="40%" stopColor="#475569" stopOpacity="0.04" />
                <stop offset="100%" stopColor="#000000" stopOpacity="0.9" />
              </linearGradient>
              <linearGradient id="landing-silk-2" x1="100%" y1="0%" x2="30%" y2="80%">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.08" />
                <stop offset="100%" stopColor="#000000" stopOpacity="0.95" />
              </linearGradient>
            </defs>
            <path d="M250 0 C380 180, 200 380, 600 480 L600 0 Z" fill="url(#landing-silk-1)" />
            <path d="M380 0 C450 140, 320 280, 600 380 L600 0 Z" fill="url(#landing-silk-2)" opacity="0.6" />
          </svg>
        </div>

        {/* Bottom Left Silk Wave */}
        <div className="absolute bottom-0 left-0 w-[50%] h-[60%] select-none pointer-events-none opacity-35 z-0">
          <svg className="w-full h-full" viewBox="0 0 600 600" fill="none" preserveAspectRatio="none">
            <defs>
              <linearGradient id="landing-silk-3" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.1" />
                <stop offset="50%" stopColor="#475569" stopOpacity="0.03" />
                <stop offset="100%" stopColor="#000000" stopOpacity="0.9" />
              </linearGradient>
            </defs>
            <path d="M0 200 C180 320, 250 480, 350 600 L0 600 Z" fill="url(#landing-silk-3)" />
          </svg>
        </div>

        {/* Hero content grid */}
        <div className="flex-1 w-full max-w-[1440px] mx-auto px-6 lg:px-12 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center relative z-10 pt-24 pb-4">
          <div className="lg:col-span-6 space-y-5 flex flex-col justify-center">
            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.08 }}
            >
              <h1 className="font-display font-extrabold text-4xl sm:text-5xl lg:text-6xl leading-[1.08] tracking-tight text-white">
                {t("landing.hero_title_1")}{" "}
                {t("landing.hero_title_2")}{" "}
                <span className="text-white/50 font-normal">{t("landing.hero_title_3")}</span>{" "}
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400 font-bold">
                  {t("landing.hero_title_accent")}
                </span>
              </h1>
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.16 }}
              className="text-sm sm:text-base text-slate-300 leading-relaxed max-w-xl font-medium"
            >
              {t("landing.hero_desc")}
            </MotionDiv>

            {/* High contrast white buttons on dark background */}
            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.24 }}
              className="flex flex-row items-center gap-4 pt-1"
            >
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-6 py-3 bg-white hover:bg-slate-100 text-slate-950 font-bold rounded-xl shadow-[0_4px_25px_rgba(255,255,255,0.18)] active:scale-[0.97] transition-all cursor-pointer text-[13px]"
              >
                <span>{t("landing.cta_trial")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </MotionDiv>
          </div>

          <div className="lg:col-span-6 flex justify-center lg:justify-end h-full max-h-[380px]">
            <MotionDiv
              initial={{ opacity: 0, filter: "blur(10px)" }}
              animate={{ opacity: 1, filter: "blur(0px)" }}
              transition={{ duration: 0.8, delay: 0.3, ease: "easeOut" }}
              className="w-full h-full flex items-center"
            >
              {/* Restored 3D Industrial Pneumatic Email Sorting Pipeline Animation */}
              <EmailGatewayAnimation />
            </MotionDiv>
          </div>
        </div>

        {/* Marquee anchored at hero bottom */}
        <div className="w-full bg-white/[0.02] border-t border-white/10 py-5 mt-auto relative z-20 backdrop-blur-sm">
          <div className="relative flex max-w-full overflow-hidden">
            <div className="animate-marquee flex gap-12 whitespace-nowrap text-white text-[12px] font-bold tracking-[0.15em] uppercase shrink-0">
              {[...marqueeItems, ...marqueeItems].map((item, idx) => {
                const Icon = item.icon;
                return (
                  <span key={idx} className="flex items-center gap-2.5">
                    <Icon className="w-4.5 h-4.5 text-[#1B4FCC]" />
                    {item.label}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ── Section 2: Security & Protection Features (Light Theme Grid) ── */}
      <section id="features" className="bg-[#faf8ff] py-20 lg:py-28 relative z-10">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 space-y-16">
          
          <FadeInSection className="text-center max-w-2xl mx-auto space-y-4">
            <span className="text-[11px] font-bold tracking-widest text-primary uppercase">FONCTIONNALITÉS</span>
            <h2 className="font-display font-bold text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-tight text-slate-900">
              {t("landing.features_title")}
            </h2>
            <p className="text-slate-600 text-[15px] leading-relaxed">
              {t("landing.features_desc")}
            </p>
          </FadeInSection>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {features.map((feat, idx) => {
              return (
                <FadeInSection key={idx} delay={idx * 0.05}>
                  <div className="p-8 rounded-2xl bg-white border border-slate-200/80 hover:border-slate-300 transition-all duration-200 text-left space-y-3 h-full">
                    <h3 className="text-[20px] font-bold text-slate-900 font-display leading-snug tracking-tight">
                      {feat.title}
                    </h3>
                    <p className="text-sm text-slate-600 leading-relaxed font-sans">
                      {feat.desc}
                    </p>
                  </div>
                </FadeInSection>
              );
            })}
          </div>

        </div>
      </section>

      {/* ── Section 4: Call to Action (Light Theme) ── */}
      <section id="cta" className="bg-white py-20 lg:py-24 relative overflow-hidden border-t border-slate-200/80">
        <div className="max-w-3xl mx-auto px-6 lg:px-8 text-center space-y-6 relative z-10">
          
          <FadeInSection className="space-y-4">
            <span className="text-[11px] font-bold tracking-widest text-primary uppercase">SÉCURISATION RAPIDE</span>
            <h2 className="font-display font-bold text-[clamp(1.75rem,4vw,2.5rem)] leading-tight tracking-tight text-slate-900">
              {t("landing.cta_section_title")}
            </h2>
            <p className="text-slate-600 text-[15px] leading-relaxed max-w-xl mx-auto">
              {t("landing.cta_section_desc")}
            </p>
          </FadeInSection>

          {/* Core colors CTA buttons: Navy Blue and slate outlines */}
          <FadeInSection delay={0.06}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 pt-4">
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-7 py-3.5 bg-primary text-white hover:bg-navy-dark font-bold rounded-xl shadow-md transition-all active:scale-[0.97] cursor-pointer text-[14px]"
              >
                <span>{t("landing.cta_section_trial")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
            <div className="mt-4 flex justify-center">
              <span className="text-slate-900 font-black text-[13px] tracking-wider uppercase bg-slate-100 border border-slate-200 px-4 py-1.5 rounded-full shadow-sm">
                {t("landing.cta_no_card")}
              </span>
            </div>
          </FadeInSection>

          {/* Safe Checklists */}
          <FadeInSection delay={0.12} className="pt-8 flex flex-wrap justify-center gap-x-8 gap-y-3 opacity-80 text-[12px] text-slate-600 font-semibold">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4.5 h-4.5 text-emerald-600" />
              <span>Conforme RGPD (UE)</span>
            </div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4.5 h-4.5 text-emerald-600" />
              <span>Modèle souverain français</span>
            </div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4.5 h-4.5 text-emerald-600" />
              <span>Intégration instantanée</span>
            </div>
          </FadeInSection>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="bg-[#05080e] text-white/40 border-t border-white/5 py-8 relative z-10">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-8 h-8" />
            <span className="font-display font-bold text-white text-[16px]">Sicurre</span>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-[12px] font-medium">
            <a href="#" className="hover:text-white transition-colors">Mentions légales</a>
            <a href="#" className="hover:text-white transition-colors">Confidentialité</a>
            <a href="#" className="hover:text-white transition-colors">Contact</a>
          </div>
          <div className="text-[11px] text-white/30">
            {t("landing.footer_copyright")}
          </div>
        </div>
      </footer>
    </div>
  );
}
