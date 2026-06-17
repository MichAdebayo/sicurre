import { useEffect, useRef, useState } from "react";
import {
  Shield,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  Zap,
  Lock,
  Mail,
  Server,
  Link2,
  UserCheck,
  RotateCcw,
  CheckCircle2,
  BarChart3,
} from "lucide-react";
import { motion } from "framer-motion";
import serverRoomImg from "../assets/server-room.png";

const MotionDiv = motion.div as any;
const MotionSection = motion.section as any;

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

export default function LandingRoute({ onNavigateToLogin, onNavigateToSignUp }: LandingRouteProps) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const features = [
    {
      icon: Link2,
      title: "Analyse Dynamique des Liens",
      desc: "Inspection en temps réel de chaque URL dans chaque e-mail. Nous suivons les redirections et analysons les destinations finales pour détecter les intentions malveillantes.",
    },
    {
      icon: UserCheck,
      title: "Vérification d'Identité",
      desc: "Protection contre le Business Email Compromise (BEC) avec cartographie avancée de l'identité des expéditeurs et détection d'anomalies comportementales.",
    },
    {
      icon: RotateCcw,
      title: "Auto-Remédiation",
      desc: "Pas besoin d'attendre l'équipe IT. Notre plateforme récupère automatiquement les e-mails malveillants de toutes les boîtes de réception connectées en moins de 2 secondes.",
    },
  ];

  const marqueeItems = [
    { icon: Shield, label: "ARCHITECTURE ZERO-TRUST" },
    { icon: ShieldAlert, label: "DÉTECTION IA MENACES" },
    { icon: Lock, label: "INTÉGRATION SAML/SSO" },
    { icon: Mail, label: "SÉCURITÉ E-MAIL NATIVE" },
    { icon: Zap, label: "ANALYSE TEMPS RÉEL" },
    { icon: Server, label: "INFÉRENCE CAMEMBERTAV2" },
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
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-primary text-on-primary">
              <Shield className="w-5 h-5 stroke-[1.5]" />
            </div>
            <span className={`font-display font-bold text-lg tracking-tight ${scrolled ? "text-on-surface" : "text-on-surface"}`}>
              Sicurre
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-[13px] font-medium text-on-surface-variant">
            <a href="#features" className="hover:text-primary transition-colors">Fonctionnalités</a>
            <a href="#pricing" className="hover:text-primary transition-colors">Tarifs</a>
            <a href="#compliance" className="hover:text-primary transition-colors">Ressources</a>
          </nav>

          <div className="flex items-center gap-3">
            <button
              onClick={onNavigateToLogin}
              className="text-[13px] font-semibold text-on-surface-variant hover:text-primary transition-colors cursor-pointer hidden sm:block"
            >
              Connexion
            </button>
            <button
              onClick={onNavigateToSignUp}
              className="px-4 py-2 bg-primary hover:bg-navy-dark text-on-primary rounded-lg text-[13px] font-semibold transition-all active:scale-[0.97] cursor-pointer shadow-sm"
            >
              Commencer
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero Section — White background, matching Stitch mockup ── */}
      <section className="relative bg-white pt-28 pb-16 lg:pt-36 lg:pb-24 overflow-hidden">
        {/* Subtle grid pattern */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,56,164,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,56,164,0.03)_1px,transparent_1px)] bg-[size:4rem_4rem]" />
        {/* Soft radial glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-[radial-gradient(ellipse,rgba(27,79,204,0.06),transparent_60%)]" />

        <div className="max-w-7xl mx-auto px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start relative z-10">
          {/* Left: Copy */}
          <div className="lg:col-span-7 space-y-7 pt-6">
            <MotionDiv
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-primary/[0.06] border border-primary/10 text-primary text-[11px] font-bold tracking-wider uppercase"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Cyber-résilience pour les PME</span>
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.08 }}
            >
              <h1 className="font-display font-bold text-[clamp(2rem,5vw,3.25rem)] leading-[1.1] tracking-tight text-on-surface">
                Protection Anti-Phishing{" "}
                <br className="hidden lg:block" />
                de Nouvelle Génération{" "}
                <br className="hidden lg:block" />
                pour la{" "}
                <span className="text-primary italic">PME Moderne</span>
              </h1>
            </MotionDiv>

            <MotionDiv
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.16 }}
              className="text-[17px] text-on-surface-variant leading-relaxed max-w-xl"
            >
              Déployez une sécurité e-mail de niveau entreprise qui identifie les menaces sophistiquées avant qu'elles n'atteignent votre boîte de réception. Pas de configuration complexe, juste une protection pure.
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
                <span>Essai Gratuit de 14 Jours</span>
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={onNavigateToLogin}
                className="flex items-center gap-2 px-7 py-3.5 bg-white hover:bg-surface-low border border-border-subtle text-on-surface font-semibold rounded-lg active:scale-[0.97] transition-all cursor-pointer text-[15px]"
              >
                <span>Réserver une Démo</span>
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
                Approuvé par <strong className="text-on-surface">500+</strong> PME en France
              </span>
            </MotionDiv>
          </div>

          {/* Right: Glassmorphic Security Overview Card */}
          <div className="lg:col-span-5 flex justify-center lg:justify-end">
            <MotionDiv
              initial={{ opacity: 0, scale: 0.96, y: 24 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
              className="w-full max-w-sm"
            >
              <div className="bg-white rounded-2xl border border-border-subtle shadow-xl shadow-on-surface/[0.06] p-6 space-y-5">
                {/* Card Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-error animate-pulse" />
                    <span className="text-sm font-bold text-on-surface">Security Overview</span>
                  </div>
                  <span className="text-[11px] font-mono text-primary bg-primary/[0.06] px-2 py-0.5 rounded-md font-medium">v2.4.0</span>
                </div>

                {/* Threat Alert Row */}
                <div className="flex items-center justify-between p-3.5 bg-error/[0.04] border border-error/10 rounded-xl">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-error/10 text-error rounded-lg">
                      <ShieldAlert className="w-4.5 h-4.5 stroke-[1.5]" />
                    </div>
                    <div>
                      <div className="text-sm font-bold text-on-surface">Threat Detected</div>
                      <div className="text-[11px] text-on-surface-variant">Suspicious credential harvester</div>
                    </div>
                  </div>
                  <span className="text-[11px] font-bold text-on-error bg-primary px-2.5 py-1 rounded-md">Block</span>
                </div>

                {/* Shield Active Row */}
                <div className="flex items-center justify-between p-3.5 bg-surface-low/60 border border-border-subtle rounded-xl">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-safe/10 text-safe rounded-lg">
                      <ShieldCheck className="w-4.5 h-4.5 stroke-[1.5]" />
                    </div>
                    <div>
                      <div className="text-sm font-bold text-on-surface">Inbox Shield Active</div>
                      <div className="text-[11px] text-on-surface-variant">542 emails secured this week</div>
                    </div>
                  </div>
                  <BarChart3 className="w-5 h-5 text-primary" />
                </div>

                {/* Threat Radius Progress */}
                <div className="space-y-2 pt-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="font-semibold text-on-surface-variant uppercase tracking-wider">Threat Radius</span>
                    <span className="font-mono font-bold text-safe">85 % SECURE</span>
                  </div>
                  <div className="w-full h-2 bg-surface-container rounded-full overflow-hidden">
                    <div className="h-full bg-primary rounded-full transition-all duration-1000" style={{ width: "85%" }} />
                  </div>
                </div>
              </div>
            </MotionDiv>
          </div>
        </div>
      </section>

      {/* ── Feature Marquee ── */}
      <section className="bg-[#0B1426] border-y border-white/5 py-5 overflow-hidden">
        <div className="relative flex max-w-full">
          <div className="animate-marquee flex gap-10 whitespace-nowrap text-white/50 text-[10px] font-bold tracking-[0.15em] uppercase shrink-0">
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
              Protection de Précision
            </h2>
            <p className="text-on-surface-variant text-[16px] leading-relaxed">
              Nous ciblons l'élément humain de la sécurité, neutralisant les attaques avant qu'elles n'exploitent votre équipe.
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
              Conçu pour les Environnements à Enjeux Élevés
            </h2>
            <p className="text-white/60 text-[16px] leading-relaxed max-w-lg">
              Les responsables IT méritent un outil qui parle leur langage. Sicurre offre un contrôle granulaire sans la complexité des suites de sécurité héritées.
            </p>
            <ul className="space-y-4">
              {[
                "Intégration API-first pour O365 & Google Workspace",
                "Mode invisible pour zéro impact sur le flux utilisateur",
                "Traitement des données conforme SOC 2 & chiffrement",
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
              Sécurisez Votre Entreprise Aujourd'hui
            </h2>
          </FadeInSection>
          <FadeInSection delay={0.06}>
            <p className="text-white/80 text-[16px] leading-relaxed max-w-xl mx-auto">
              Rejoignez des centaines de dirigeants qui dorment mieux en sachant que leur passerelle e-mail est protégée par Sicurre.
            </p>
          </FadeInSection>
          <FadeInSection delay={0.12}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
              <button
                onClick={onNavigateToSignUp}
                className="flex items-center gap-2 px-7 py-3.5 bg-white text-primary hover:bg-surface-low font-bold rounded-lg shadow-lg transition-all active:scale-[0.97] cursor-pointer text-[15px]"
              >
                <span>Essai Gratuit de 14 Jours</span>
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={onNavigateToLogin}
                className="flex items-center gap-2 px-7 py-3.5 bg-white/10 hover:bg-white/15 border border-white/20 text-white font-semibold rounded-lg transition-all active:scale-[0.97] cursor-pointer text-[15px]"
              >
                <span>Planifier une Démo</span>
              </button>
            </div>
            <p className="text-white/50 text-[12px] mt-4">
              Aucune carte bancaire requise. Opérationnel en moins de 5 minutes.
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
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-primary text-on-primary">
                  <Shield className="w-4 h-4" />
                </div>
                <span className="font-display font-bold text-white text-[15px]">Sicurre</span>
              </div>
              <p className="text-[12px] text-white/40 leading-relaxed max-w-[200px]">
                La solution française souveraine de protection anti-phishing pour les PME modernes.
              </p>
            </div>

            {/* Product */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">Produit</span>
              <ul className="text-[12px] space-y-2.5">
                <li><a href="#" className="hover:text-white transition-colors">Fonctionnalités</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Tarifs</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Sécurité</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Conformité</a></li>
              </ul>
            </div>

            {/* Resources */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">Ressources</span>
              <ul className="text-[12px] space-y-2.5">
                <li><a href="#" className="hover:text-white transition-colors">Blog</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Documentation</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Support</a></li>
                <li><a href="#" className="hover:text-white transition-colors">API</a></li>
              </ul>
            </div>

            {/* Company */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">Société</span>
              <ul className="text-[12px] space-y-2.5">
                <li><a href="#" className="hover:text-white transition-colors">À propos</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Contact</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Confidentialité</a></li>
                <li><a href="#" className="hover:text-white transition-colors">CGU</a></li>
              </ul>
            </div>

            {/* Trust */}
            <div className="space-y-3">
              <span className="text-[10px] font-bold text-white tracking-[0.15em] uppercase">Confiance</span>
              <div className="flex flex-wrap gap-2">
                <span className="text-[10px] font-bold text-white/60 bg-white/5 border border-white/10 px-2.5 py-1 rounded-md">SOC 2</span>
                <span className="text-[10px] font-bold text-white/60 bg-white/5 border border-white/10 px-2.5 py-1 rounded-md">RGPD</span>
              </div>
            </div>
          </div>

          {/* Bottom Bar */}
          <div className="border-t border-white/5 pt-6 flex flex-col sm:flex-row items-center justify-between text-[11px] text-white/30 gap-3">
            <span>&copy; 2026 Sicurre SAS. Tous droits réservés.</span>
            <span>Protection sécurisée pour l'entreprise moderne.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
