import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Shield,
  ArrowRight,
  ShieldCheck,
  Lock,
  Mail,
  Server,
  ChevronDown,
  Globe,
  Cpu,
  CheckCircle2,
  Zap,
  Key,
  Search as SearchIcon,
  FileCheck,
  Terminal,
} from "lucide-react";
import { motion } from "framer-motion";
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

/* ── Integration Terminal Mock ─────────────────────────────────────────────── */
function IntegrationTerminal() {
  const [activeStep, setActiveStep] = useState(0);
  const { t } = useTranslation();

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveStep((prev) => (prev >= 3 ? 0 : prev + 1));
    }, 2800);
    return () => clearInterval(timer);
  }, []);

  const steps = [
    { icon: Key, color: "#f59e0b", title: t("landing.integration_step_1_title"), desc: t("landing.integration_step_1_desc") },
    { icon: SearchIcon, color: "#3b82f6", title: t("landing.integration_step_2_title"), desc: t("landing.integration_step_2_desc") },
    { icon: FileCheck, color: "#8b5cf6", title: t("landing.integration_step_3_title"), desc: t("landing.integration_step_3_desc") },
    { icon: CheckCircle2, color: "#10b981", title: t("landing.integration_step_4_title"), desc: t("landing.integration_step_4_desc") },
  ];

  return (
    <div
      style={{
        background: "linear-gradient(145deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.005) 100%)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: "16px",
        overflow: "hidden",
      }}
      className="w-full max-w-[520px]"
    >
      {/* Terminal Header */}
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-white/5">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
        </div>
        <div className="flex-1 text-center">
          <span className="text-[11px] text-white/30 font-mono">sicurre — integration</span>
        </div>
      </div>

      {/* Terminal Body */}
      <div className="p-5 space-y-3 font-mono text-[13px]">
        {steps.map((step, idx) => {
          const Icon = step.icon;
          const isActive = idx <= activeStep;
          const isCurrent = idx === activeStep;
          return (
            <MotionDiv
              key={idx}
              initial={{ opacity: 0.3 }}
              animate={{ opacity: isActive ? 1 : 0.3 }}
              transition={{ duration: 0.4 }}
              className={`flex items-start gap-3 py-2.5 px-3 rounded-lg transition-all duration-300 ${
                isCurrent ? "bg-white/[0.04]" : ""
              }`}
            >
              <div
                className="mt-0.5 flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center transition-all duration-300"
                style={{
                  backgroundColor: isActive ? `${step.color}15` : "rgba(255,255,255,0.03)",
                  border: `1px solid ${isActive ? `${step.color}30` : "rgba(255,255,255,0.05)"}`,
                }}
              >
                {isActive && idx < activeStep ? (
                  <CheckCircle2 className="w-3.5 h-3.5" style={{ color: step.color }} />
                ) : (
                  <Icon className="w-3.5 h-3.5" style={{ color: isActive ? step.color : "#555" }} />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className="text-[12px] font-semibold leading-tight transition-colors"
                  style={{ color: isActive ? "#e2e8f0" : "#555", fontFamily: "Inter, system-ui, sans-serif" }}
                >
                  {step.title}
                </div>
                {isCurrent && (
                  <MotionDiv
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    transition={{ duration: 0.3 }}
                  >
                    <p className="text-[11px] text-white/40 mt-1 leading-relaxed" style={{ fontFamily: "Inter, system-ui, sans-serif" }}>
                      {step.desc}
                    </p>
                  </MotionDiv>
                )}
              </div>
              {isCurrent && (
                <div className="mt-1 w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: step.color }} />
              )}
            </MotionDiv>
          );
        })}
      </div>
    </div>
  );
}

/* ── Trust Logo Placeholders ───────────────────────────────────────────────── */
function TrustLogo({ name }: { name: string }) {
  return (
    <div className="flex h-12 items-center justify-center opacity-30 hover:opacity-50 transition-opacity duration-300">
      <div className="text-[14px] font-bold tracking-[0.15em] uppercase text-white/60 select-none">
        {name}
      </div>
    </div>
  );
}

/* ── Main Landing Component ────────────────────────────────────────────────── */
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

  const marqueeItems = [
    { icon: Shield, label: t("landing.marquee_zero_trust") },
    { icon: ShieldCheck, label: t("landing.marquee_ai") },
    { icon: Lock, label: t("landing.marquee_gmail") },
    { icon: Mail, label: t("landing.marquee_sovereign") },
    { icon: ShieldCheck, label: t("landing.marquee_rgpd") },
    { icon: Server, label: t("landing.marquee_realtime") },
  ];

  const featuresConfig = [
    {
      icon: Cpu,
      lineColor: "#3b82f6",
      stat: t("landing.feat_ai_stat"),
      label: t("landing.feat_ai_label"),
      title: t("landing.feat_ai_title"),
      desc: t("landing.feat_ai_desc"),
      iconBg: "rgba(59, 130, 246, 0.12)",
      iconColor: "#3b82f6",
      labelColor: "#3b82f6",
    },
    {
      icon: Zap,
      lineColor: "#10b981",
      stat: t("landing.feat_remediation_stat"),
      label: t("landing.feat_remediation_label"),
      title: t("landing.feat_remediation_title"),
      desc: t("landing.feat_remediation_desc"),
      iconBg: "rgba(16, 185, 129, 0.12)",
      iconColor: "#10b981",
      labelColor: "#10b981",
    },
    {
      icon: Globe,
      lineColor: "#f59e0b",
      stat: t("landing.feat_dns_stat"),
      label: t("landing.feat_dns_label"),
      title: t("landing.feat_dns_title"),
      desc: t("landing.feat_dns_desc"),
      iconBg: "rgba(245, 158, 11, 0.12)",
      iconColor: "#f59e0b",
      labelColor: "#f59e0b",
    },
  ];

  return (
    <div className="min-h-screen font-sans select-none relative overflow-x-hidden bg-black text-white">
      
      {/* ═══════════════════════════════════════════════════════════════════════
          HEADER — Sticky glassmorphism nav (Resend-style)
          ═══════════════════════════════════════════════════════════════════════ */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-black/70 backdrop-blur-xl border-b border-white/5 py-3"
            : "bg-transparent py-5"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-10 h-10" />
            <span className="font-display font-bold text-xl tracking-tight text-white">
              Sicurre
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-[13px] font-medium text-white/50">
            <a href="#features" className="hover:text-white transition-colors duration-200">{t("landing.nav_features")}</a>
            <a href="#integration" className="hover:text-white transition-colors duration-200">Integration</a>
          </nav>

          <div className="flex items-center gap-4">
            <LanguageSwitcher scrolled={false} />
            <button
              onClick={onNavigateToLogin}
              className="text-[13px] font-medium text-white/50 hover:text-white transition-colors cursor-pointer hidden sm:block"
            >
              {t("landing.nav_login")}
            </button>
            <button
              onClick={onNavigateToSignUp}
              className="px-4.5 py-2 rounded-xl text-[13px] font-semibold transition-all active:scale-[0.97] cursor-pointer text-white border border-white/10 bg-white/[0.06] hover:bg-white/[0.12] backdrop-blur-sm"
            >
              {t("landing.nav_cta")}
            </button>
          </div>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════════════════════════════
          HERO — Resend-style large serif heading + animation
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="relative w-full min-h-screen flex flex-col justify-between overflow-hidden">
        {/* ── Layer 1: Floor surface with subtle reflections (Resend bg-hero-1 equivalent) ── */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `
              linear-gradient(180deg, 
                rgba(0,0,0,0) 0%, 
                rgba(0,0,0,0) 55%, 
                rgba(15,18,30,0.6) 70%, 
                rgba(20,24,40,0.8) 85%, 
                rgba(10,12,20,0.95) 100%
              )
            `,
          }}
        />
        
        {/* ── Layer 2: Light ray cone from top center (Resend bg-light equivalent) ── */}
        <div
          className="absolute pointer-events-none"
          style={{
            top: "-15%",
            left: "50%",
            transform: "translateX(-50%)",
            width: "140%",
            height: "110%",
            background: `
              conic-gradient(
                from 180deg at 50% 0%,
                transparent 35%,
                rgba(200,210,230,0.04) 42%,
                rgba(180,195,225,0.07) 47%,
                rgba(200,210,240,0.09) 50%,
                rgba(180,195,225,0.07) 53%,
                rgba(200,210,230,0.04) 58%,
                transparent 65%
              )
            `,
            maskImage: "linear-gradient(to bottom, black 0%, black 60%, transparent 100%)",
            WebkitMaskImage: "linear-gradient(to bottom, black 0%, black 60%, transparent 100%)",
          }}
        />

        {/* ── Layer 3: Radial spotlight glow (soft center wash) ── */}
        <div
          className="absolute pointer-events-none"
          style={{
            top: "-30%",
            left: "50%",
            transform: "translateX(-50%)",
            width: "100%",
            height: "90%",
            background: "radial-gradient(ellipse 60% 50% at 50% 0%, rgba(160,175,210,0.08) 0%, rgba(100,120,180,0.03) 40%, transparent 70%)",
          }}
        />

        {/* ── Layer 4: Floor reflection streaks ── */}
        <div
          className="absolute bottom-0 left-0 right-0 h-[35%] pointer-events-none"
          style={{
            background: `
              linear-gradient(165deg, transparent 30%, rgba(255,255,255,0.015) 45%, transparent 55%),
              linear-gradient(195deg, transparent 35%, rgba(255,255,255,0.01) 50%, transparent 60%),
              linear-gradient(180deg, transparent 0%, rgba(15,20,35,0.5) 30%, rgba(20,25,45,0.7) 100%)
            `,
          }}
        />

        {/* ── Layer 5: Side vignette (dark blue tint at edges like Resend) ── */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `
              linear-gradient(90deg, rgba(5,8,20,0.7) 0%, transparent 25%, transparent 75%, rgba(5,8,20,0.7) 100%)
            `,
          }}
        />

        {/* ── Layer 6: Very subtle grid texture ── */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.008)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.008)_1px,transparent_1px)] bg-[size:5rem_5rem] pointer-events-none" />

        {/* Hero content */}
        <div className="flex-1 w-full max-w-7xl mx-auto px-6 lg:px-12 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-16 items-center relative z-10 pt-32 pb-8">
          <div className="lg:col-span-6 space-y-6 flex flex-col justify-center">
            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
            >
              <h1 className="font-display font-extrabold text-[clamp(2.5rem,5.5vw,4.5rem)] leading-[1.05] tracking-[-0.02em] text-white">
                {t("landing.hero_title_line1")}
                <br />
                <span className="text-white/40">{t("landing.hero_title_line2")}</span>
              </h1>
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="text-[16px] sm:text-[18px] text-white/50 leading-[1.6] max-w-[30rem] font-normal"
            >
              {t("landing.hero_desc")}
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="flex flex-col sm:flex-row items-start gap-4 pt-1"
            >
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-6 py-3 rounded-xl text-[15px] font-semibold transition-all active:scale-[0.97] cursor-pointer text-white border border-white/10 bg-white/[0.06] hover:bg-white/90 hover:text-black hover:shadow-[0_0_20px_rgba(255,255,255,0.15)] duration-200"
              >
                <span>{t("landing.hero_cta_primary")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
              <a
                href="#features"
                className="flex items-center gap-2 px-6 py-3 text-[15px] font-medium text-white/50 hover:text-white transition-colors cursor-pointer"
              >
                {t("landing.hero_cta_secondary")}
              </a>
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.45 }}
              className="text-[13px] text-white/25 font-medium pt-2"
            >
              {t("landing.hero_social_proof")}
            </MotionDiv>
          </div>

          <div className="lg:col-span-6 flex justify-center lg:justify-end h-full max-h-[420px]">
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

        {/* Marquee loop at bottom of hero */}
        <div className="w-full bg-white/[0.02] border-t border-white/5 py-5 relative z-20 backdrop-blur-sm">
          <div className="relative flex max-w-full overflow-hidden">
            <div className="animate-marquee flex gap-12 whitespace-nowrap text-white text-[11px] font-bold tracking-[0.2em] uppercase shrink-0">
              {[...marqueeItems, ...marqueeItems].map((item, idx) => {
                const Icon = item.icon;
                return (
                  <span key={idx} className="flex items-center gap-2.5 text-white/40">
                    <Icon className="w-4 h-4 text-white/20" />
                    {item.label}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          TRUST BAR — Company logos
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="py-16 relative border-t border-white/5">
        <div className="max-w-5xl mx-auto px-6 lg:px-8 flex flex-col items-center">
          <p className="text-[15px] text-white/30 font-normal mb-10 text-center">
            {t("landing.trust_subtitle")}
          </p>
          <div className="w-full grid grid-cols-3 sm:grid-cols-6 gap-6 items-center">
            <TrustLogo name="Mediaflow" />
            <TrustLogo name="Nextera" />
            <TrustLogo name="LogiPro" />
            <TrustLogo name="Axantis" />
            <TrustLogo name="Primelis" />
            <TrustLogo name="Vecteur" />
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          FEATURES — 3-column grid
          ═══════════════════════════════════════════════════════════════════════ */}
      <section id="features" className="py-24 lg:py-32 relative border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 space-y-16 relative z-10">
          
          <FadeInSection className="text-center max-w-2xl mx-auto space-y-4">
            <span
              className="px-3.5 py-1.5 rounded-full w-fit inline-block text-[11px] font-bold tracking-widest uppercase"
              style={{ color: "#3b82f6", backgroundColor: "rgba(59, 130, 246, 0.08)" }}
            >
              {t("landing.features_label")}
            </span>
            <h2 className="font-display font-bold text-[clamp(1.75rem,3.5vw,2.75rem)] leading-[1.1] tracking-[-0.02em] text-white mt-3">
              {t("landing.features_title")}
            </h2>
            <p className="text-[15px] leading-relaxed max-w-xl mx-auto font-normal text-white/40">
              {t("landing.features_desc")}
            </p>
          </FadeInSection>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {featuresConfig.map((feat, idx) => {
              const IconComponent = feat.icon;
              return (
                <FadeInSection key={idx} delay={idx * 0.06}>
                  <div 
                    style={{
                      background: "rgba(255, 255, 255, 0.015)",
                      border: "1px solid rgba(255, 255, 255, 0.06)",
                    }}
                    className="relative overflow-hidden text-left flex flex-col justify-between h-full group rounded-2xl hover:border-white/12 hover:bg-white/[0.03] transition-all duration-300"
                  >
                    <div style={{ height: "2px", width: "100%", backgroundColor: feat.lineColor }} />
                    
                    <div className="p-8 space-y-5 flex-1 flex flex-col justify-between">
                      <div className="space-y-5">
                        <div 
                          className="group-hover:scale-110 group-hover:-translate-y-1 transition-all duration-300"
                          style={{
                            width: "40px",
                            height: "40px",
                            borderRadius: "10px",
                            padding: "8px",
                            backgroundColor: feat.iconBg,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <IconComponent style={{ width: "22px", height: "22px", color: feat.iconColor }} strokeWidth={1.5} />
                        </div>

                        <div style={{ fontSize: "24px", fontWeight: 600, color: "#ffffff", letterSpacing: "-0.02em" }}>
                          {feat.stat}
                        </div>

                        <div 
                          style={{
                            color: feat.labelColor,
                            fontSize: "11px",
                            textTransform: "uppercase",
                            letterSpacing: "0.1em",
                            fontWeight: 600,
                          }}
                        >
                          {feat.label}
                        </div>

                        <h3 className="font-display font-bold text-[15px] text-white/80 tracking-tight leading-snug">
                          {feat.title}
                        </h3>

                        <p className="text-[14px] leading-relaxed text-white/35">
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

      {/* ═══════════════════════════════════════════════════════════════════════
          INTEGRATION — 1-Click DNS auto-config showcase
          ═══════════════════════════════════════════════════════════════════════ */}
      <section id="integration" className="py-24 lg:py-32 relative border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 items-center">
            
            {/* Left: Copy */}
            <FadeInSection className="space-y-6">
              <span
                className="px-3.5 py-1.5 rounded-full w-fit inline-block text-[11px] font-bold tracking-widest uppercase"
                style={{ color: "#10b981", backgroundColor: "rgba(16, 185, 129, 0.08)" }}
              >
                {t("landing.integration_label")}
              </span>
              
              <h2 className="font-display font-bold text-[clamp(1.75rem,3.5vw,2.75rem)] leading-[1.1] tracking-[-0.02em] text-white">
                {t("landing.integration_title")}
              </h2>
              
              <p className="text-[16px] leading-relaxed text-white/40 font-normal max-w-lg">
                {t("landing.integration_desc")}
              </p>

              <div className="flex flex-col sm:flex-row items-start gap-4 pt-2">
                <button
                  onClick={onNavigateToSignUp}
                  className="flex items-center gap-2 px-6 py-3 rounded-xl text-[14px] font-semibold transition-all active:scale-[0.97] cursor-pointer text-white border border-white/10 bg-white/[0.06] hover:bg-white/90 hover:text-black hover:shadow-[0_0_20px_rgba(255,255,255,0.15)] duration-200"
                >
                  <Terminal className="w-4 h-4" />
                  <span>{t("landing.integration_cta")}</span>
                </button>
              </div>

              <p className="text-[12px] text-white/20 font-medium pt-1">
                {t("landing.integration_note")}
              </p>
            </FadeInSection>

            {/* Right: Terminal Mock */}
            <FadeInSection delay={0.1} className="flex justify-center lg:justify-end">
              <IntegrationTerminal />
            </FadeInSection>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          STATS + TESTIMONIAL + CTA
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="py-24 lg:py-32 relative border-t border-white/5">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.03),transparent_60%)] pointer-events-none" />
        <div className="max-w-3xl mx-auto px-6 lg:px-8 text-center space-y-10 relative z-10">
          
          {/* Stats Row */}
          <FadeInSection>
            <div className="flex flex-row items-center justify-center gap-12 sm:gap-20 py-2">
              <div className="text-center">
                <div className="text-[32px] font-semibold text-white tracking-tight">{t("landing.stats_smes")}</div>
                <div className="text-[12px] text-white/30 mt-1">{t("landing.stats_smes_label")}</div>
              </div>
              <div className="text-center">
                <div className="text-[32px] font-semibold text-white tracking-tight">{t("landing.stats_emails")}</div>
                <div className="text-[12px] text-white/30 mt-1">{t("landing.stats_emails_label")}</div>
              </div>
              <div className="text-center">
                <div className="text-[32px] font-semibold text-white tracking-tight">{t("landing.stats_breaches")}</div>
                <div className="text-[12px] text-white/30 mt-1">{t("landing.stats_breaches_label")}</div>
              </div>
            </div>
          </FadeInSection>

          <div style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", width: "100%" }} />

          {/* Testimonial */}
          <FadeInSection delay={0.04}>
            <div 
              style={{
                maxWidth: "520px",
                background: "rgba(255, 255, 255, 0.015)",
                border: "1px solid rgba(255, 255, 255, 0.06)",
                padding: "24px",
                margin: "0 auto",
                borderRadius: "16px",
              }}
              className="text-left hover:border-white/10 transition-all duration-300"
            >
              <p className="text-[14px] text-white/60 leading-[1.7] mb-4 italic">
                "{t("landing.testimonial_text")}"
              </p>
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div 
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "50%",
                      backgroundColor: "rgba(59, 130, 246, 0.15)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "#3b82f6",
                      fontSize: "11px",
                      fontWeight: "bold",
                    }}
                  >
                    TM
                  </div>
                  <div>
                    <div className="text-[13px] font-semibold text-white/80">{t("landing.testimonial_author")}</div>
                    <div className="text-[12px] text-white/30">{t("landing.testimonial_role")}</div>
                  </div>
                </div>
                <div className="text-[14px] text-amber-400 tracking-wider">
                  ★★★★★
                </div>
              </div>
            </div>
          </FadeInSection>

          {/* CTA */}
          <FadeInSection className="space-y-4" delay={0.08}>
            <h2 className="font-display font-bold text-[clamp(1.5rem,4vw,2.5rem)] leading-[1.1] tracking-[-0.02em] text-white mt-4">
              {t("landing.cta_section_title")}
            </h2>
            <p className="text-[15px] leading-relaxed max-w-xl mx-auto font-normal text-white/40">
              {t("landing.cta_section_desc")}
            </p>
          </FadeInSection>

          <FadeInSection delay={0.12}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 pt-2">
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-7 py-3.5 rounded-xl text-[15px] font-semibold transition-all active:scale-[0.97] cursor-pointer text-white border border-white/10 bg-white/[0.06] hover:bg-white/90 hover:text-black hover:shadow-[0_0_20px_rgba(255,255,255,0.15)] duration-200"
              >
                <span>{t("landing.cta_section_trial")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
            <div className="text-[13px] text-white/20 mt-3 font-medium">
              {t("landing.cta_no_card")}
            </div>
          </FadeInSection>

          <FadeInSection delay={0.16} className="pt-4 flex flex-wrap justify-center gap-x-8 gap-y-3 text-[13px] font-medium">
            <div className="flex items-center gap-2 text-white/30">
              <ShieldCheck className="w-4 h-4 text-emerald-500/60" />
              <span>{t("landing.cta_badge_rgpd")}</span>
            </div>
            <div className="flex items-center gap-2 text-white/30">
              <ShieldCheck className="w-4 h-4 text-emerald-500/60" />
              <span>{t("landing.cta_badge_sovereign")}</span>
            </div>
            <div className="flex items-center gap-2 text-white/30">
              <ShieldCheck className="w-4 h-4 text-emerald-500/60" />
              <span>{t("landing.cta_badge_instant")}</span>
            </div>
          </FadeInSection>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          FOOTER — Minimal dark
          ═══════════════════════════════════════════════════════════════════════ */}
      <footer className="border-t border-white/5 py-8 relative z-10">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-7 h-7" />
            <span className="font-display font-bold text-white text-[15px]">Sicurre</span>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-[12px] font-medium text-white/25">
            <button
              onClick={onNavigateToMentionsLegales}
              className="hover:text-white/60 transition-colors cursor-pointer border-none bg-transparent p-0 text-inherit font-medium outline-none text-[12px]"
            >
              {t("landing.footer_mentions")}
            </button>
            <button
              onClick={onNavigateToConfidentialite}
              className="hover:text-white/60 transition-colors cursor-pointer border-none bg-transparent p-0 text-inherit font-medium outline-none text-[12px]"
            >
              {t("landing.footer_privacy")}
            </button>
            <button
              onClick={onNavigateToContact}
              className="hover:text-white/60 transition-colors cursor-pointer border-none bg-transparent p-0 text-inherit font-medium outline-none text-[12px]"
            >
              {t("landing.footer_contact")}
            </button>
          </div>
          <div className="text-[11px] text-white/15">
            {t("landing.footer_copyright")}
          </div>
        </div>
      </footer>
    </div>
  );
}
