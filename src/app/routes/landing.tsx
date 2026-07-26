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
    document.documentElement.lang = lang;
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-white/15 bg-white/[0.06] hover:bg-white/[0.12] text-white/90 text-[13px] font-medium transition-all cursor-pointer select-none shadow-sm"
      >
        <span>{currentLang === "fr" ? "🇫🇷" : "🇬🇧"}</span>
        <ChevronDown className="w-3.5 h-3.5 opacity-60" />
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-36 rounded-xl border border-white/15 bg-[#101424]/95 backdrop-blur-2xl text-white shadow-2xl shadow-black/80 py-1 text-[13px] font-medium text-left z-50 overflow-hidden">
          <button
            onClick={() => changeLanguage("fr")}
            className={`w-full px-3.5 py-2.5 transition-all flex items-center gap-2.5 cursor-pointer border-0 outline-none hover:bg-primary/20 hover:text-white ${
              currentLang === "fr" ? "text-primary font-bold bg-primary/10" : "text-white/80"
            }`}
          >
            <span>🇫🇷</span>
            <span>Français</span>
          </button>
          <button
            onClick={() => changeLanguage("en")}
            className={`w-full px-3.5 py-2.5 transition-all flex items-center gap-2.5 cursor-pointer border-0 outline-none hover:bg-primary/20 hover:text-white ${
              currentLang === "en" ? "text-primary font-bold bg-primary/10" : "text-white/80"
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

/* ── Integration Glassy Step Card Showcase (Resend Style) ───────────────── */
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
    { icon: SearchIcon, color: "#4a90d9", title: t("landing.integration_step_2_title"), desc: t("landing.integration_step_2_desc") },
    { icon: FileCheck, color: "#8b5cf6", title: t("landing.integration_step_3_title"), desc: t("landing.integration_step_3_desc") },
    { icon: CheckCircle2, color: "#10b981", title: t("landing.integration_step_4_title"), desc: t("landing.integration_step_4_desc") },
  ];

  return (
    <div
      style={{
        background: "rgba(255, 255, 255, 0.025)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        border: "1px solid rgba(255, 255, 255, 0.1)",
        boxShadow: "0 25px 60px rgba(0, 0, 0, 0.65)",
      }}
      className="w-full max-w-[560px] min-h-[440px] rounded-2xl p-6 lg:p-8 flex flex-col justify-center select-none"
    >
      <div className="space-y-3.5">
        {steps.map((step, idx) => {
          const Icon = step.icon;
          const isActive = idx <= activeStep;
          const isCurrent = idx === activeStep;
          return (
            <MotionDiv
              key={idx}
              initial={{ opacity: 0.3 }}
              animate={{ opacity: isActive ? 1 : 0.35 }}
              transition={{ duration: 0.4 }}
              className={`flex items-start gap-4 py-3.5 px-4 rounded-xl transition-all duration-300 border ${
                isCurrent
                  ? "bg-white/[0.04] border-white/15 shadow-md shadow-black/30"
                  : "border-transparent"
              }`}
            >
              <div
                className="mt-0.5 flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-300"
                style={{
                  backgroundColor: isActive ? `${step.color}18` : "rgba(255,255,255,0.03)",
                  border: `1px solid ${isActive ? `${step.color}35` : "rgba(255,255,255,0.05)"}`,
                }}
              >
                {isActive && idx < activeStep ? (
                  <CheckCircle2 className="w-4.5 h-4.5" style={{ color: step.color }} />
                ) : (
                  <Icon className="w-4.5 h-4.5" style={{ color: isActive ? step.color : "#666" }} />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className="text-[15px] sm:text-[16px] font-semibold leading-snug transition-colors"
                  style={{ color: isActive ? "#f8fafc" : "#64748b" }}
                >
                  {step.title}
                </div>
                <p
                  className={`text-[13px] sm:text-[14px] leading-relaxed transition-all duration-300 ${
                    isCurrent ? "text-slate-400 mt-1 max-h-16 opacity-100" : "text-slate-500/40 mt-0.5 max-h-0 opacity-0 overflow-hidden"
                  }`}
                >
                  {step.desc}
                </p>
              </div>
              {isCurrent && (
                <div className="mt-2 w-2.5 h-2.5 rounded-full animate-pulse shrink-0" style={{ backgroundColor: step.color }} />
              )}
            </MotionDiv>
          );
        })}
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
      icon: ShieldCheck,
      stat: t("landing.feat_ai_stat"),
      label: t("landing.feat_ai_label"),
      title: t("landing.feat_ai_title"),
      desc: t("landing.feat_ai_desc"),
      preview: (
        <div className="mt-5 p-3.5 rounded-xl bg-white/[0.03] border border-white/10 text-[13px] space-y-2 text-white/80 font-sans">
          <div className="flex items-center justify-between text-white font-medium">
            <span className="flex items-center gap-1.5 text-white/90">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
              {t("landing.preview_verdict")}
            </span>
            <span className="px-2.5 py-0.5 rounded-md bg-rose-500/20 text-rose-300 font-semibold border border-rose-500/30 text-[12px]">
              {t("landing.preview_score")}
            </span>
          </div>
          <div className="text-[12px] text-slate-400">{t("landing.preview_action")}</div>
        </div>
      ),
    },
    {
      icon: Lock,
      stat: t("landing.feat_remediation_stat"),
      label: t("landing.feat_remediation_label"),
      title: t("landing.feat_remediation_title"),
      desc: t("landing.feat_remediation_desc"),
      preview: (
        <div className="mt-5 p-3.5 rounded-xl bg-white/[0.03] border border-white/10 text-[13px] flex items-center justify-between text-white/80 font-sans">
          <span className="text-slate-300 font-normal">{t("landing.preview_retention")}</span>
          <span className="px-2.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 font-semibold border border-emerald-500/30 text-[12px]">
            {t("landing.preview_active")}
          </span>
        </div>
      ),
    },
    {
      icon: Terminal,
      stat: t("landing.feat_dns_stat"),
      label: t("landing.feat_dns_label"),
      title: t("landing.feat_dns_title"),
      desc: t("landing.feat_dns_desc"),
      preview: (
        <div className="mt-5 p-3.5 rounded-xl bg-white/[0.03] border border-white/10 text-[13px] flex items-center justify-between text-white/80 font-sans">
          <span className="text-emerald-400 font-semibold">SPF ✓</span>
          <span className="text-emerald-400 font-semibold">DKIM ✓</span>
          <span className="text-emerald-400 font-semibold">DMARC ✓</span>
        </div>
      ),
    },
  ];

  return (
    <div className="min-h-screen font-sans select-none relative overflow-x-hidden bg-black text-white">
      
      {/* ═══════════════════════════════════════════════════════════════════════
          HEADER — Sticky glassmorphism nav (No height jump on scroll)
          ═══════════════════════════════════════════════════════════════════════ */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 py-3.5 transition-all duration-300 ${
          scrolled
            ? "bg-black/80 backdrop-blur-xl border-b border-white/10 shadow-lg shadow-black/40"
            : "bg-transparent border-b border-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-9 h-9" />
            <span className="font-display font-bold text-xl tracking-tight text-white">
              Sicurre
            </span>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <LanguageSwitcher scrolled={scrolled} />
            <button
              onClick={onNavigateToLogin}
              className="text-[13px] font-medium text-white/60 hover:text-primary transition-colors cursor-pointer hidden sm:block"
            >
              {t("landing.nav_login")}
            </button>
            <button
              onClick={onNavigateToSignUp}
              className="px-3 py-2 sm:px-4.5 rounded-lg text-[12px] sm:text-[13px] font-semibold transition-all active:scale-[0.97] cursor-pointer text-white border border-white/15 bg-white/[0.06] hover:bg-primary hover:text-white hover:border-primary shadow-sm"
            >
              {t("landing.nav_cta")}
            </button>
          </div>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════════════════════════════
          HERO — Full viewport heading, trust badges & bottom marquee banner
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="relative w-full min-h-screen flex flex-col justify-between overflow-hidden pt-24 pb-0">
        <div className="absolute inset-0 pointer-events-none" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0) 55%, rgba(15,18,30,0.6) 70%, rgba(20,24,40,0.8) 85%, rgba(10,12,20,0.95) 100%)" }} />
        <div className="absolute pointer-events-none" style={{ top: "-15%", left: "50%", transform: "translateX(-50%)", width: "140%", height: "110%", background: "conic-gradient(from 180deg at 50% 0%, transparent 35%, rgba(200,210,230,0.04) 42%, rgba(180,195,225,0.07) 47%, rgba(200,210,240,0.09) 50%, rgba(180,195,225,0.07) 53%, rgba(200,210,230,0.04) 58%, transparent 65%)", maskImage: "linear-gradient(to bottom, black 0%, black 60%, transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom, black 0%, black 60%, transparent 100%)" }} />
        <div className="absolute pointer-events-none" style={{ top: "-30%", left: "50%", transform: "translateX(-50%)", width: "100%", height: "90%", background: "radial-gradient(ellipse 60% 50% at 50% 0%, rgba(160,175,210,0.08) 0%, rgba(100,120,180,0.03) 40%, transparent 70%)" }} />
        <div className="absolute bottom-0 left-0 right-0 h-[35%] pointer-events-none" style={{ background: "linear-gradient(165deg, transparent 30%, rgba(255,255,255,0.015) 45%, transparent 55%), linear-gradient(195deg, transparent 35%, rgba(255,255,255,0.01) 50%, transparent 60%), linear-gradient(180deg, transparent 0%, rgba(15,20,35,0.5) 30%, rgba(20,25,45,0.7) 100%)" }} />
        <div className="absolute inset-0 pointer-events-none" style={{ background: "linear-gradient(90deg, rgba(5,8,20,0.7) 0%, transparent 25%, transparent 75%, rgba(5,8,20,0.7) 100%)" }} />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.008)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.008)_1px,transparent_1px)] bg-[size:5rem_5rem] pointer-events-none" />

        <div className="flex-1 w-full max-w-7xl mx-auto px-6 lg:px-12 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-16 items-center relative z-10 py-12">
          <div className="lg:col-span-6 space-y-7 flex flex-col justify-center">
            <MotionDiv initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}>
              <h1 className="font-display font-extrabold text-[clamp(2.5rem,5.2vw,4.25rem)] leading-[1.08] tracking-[-0.03em] text-white">
                <span className="block">{t("landing.hero_title_line1")}</span>
                {t("landing.hero_title_line2") && <span className="block text-white/50 font-semibold mt-1">{t("landing.hero_title_line2")}</span>}
              </h1>
            </MotionDiv>
            <MotionDiv initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }} className="text-[17px] sm:text-[19px] text-slate-400 leading-[1.65] max-w-[34rem] font-normal">
              {t("landing.hero_desc")}
            </MotionDiv>
            <MotionDiv initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.3 }} className="flex items-center gap-4 pt-2">
              <button onClick={onNavigateToSignUp} className="flex w-full items-center justify-center gap-2.5 rounded-lg border border-white/15 bg-white/[0.08] px-5 py-3.5 text-[15px] font-semibold text-white transition-all duration-200 active:scale-[0.97] hover:border-primary hover:bg-primary sm:w-auto sm:px-7 sm:py-4 sm:text-[16px]">
                <span>{t("landing.hero_cta_primary")}</span>
                <ArrowRight className="w-4.5 h-4.5" />
              </button>
            </MotionDiv>
          </div>

          <div className="lg:col-span-6 flex justify-center lg:justify-end h-full max-h-[460px]">
            <MotionDiv initial={{ opacity: 0, filter: "blur(10px)" }} animate={{ opacity: 1, filter: "blur(0px)" }} transition={{ duration: 0.8, delay: 0.3, ease: "easeOut" }} className="w-full h-full flex items-center">
              <EmailGatewayAnimation />
            </MotionDiv>
          </div>
        </div>

        <div className="w-full py-3.5 relative z-20 border-t border-b border-white/10 bg-black/60 backdrop-blur-xl shrink-0">
          <div className="relative flex max-w-full overflow-hidden">
            <div className="animate-marquee flex gap-16 whitespace-nowrap shrink-0">
              {[...marqueeItems, ...marqueeItems].map((item, idx) => {
                const Icon = item.icon;
                return (
                  <span key={idx} className="flex items-center gap-3.5 text-[16px] sm:text-[17px] font-semibold text-white/90">
                    <Icon className="w-5 h-5 text-primary/80 shrink-0" />
                    {item.label}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          FEATURES — Sleek Resend-style glassmorphism grid
          ═══════════════════════════════════════════════════════════════════════ */}
      <section id="features" className="py-20 lg:py-28 relative">
        <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(ellipse 80% 50% at 50% 20%, rgba(74,144,217,0.06) 0%, transparent 60%)" }} />
        <div className="max-w-7xl mx-auto px-6 lg:px-8 space-y-16 lg:space-y-20 relative z-10">
          <FadeInSection className="text-center max-w-4xl mx-auto space-y-4">
            <h2 className="font-display font-medium text-[clamp(2.15rem,4.2vw,3.25rem)] leading-[1.12] tracking-[-0.02em] text-slate-100">
              {t("landing.features_title")}
            </h2>
            <p className="text-[16px] sm:text-[18px] lg:text-[19px] leading-[1.65] max-w-4xl mx-auto font-normal text-slate-400">
              {t("landing.features_desc")}
            </p>
          </FadeInSection>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {featuresConfig.map((feat, idx) => {
              const IconComponent = feat.icon;
              return (
                <FadeInSection key={idx} delay={idx * 0.08}>
                  <div 
                    className="relative overflow-hidden text-left flex flex-col justify-between h-full group rounded-2xl transition-all duration-400 hover:scale-[1.02] hover:shadow-[0_16px_50px_rgba(74,144,217,0.14)] p-7"
                    style={{
                      background: "rgba(255, 255, 255, 0.02)",
                      backdropFilter: "blur(24px)",
                      WebkitBackdropFilter: "blur(24px)",
                      border: "1px solid rgba(255, 255, 255, 0.08)",
                    }}
                  >
                    {/* Resend top-center glass sheen reflection */}
                    <div
                      className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-20 pointer-events-none rounded-t-2xl"
                      style={{
                        background: "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.02) 45%, transparent 75%)",
                      }}
                    />
                    <div className="absolute top-0 left-6 right-6 h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent pointer-events-none" />

                    <div className="space-y-4 flex-1 flex flex-col justify-between relative z-10">
                      <div className="space-y-4">
                        <div className="w-10 h-10 rounded-xl bg-white/[0.05] border border-white/10 flex items-center justify-center text-white group-hover:bg-primary/20 group-hover:border-primary/40 group-hover:text-primary transition-all duration-300">
                          <IconComponent className="w-5 h-5" strokeWidth={1.75} />
                        </div>
                        <div className="font-display font-semibold text-[24px] text-white tracking-[-0.02em] leading-tight">
                          {feat.stat}
                        </div>
                        <div className="text-[11px] uppercase tracking-[0.12em] font-bold text-primary">
                          {feat.label}
                        </div>
                        <h3 className="font-display font-medium text-[20px] text-slate-100 tracking-tight leading-snug">
                          {feat.title}
                        </h3>
                        <p className="text-[15px] leading-[1.65] text-slate-400 font-normal">
                          {feat.desc}
                        </p>
                      </div>
                      {feat.preview}
                    </div>
                  </div>
                </FadeInSection>
              );
            })}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          INTEGRATION — Clean DNS auto-config showcase
          ═══════════════════════════════════════════════════════════════════════ */}
      <section id="integration" className="py-20 lg:py-28 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(ellipse 60% 40% at 30% 50%, rgba(74,144,217,0.06) 0%, transparent 60%)" }} />
        <div className="max-w-7xl mx-auto px-6 lg:px-8 relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            <FadeInSection className="space-y-6">
              <h2 className="font-display font-medium text-[clamp(2.15rem,4.2vw,3.25rem)] leading-[1.12] tracking-[-0.02em] text-slate-100">
                {t("landing.integration_title")}
              </h2>
              <p className="text-[17px] sm:text-[19px] leading-[1.65] text-slate-400 font-normal max-w-lg">
                {t("landing.integration_desc")}
              </p>
              <div className="flex flex-col sm:flex-row items-start gap-4 pt-2">
                <button
                  onClick={onNavigateToSignUp}
                  className="flex items-center gap-2.5 px-7 py-3.5 rounded-xl text-[15px] font-semibold text-white bg-white/[0.08] border border-white/15 hover:bg-[#f59e0b] hover:text-black hover:border-[#f59e0b] hover:shadow-[0_0_25px_rgba(245,158,11,0.35)] transition-all duration-200 active:scale-[0.98] cursor-pointer"
                >
                  <span>{t("landing.integration_cta")}</span>
                  <ArrowRight className="w-4.5 h-4.5" />
                </button>
              </div>
            </FadeInSection>

            {/* Right: Terminal Mock */}
            <FadeInSection delay={0.1} className="flex justify-center lg:justify-end">
              <IntegrationTerminal />
            </FadeInSection>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          CTA — Early-stage conversion section
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="pt-12 pb-36 lg:pt-16 lg:pb-48 relative overflow-hidden z-10">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none" style={{
          background: "radial-gradient(ellipse 70% 50% at 50% 30%, rgba(74,144,217,0.06) 0%, transparent 60%)",
        }} />

        <div className="max-w-4xl mx-auto px-6 lg:px-8 text-center space-y-10 relative z-10">
          <FadeInSection className="space-y-4">
            <h2 className="font-display font-medium text-[clamp(2rem,4vw,3rem)] leading-[1.12] tracking-[-0.02em] text-slate-100 mt-2">
              {t("landing.cta_section_title")}
            </h2>
            <p className="text-[16px] sm:text-[18px] lg:text-[19px] leading-[1.65] max-w-3xl mx-auto font-normal text-slate-400 md:whitespace-nowrap">
              {t("landing.cta_section_desc")}
            </p>
          </FadeInSection>

          <FadeInSection delay={0.14}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-1">
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2.5 px-7 py-3.5 rounded-xl text-[15px] font-semibold transition-all active:scale-[0.97] cursor-pointer duration-200"
                style={{
                  background: "linear-gradient(135deg, rgba(74,144,217,0.2) 0%, rgba(74,144,217,0.1) 100%)",
                  border: "1px solid rgba(74,144,217,0.3)",
                  color: "#fff",
                  boxShadow: "0 4px 24px rgba(74,144,217,0.12)",
                }}
              >
                <span>{t("landing.cta_section_trial")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
            <div className="text-[13px] text-slate-400 mt-3 font-medium">
              {t("landing.cta_no_card")}
            </div>
          </FadeInSection>

          <FadeInSection delay={0.18} className="pt-4 flex flex-wrap justify-center gap-x-8 gap-y-3 text-[14px] font-medium">
            <div className="flex items-center gap-2 text-slate-300">
              <ShieldCheck className="w-4.5 h-4.5 text-emerald-400" />
              <span>{t("landing.cta_badge_rgpd")}</span>
            </div>
            <div className="flex items-center gap-2 text-slate-300">
              <ShieldCheck className="w-4.5 h-4.5 text-emerald-400" />
              <span>{t("landing.cta_badge_sovereign")}</span>
            </div>
            <div className="flex items-center gap-2 text-slate-300">
              <ShieldCheck className="w-4.5 h-4.5 text-emerald-400" />
              <span>{t("landing.cta_badge_instant")}</span>
            </div>
          </FadeInSection>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          FOOTER — Compact sleek dark glassmorphism footer
          ═══════════════════════════════════════════════════════════════════════ */}
      <footer className="border-t border-white/10 py-5 relative z-10 bg-black/60 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-6 h-6" />
            <span className="font-display font-bold text-white text-[15px] tracking-tight">Sicurre</span>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-[13px] font-medium">
            <button
              onClick={onNavigateToMentionsLegales}
              className="text-slate-300 hover:text-white transition-colors cursor-pointer border-none bg-transparent p-0 font-medium outline-none"
            >
              {t("landing.footer_mentions")}
            </button>
            <button
              onClick={onNavigateToConfidentialite}
              className="text-slate-300 hover:text-white transition-colors cursor-pointer border-none bg-transparent p-0 font-medium outline-none"
            >
              {t("landing.footer_privacy")}
            </button>
            <button
              onClick={onNavigateToContact}
              className="text-slate-300 hover:text-white transition-colors cursor-pointer border-none bg-transparent p-0 font-medium outline-none"
            >
              {t("landing.footer_contact")}
            </button>
          </div>
          <div className="text-[12px] text-slate-400 font-normal">
            {t("landing.footer_copyright")}
          </div>
        </div>
      </footer>
    </div>
  );
}
