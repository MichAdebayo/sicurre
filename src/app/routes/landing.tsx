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
  ChevronDown,
  Globe,
  CreditCard,
  Search,
  FileText,
  TrendingUp,
} from "lucide-react";
import { motion } from "framer-motion";
import serverRoomImg from "../assets/server-room.png";
import sicurreLogo from "../assets/sicurre.svg";
import { EmailGatewayAnimation } from "../components/landing/email-gateway-animation";

const MotionDiv = motion.div as any;

interface LandingRouteProps {
  onNavigateToLogin: () => void;
  onNavigateToSignUp: () => void;
  onNavigateToMentionsLegales: () => void;
  onNavigateToConfidentialite: () => void;
  onNavigateToContact: () => void;
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
  const [isOpen, setIsOpen] = useState(false);
  const currentLang = i18n.language;

  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
    localStorage.setItem("sicurre_lang", lang);
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-[14px] font-medium transition-all cursor-pointer select-none ${
          scrolled
            ? "bg-slate-50 hover:bg-slate-100 border-slate-200 text-slate-700"
            : "bg-white/5 hover:bg-white/10 border-white/10 text-white/80"
        }`}
      >
        <span>{currentLang === "fr" ? "🇫🇷" : "🇬🇧"}</span>
        <ChevronDown className="w-3 h-3 opacity-50" />
      </button>
      {isOpen && (
        <div className={`absolute right-0 mt-1.5 w-32 rounded-xl border shadow-lg py-1 text-[12px] font-semibold text-left z-50 overflow-hidden ${
          scrolled 
            ? "bg-white border border-slate-200 text-slate-800 shadow-slate-200/50" 
            : "bg-[#141414] border border-white/10 text-white shadow-black/50"
        }`}>
          <button
            onClick={() => changeLanguage("fr")}
            className={`w-full px-4 py-2 transition-all flex items-center gap-2 cursor-pointer border-0 outline-none ${
              scrolled
                ? `hover:bg-slate-100 ${currentLang === "fr" ? "text-primary font-bold bg-slate-50" : "text-slate-600"}`
                : `hover:bg-white/5 ${currentLang === "fr" ? "text-[#4a9ed4] font-bold bg-white/5" : "text-white/70"}`
            }`}
          >
            <span>🇫🇷</span>
            <span>Français</span>
          </button>
          <button
            onClick={() => changeLanguage("en")}
            className={`w-full px-4 py-2 transition-all flex items-center gap-2 cursor-pointer border-0 outline-none ${
              scrolled
                ? `hover:bg-slate-100 ${currentLang === "en" ? "text-primary font-bold bg-slate-50" : "text-slate-600"}`
                : `hover:bg-white/5 ${currentLang === "en" ? "text-[#4a9ed4] font-bold bg-white/5" : "text-white/70"}`
            }`}
          >
            <span>🇬🇧</span>
            <span>English</span>
          </button>
        </div>
      )}
    </div>
  );
}

export default function LandingRoute({
  onNavigateToLogin,
  onNavigateToSignUp,
  onNavigateToMentionsLegales,
  onNavigateToConfidentialite,
  onNavigateToContact,
}: LandingRouteProps) {
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
      color: "border-primary/20 bg-primary/5 text-primary",
    },
    {
      icon: RotateCcw,
      title: t("landing.feat_remediation_title"),
      desc: t("landing.feat_remediation_desc"),
      color: "border-emerald-500/20 bg-emerald-500/5 text-emerald-600",
    },
    {
      icon: Globe,
      title: t("landing.feat_dmarc_title"),
      desc: t("landing.feat_dmarc_desc"),
      color: "border-amber-500/20 bg-amber-500/5 text-amber-600",
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

      <section className="relative w-full h-screen min-h-[600px] max-h-[850px] flex flex-col justify-between bg-black text-white overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.012)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.012)_1px,transparent_1px)] bg-[size:4rem_4rem]" />
        
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
              className="text-sm sm:text-base text-slate-300 leading-relaxed max-w-xl font-medium text-left"
            >
              {t("landing.hero_desc")}
            </MotionDiv>
            
            <MotionDiv
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              style={{ fontSize: "13px", color: "#888888", marginTop: "8px" }}
              className="text-left font-medium"
            >
              Déjà 200+ PME protégées en France
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.24 }}
              className="flex flex-row items-center gap-4 pt-1"
            >
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-7 py-3.5 bg-primary hover:bg-navy-dark text-on-primary font-semibold rounded-lg shadow-md shadow-primary/20 active:scale-[0.97] transition-all cursor-pointer text-[15px]"
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
              <EmailGatewayAnimation />
            </MotionDiv>
          </div>
        </div>

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

      <section id="features" style={{ backgroundColor: "#000000" }} className="py-20 lg:py-28 relative z-10 overflow-hidden border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 space-y-16 relative z-10">
          
          <FadeInSection className="text-center max-w-2xl mx-auto space-y-4">
            <span className="px-3.5 py-1.5 rounded-full w-fit inline-block text-[11px] font-bold tracking-widest uppercase" style={{ color: "#1B4FCC", backgroundColor: "rgba(27, 79, 204, 0.1)" }}>FONCTIONNALITÉS</span>
            <h2 className="font-display font-bold text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-tight text-white mt-3">
              {t("landing.features_title")}
            </h2>
            <p className="text-[15px] leading-relaxed max-w-xl mx-auto font-medium" style={{ color: "#888888" }}>
              {t("landing.features_desc")}
            </p>
          </FadeInSection>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {features.map((feat, idx) => {
              const IconComponent = feat.icon;
              const featuresConfig = [
                {
                  lineColor: "#1B4FCC",
                  stat: "99.8%",
                  statSize: "22px",
                  label: "Précision de détection",
                  labelColor: "#1B4FCC",
                  iconBg: "rgba(27, 79, 204, 0.12)",
                  iconColor: "#1B4FCC",
                },
                {
                  lineColor: "#10b981",
                  stat: "< 2 sec",
                  statSize: "22px",
                  label: "Remédiation automatique",
                  labelColor: "#10b981",
                  iconBg: "rgba(16, 185, 129, 0.12)",
                  iconColor: "#10b981",
                },
                {
                  lineColor: "#f59e0b",
                  stat: "SPF · DKIM · DMARC",
                  statSize: "16px",
                  label: "Sécurité DNS complète",
                  labelColor: "#f59e0b",
                  iconBg: "rgba(245, 158, 11, 0.12)",
                  iconColor: "#f59e0b",
                },
              ];
              const config = featuresConfig[idx];
              return (
                <FadeInSection key={idx} delay={idx * 0.05}>
                  <div 
                    style={{
                      background: "rgba(255, 255, 255, 0.015)",
                      border: "1px solid rgba(255, 255, 255, 0.06)",
                      backdropFilter: "blur(12px)",
                      WebkitBackdropFilter: "blur(12px)",
                    }}
                    className="relative overflow-hidden text-left flex flex-col justify-between h-full group rounded-xl hover:border-white/15 hover:bg-white/[0.03] hover:shadow-[0_0_30px_rgba(27,79,204,0.08)] transition-all duration-300"
                  >
                    <div style={{ height: "2px", width: "100%", backgroundColor: config.lineColor }} />
                    
                    <div className="p-8 space-y-4 flex-1 flex flex-col justify-between">
                      <div className="space-y-4">
                        <div 
                          className="group-hover:scale-110 group-hover:-translate-y-1 transition-all duration-300"
                          style={{
                            width: "36px",
                            height: "36px",
                            borderRadius: "8px",
                            padding: "8px",
                            backgroundColor: config.iconBg,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <IconComponent style={{ width: "20px", height: "20px", color: config.iconColor }} strokeWidth={1.5} />
                        </div>

                        <div style={{ fontSize: config.statSize, fontWeight: 600, color: "#ffffff" }} className="font-semibold text-[22px]">
                          {config.stat}
                        </div>

                        <div 
                          style={{
                            color: config.labelColor,
                            fontSize: "11px",
                            textTransform: "uppercase",
                            letterSpacing: "0.5px",
                            fontWeight: 600,
                          }}
                        >
                          {config.label}
                        </div>

                        <h3 style={{ color: "#cccccc", fontSize: "13px", fontWeight: 700 }} className="font-display tracking-tight leading-snug">
                          {feat.title}
                        </h3>

                        <p style={{ color: "#888888" }} className="text-sm leading-relaxed">
                          {feat.desc}
                        </p>
                      </div>
                    </div>
                  </div>
                </FadeInSection>
              );
            })}
          </div>
        </div>
      </section>

      <section id="cta" style={{ backgroundColor: "#000000" }} className="py-20 lg:py-24 relative overflow-hidden border-t border-white/5">
        <div className="max-w-3xl mx-auto px-6 lg:px-8 text-center space-y-8 relative z-10">
          
          <FadeInSection className="w-full">
            <div className="flex flex-row items-center justify-center gap-12 sm:gap-16 py-2">
              <div className="text-center">
                <div style={{ fontSize: "28px", fontWeight: 600, color: "#ffffff" }}>200+</div>
                <div style={{ fontSize: "12px", color: "#666666" }} className="mt-1">PME protégées</div>
              </div>
              <div className="text-center">
                <div style={{ fontSize: "28px", fontWeight: 600, color: "#ffffff" }}>1.2M+</div>
                <div style={{ fontSize: "12px", color: "#666666" }} className="mt-1">E-mails analysés</div>
              </div>
              <div className="text-center">
                <div style={{ fontSize: "28px", fontWeight: 600, color: "#ffffff" }}>0</div>
                <div style={{ fontSize: "12px", color: "#666666" }} className="mt-1">Fuite de données</div>
              </div>
            </div>
            <div style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", width: "100%", marginBottom: "32px", marginTop: "32px" }} />
          </FadeInSection>

          <FadeInSection delay={0.04}>
            <div 
              style={{
                maxWidth: "560px",
                background: "rgba(255, 255, 255, 0.015)",
                border: "1px solid rgba(255, 255, 255, 0.06)",
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                padding: "20px",
                margin: "0 auto 32px auto",
              }}
              className="text-left rounded-xl hover:border-white/15 hover:bg-white/[0.03] hover:shadow-[0_0_30px_rgba(27,79,204,0.06)] transition-all duration-300"
            >
              <p style={{ fontSize: "14px", color: "#cccccc", lineHeight: "1.6", marginBottom: "12px" }}>
                "Sicurre a bloqué 3 tentatives de phishing ciblées la première semaine. Intégration en 10 minutes chrono."
              </p>
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div 
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "50%",
                      backgroundColor: "rgba(27, 79, 204, 0.2)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "#1B4FCC",
                      fontSize: "12px",
                      fontWeight: "bold",
                    }}
                  >
                    TM
                  </div>
                  <div>
                    <div style={{ fontSize: "13px", fontWeight: 600, color: "#ffffff" }}>Thomas M.</div>
                    <div style={{ fontSize: "12px", color: "#666666" }}>DSI, PME Logistique · Lyon</div>
                  </div>
                </div>
                <div style={{ color: "#f59e0b", fontSize: "14px", letterSpacing: "1px" }}>
                  ★★★★★
                </div>
              </div>
            </div>
          </FadeInSection>

          <FadeInSection className="space-y-4" delay={0.08}>
            <span className="text-[11px] font-bold tracking-widest uppercase" style={{ color: "#1B4FCC" }}>SÉCURISATION RAPIDE</span>
            <h2 className="font-display font-bold text-[clamp(1.75rem,4vw,2.5rem)] leading-tight tracking-tight mt-1 text-white">
              {t("landing.cta_section_title")}
            </h2>
            <p className="text-[15px] leading-relaxed max-w-xl mx-auto font-medium" style={{ color: "#888888" }}>
              {t("landing.cta_section_desc")}
            </p>
          </FadeInSection>
 
          <FadeInSection delay={0.12}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 pt-2">
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-7 py-3.5 bg-primary hover:bg-navy-dark text-on-primary font-bold rounded-xl shadow-md hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer text-[14px]"
              >
                <span>{t("landing.cta_section_trial")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
            <div style={{ fontSize: "13px", color: "#555555", marginTop: "8px" }} className="text-center font-medium">
              {t("landing.cta_no_card")}
            </div>
          </FadeInSection>
 
          <FadeInSection delay={0.16} className="pt-4 flex flex-wrap justify-center gap-x-8 gap-y-3 opacity-90 text-[13px] font-semibold">
            <div className="flex items-center gap-2" style={{ color: "#888888" }}>
              <ShieldCheck className="w-4.5 h-4.5" style={{ color: "#10b981" }} />
              <span>Conforme RGPD (UE)</span>
            </div>
            <div className="flex items-center gap-2" style={{ color: "#888888" }}>
              <ShieldCheck className="w-4.5 h-4.5" style={{ color: "#10b981" }} />
              <span>Modèle souverain français</span>
            </div>
            <div className="flex items-center gap-2" style={{ color: "#888888" }}>
              <ShieldCheck className="w-4.5 h-4.5" style={{ color: "#10b981" }} />
              <span>Intégration instantanée</span>
            </div>
          </FadeInSection>
        </div>
      </section>

      {/* SECTION 4: RESOURCES & INSIGHTS */}
      <section id="resources" style={{ backgroundColor: "#000000" }} className="py-20 lg:py-28 relative z-10 overflow-hidden border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 space-y-12 relative z-10">
          
          <FadeInSection className="text-center max-w-2xl mx-auto space-y-4">
            <span className="px-3.5 py-1.5 rounded-full w-fit inline-block text-[11px] font-bold tracking-widest uppercase" style={{ color: "#1B4FCC", backgroundColor: "rgba(27, 79, 204, 0.1)" }}>
              {t("landing.resources_label")}
            </span>
            <h2 className="font-display font-bold text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-tight text-white mt-3">
              {t("landing.resources_title")}
            </h2>
            <p className="text-[15px] leading-relaxed max-w-xl mx-auto font-medium" style={{ color: "#888888" }}>
              {t("landing.resources_desc")}
            </p>
          </FadeInSection>

          {/* Search bar and Filters */}
          <div className="flex flex-col md:flex-row items-center justify-between gap-4 pt-4 border-b border-white/5 pb-6">
            <div className="relative w-full md:max-w-md">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-[#888888]" />
              <input 
                type="text" 
                placeholder={t("landing.resources_search_placeholder")}
                className="w-full pl-10 pr-4 py-2.5 bg-black/40 border border-white/8 text-sm rounded-xl text-white placeholder-[#555555] focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2 overflow-x-auto max-w-full pb-2 md:pb-0">
              <span className="px-3.5 py-1.5 rounded-full text-[12px] font-semibold bg-primary text-white cursor-pointer transition-all">
                {t("landing.resources_tab_all")}
              </span>
              <span className="px-3.5 py-1.5 rounded-full text-[12px] font-semibold bg-white/[0.02] border border-white/8 text-[#888888] hover:text-white cursor-pointer transition-all">
                {t("landing.resources_tab_compliance")}
              </span>
              <span className="px-3.5 py-1.5 rounded-full text-[12px] font-semibold bg-white/[0.02] border border-white/8 text-[#888888] hover:text-white cursor-pointer transition-all">
                {t("landing.resources_tab_threats")}
              </span>
              <span className="px-3.5 py-1.5 rounded-full text-[12px] font-semibold bg-white/[0.02] border border-white/8 text-[#888888] hover:text-white cursor-pointer transition-all">
                {t("landing.resources_tab_sme")}
              </span>
              <span className="px-3.5 py-1.5 rounded-full text-[12px] font-semibold bg-white/[0.02] border border-white/8 text-[#888888] hover:text-white cursor-pointer transition-all">
                {t("landing.resources_tab_privacy")}
              </span>
            </div>
          </div>

          {/* Cards Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
            
            {/* Left: Featured Guide */}
            <div className="lg:col-span-8 flex">
              <FadeInSection className="w-full flex" delay={0.02}>
                <div 
                  style={{
                    background: "rgba(255, 255, 255, 0.015)",
                    border: "1px solid rgba(255, 255, 255, 0.06)",
                    backdropFilter: "blur(12px)",
                    WebkitBackdropFilter: "blur(12px)",
                  }}
                  className="flex flex-col md:flex-row overflow-hidden w-full group rounded-xl hover:border-white/15 hover:bg-white/[0.03] hover:shadow-[0_0_35px_rgba(27,79,204,0.06)] transition-all duration-300"
                >
                  <div className="w-full md:w-1/2 min-h-[220px] md:min-h-full relative overflow-hidden bg-black/60 flex items-center justify-center p-6 border-b md:border-b-0 md:border-r border-white/5">
                    <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.01)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.01)_1px,transparent_1px)] bg-[size:1.5rem_1.5rem]" />
                    <div className="relative z-10 w-24 h-24 rounded-2xl bg-gradient-to-br from-[#1B4FCC]/10 to-[#10b981]/10 border border-white/10 flex items-center justify-center shadow-2xl group-hover:scale-105 transition-transform duration-300">
                      <Lock className="w-10 h-10 text-[#1B4FCC] group-hover:rotate-6 transition-transform duration-300" strokeWidth={1.5} />
                    </div>
                  </div>
                  <div className="w-full md:w-1/2 p-8 flex flex-col justify-between space-y-6">
                    <div className="space-y-3">
                      <span className="text-[10px] font-bold tracking-widest text-[#1B4FCC] uppercase bg-[#1B4FCC]/10 px-2.5 py-1 rounded">
                        {t("landing.featured_guide_label")}
                      </span>
                      <h3 className="font-display font-bold text-lg text-white tracking-tight leading-snug">
                        {t("landing.featured_guide_title")}
                      </h3>
                      <p className="text-sm text-[#888888] leading-relaxed">
                        {t("landing.featured_guide_desc")}
                      </p>
                    </div>
                    <div className="flex items-center justify-between text-xs font-semibold pt-4 border-t border-white/5">
                      <span className="text-[#1B4FCC] hover:text-[#1239A6] transition-colors flex items-center gap-1.5 cursor-pointer">
                        {t("landing.read_article")} <ArrowRight className="w-3.5 h-3.5" />
                      </span>
                      <span className="text-[#666666]">{t("landing.read_time")}</span>
                    </div>
                  </div>
                </div>
              </FadeInSection>
            </div>

            {/* Right: Security Checklist */}
            <div className="lg:col-span-4 flex">
              <FadeInSection className="w-full flex" delay={0.06}>
                <div 
                  style={{
                    background: "rgba(255, 255, 255, 0.015)",
                    border: "1px solid rgba(255, 255, 255, 0.06)",
                    backdropFilter: "blur(12px)",
                    WebkitBackdropFilter: "blur(12px)",
                  }}
                  className="p-8 flex flex-col justify-between space-y-6 w-full rounded-xl hover:border-white/15 hover:bg-white/[0.03] hover:shadow-[0_0_35px_rgba(245,158,11,0.06)] transition-all duration-300 group"
                >
                  <div className="space-y-4">
                    <div className="w-10 h-10 rounded-lg bg-[#f59e0b]/10 flex items-center justify-center border border-[#f59e0b]/20 group-hover:scale-110 group-hover:-translate-y-0.5 transition-all duration-300">
                      <FileText className="w-5 h-5 text-[#f59e0b]" />
                    </div>
                    <h3 className="font-display font-bold text-lg text-white tracking-tight leading-snug">
                      {t("landing.checklist_title")}
                    </h3>
                    <p className="text-sm text-[#888888] leading-relaxed">
                      {t("landing.checklist_desc")}
                    </p>
                  </div>
                  <div className="space-y-3">
                    <input 
                      type="email" 
                      placeholder="work@company.com" 
                      className="w-full px-4 py-2.5 bg-black/40 border border-white/8 text-sm rounded-xl text-white placeholder-[#555555] focus:outline-none focus:border-[#f59e0b]/40 transition-colors"
                    />
                    <button 
                      style={{ backgroundColor: "#f59e0b" }}
                      className="w-full py-2.5 text-black hover:bg-[#d97706] font-bold rounded-xl text-sm transition-all duration-200 cursor-pointer text-center border-0 outline-none hover:scale-[1.02] active:scale-[0.98]"
                    >
                      {t("landing.checklist_btn")}
                    </button>
                  </div>
                </div>
              </FadeInSection>
            </div>

            {/* Bottom Left: Spot Phishing */}
            <div className="lg:col-span-4 flex">
              <FadeInSection className="w-full flex" delay={0.1}>
                <div 
                  style={{
                    background: "rgba(255, 255, 255, 0.015)",
                    border: "1px solid rgba(255, 255, 255, 0.06)",
                    backdropFilter: "blur(12px)",
                    WebkitBackdropFilter: "blur(12px)",
                  }}
                  className="p-8 flex flex-col justify-between space-y-6 w-full rounded-xl hover:border-white/15 hover:bg-white/[0.03] hover:shadow-[0_0_35px_rgba(27,79,204,0.06)] transition-all duration-300 group"
                >
                  <div className="space-y-4">
                    <span className="text-[10px] font-bold tracking-widest text-[#1B4FCC] uppercase bg-[#1B4FCC]/10 px-2 py-0.5 rounded group-hover:bg-[#1B4FCC]/20 transition-colors">
                      ARTICLE
                    </span>
                    <h3 className="font-display font-bold text-[16px] text-white tracking-tight leading-snug">
                      {t("landing.phishing_guide_title")}
                    </h3>
                    <p className="text-sm text-[#888888] leading-relaxed">
                      {t("landing.phishing_guide_desc")}
                    </p>
                  </div>
                  <span className="text-[#1B4FCC] hover:text-[#1239A6] text-xs font-semibold flex items-center gap-1.5 cursor-pointer self-start group-hover:translate-x-1 transition-transform duration-300">
                    {t("landing.read_article")} <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </FadeInSection>
            </div>

            {/* Bottom Middle: Cost of Data Breach */}
            <div className="lg:col-span-4 flex">
              <FadeInSection className="w-full flex" delay={0.14}>
                <div 
                  style={{
                    background: "rgba(255, 255, 255, 0.015)",
                    border: "1px solid rgba(255, 255, 255, 0.06)",
                    backdropFilter: "blur(12px)",
                    WebkitBackdropFilter: "blur(12px)",
                  }}
                  className="p-8 flex flex-col justify-between space-y-6 w-full rounded-xl hover:border-white/15 hover:bg-white/[0.03] hover:shadow-[0_0_35px_rgba(27,79,204,0.06)] transition-all duration-300 group"
                >
                  <div className="space-y-4">
                    <span className="text-[10px] font-bold tracking-widest text-[#f59e0b] uppercase bg-[#f59e0b]/10 px-2 py-0.5 rounded group-hover:bg-[#f59e0b]/20 transition-colors">
                      RAPPORT
                    </span>
                    <h3 className="font-display font-bold text-[16px] text-white tracking-tight leading-snug">
                      {t("landing.breach_cost_title")}
                    </h3>
                    <p className="text-sm text-[#888888] leading-relaxed">
                      {t("landing.breach_cost_desc")}
                    </p>
                  </div>
                  <span className="text-[#1B4FCC] hover:text-[#1239A6] text-xs font-semibold flex items-center gap-1.5 cursor-pointer self-start group-hover:translate-x-1 transition-transform duration-300">
                    {t("landing.read_article")} <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </FadeInSection>
            </div>

            {/* Bottom Right: Live Threat Metrics Widget */}
            <div className="lg:col-span-4 flex">
              <FadeInSection className="w-full flex" delay={0.18}>
                <div 
                  style={{
                    background: "rgba(255, 255, 255, 0.015)",
                    border: "1px solid rgba(255, 255, 255, 0.06)",
                    backdropFilter: "blur(12px)",
                    WebkitBackdropFilter: "blur(12px)",
                  }}
                  className="p-8 flex flex-col justify-between space-y-5 w-full rounded-xl hover:border-white/15 hover:bg-white/[0.03] hover:shadow-[0_0_35px_rgba(16,185,129,0.06)] transition-all duration-300 group relative overflow-hidden"
                >
                  <div className="absolute top-4 right-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                    <span className="w-2 h-2 rounded-full bg-emerald-500 absolute" />
                    <span className="text-[9px] font-bold tracking-wider text-emerald-500 uppercase">{t("landing.live_threat_label")}</span>
                  </div>

                  <div className="space-y-4">
                    <div className="w-10 h-10 rounded-lg bg-[#10b981]/10 flex items-center justify-center border border-[#10b981]/20 group-hover:scale-110 group-hover:-translate-y-0.5 transition-all duration-300">
                      <TrendingUp className="w-5 h-5 text-[#10b981]" />
                    </div>
                    <h3 className="font-display font-bold text-lg text-white tracking-tight leading-snug">
                      Sicurre Live
                    </h3>
                  </div>

                  <div className="space-y-3 pt-2">
                    <div className="flex items-center justify-between py-1.5 border-b border-white/5">
                      <span className="text-xs text-[#888888]">{t("landing.live_scans_label")}</span>
                      <span className="text-sm font-bold text-white font-mono">1.2M+</span>
                    </div>
                    <div className="flex items-center justify-between py-1.5 border-b border-white/5">
                      <span className="text-xs text-[#888888]">{t("landing.live_blocked_label")}</span>
                      <span className="text-sm font-bold text-[#f59e0b] font-mono">14,802</span>
                    </div>
                    <div className="flex items-center justify-between py-1.5">
                      <span className="text-xs text-[#888888]">{t("landing.live_response_label")}</span>
                      <span className="text-sm font-bold text-emerald-500 font-mono">0.04s</span>
                    </div>
                  </div>
                </div>
              </FadeInSection>
            </div>

          </div>

        </div>
      </section>

      {/* SECTION 5: STAY AHEAD OF THE THREATS (SUBSCRIBE) */}
      <section style={{ backgroundColor: "#000000" }} className="py-20 relative z-10 overflow-hidden border-t border-white/5">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(27,79,204,0.03),transparent_60%)] pointer-events-none" />
        <div className="max-w-4xl mx-auto px-6 lg:px-8 text-center space-y-8 relative z-10">
          
          <FadeInSection className="space-y-4">
            <h2 className="font-display font-bold text-[clamp(1.75rem,3.5vw,2.25rem)] leading-tight tracking-tight text-white">
              {t("landing.subscribe_title")}
            </h2>
            <p className="text-[15px] leading-relaxed max-w-2xl mx-auto font-medium" style={{ color: "#888888" }}>
              {t("landing.subscribe_desc")}
            </p>
          </FadeInSection>

          <FadeInSection delay={0.05}>
            <form onSubmit={(e) => e.preventDefault()} className="flex flex-col sm:flex-row items-center justify-center gap-3 max-w-lg mx-auto">
              <input 
                type="email" 
                placeholder={t("landing.subscribe_placeholder")}
                required
                className="w-full px-4 py-3 bg-[#0a0a0a]/60 border border-white/10 rounded-xl text-sm text-white placeholder-[#555555] focus:outline-none focus:border-primary/50 transition-colors"
              />
              <button 
                type="submit"
                className="w-full sm:w-auto px-6 py-3 bg-primary hover:bg-navy-dark text-on-primary font-bold rounded-xl text-sm transition-all duration-200 cursor-pointer text-center border-0 outline-none hover:scale-105 active:scale-95"
              >
                {t("landing.subscribe_btn")}
              </button>
            </form>
          </FadeInSection>

        </div>
      </section>

      <footer className="bg-[#05080e] text-white/40 border-t border-white/5 py-8 relative z-10">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-8 h-8" />
            <span className="font-display font-bold text-white text-[16px]">Sicurre</span>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-[12px] font-medium">
            <button
              onClick={onNavigateToMentionsLegales}
              className="hover:text-white transition-colors cursor-pointer border-none bg-transparent p-0 text-inherit font-medium outline-none text-[12px]"
            >
              Mentions légales
            </button>
            <button
              onClick={onNavigateToConfidentialite}
              className="hover:text-white transition-colors cursor-pointer border-none bg-transparent p-0 text-inherit font-medium outline-none text-[12px]"
            >
              Confidentialité
            </button>
            <button
              onClick={onNavigateToContact}
              className="hover:text-white transition-colors cursor-pointer border-none bg-transparent p-0 text-inherit font-medium outline-none text-[12px]"
            >
              Contact
            </button>
          </div>
          <div className="text-[11px] text-white/30">
            {t("landing.footer_copyright")}
          </div>
        </div>
      </footer>
    </div>
  );
}
