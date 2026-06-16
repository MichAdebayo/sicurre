import { ShieldCheck, ArrowRight, ShieldAlert, Sparkles, Mail, CheckCircle2, Zap, Brain, Lock } from "lucide-react";
import { motion } from "framer-motion";

const MotionDiv = motion.div as any;

interface LandingRouteProps {
  onNavigateToLogin: () => void;
  onNavigateToSignUp: () => void;
}

const STEPS = [
  {
    num: "01",
    title: "Connexion Gmail",
    desc: "Autorisez Sicurre en un clic via OAuth Google. Pas de redirection DNS, pas de configuration réseau.",
    color: "text-primary border-primary/30 bg-primary/10",
  },
  {
    num: "02",
    title: "Analyse en temps réel",
    desc: "Chaque email entrant est immédiatement soumis à notre pipeline IA : ONNX, DMARC, URL et signaux contextuels.",
    color: "text-accent border-accent/30 bg-accent/10",
  },
  {
    num: "03",
    title: "Remédiation automatique",
    desc: "Les menaces confirmées sont déplacées en corbeille en moins de 2 secondes. Vous ne les verrez jamais.",
    color: "text-green-400 border-green-500/30 bg-green-500/10",
  },
];

export default function LandingRoute({ onNavigateToLogin, onNavigateToSignUp }: LandingRouteProps) {
  return (
    <div className="min-h-screen bg-[#0B0F19] text-white relative overflow-hidden flex flex-col">
      {/* Background grid & glows */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f293710_1px,transparent_1px),linear-gradient(to_bottom,#1f293710_1px,transparent_1px)] bg-[size:4rem_4rem] pointer-events-none" />
      <div className="absolute top-1/4 left-1/4 w-[28rem] h-[28rem] bg-primary/10 rounded-full blur-[130px] pointer-events-none" />
      <div className="absolute bottom-1/3 right-1/4 w-[22rem] h-[22rem] bg-accent/6 rounded-full blur-[130px] pointer-events-none" />

      {/* ── Header ────────────────────────────────────────────── */}
      <header className="relative z-10 max-w-7xl mx-auto w-full px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 bg-primary/20 rounded-lg flex items-center justify-center border border-primary/30">
            <ShieldAlert className="w-5 h-5 text-primary" />
          </div>
          <span className="text-xl font-display font-bold text-white tracking-tight">Sicurre</span>
        </div>
        <nav className="flex items-center gap-4">
          <button
            onClick={onNavigateToLogin}
            className="text-sm font-semibold text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            Se connecter
          </button>
          <button
            onClick={onNavigateToSignUp}
            className="text-sm font-semibold px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-lg transition-all active:scale-[0.97] cursor-pointer"
          >
            Démarrer gratuitement
          </button>
        </nav>
      </header>

      {/* ── Hero ──────────────────────────────────────────────── */}
      <main className="relative z-10 flex-1">
        <section className="max-w-5xl mx-auto px-6 pt-20 pb-24 text-center space-y-10">
          <MotionDiv
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="space-y-6"
          >
            {/* Live status pill */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-xs text-accent">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-70" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
              </span>
              <Sparkles className="w-3 h-3" />
              <span>IA souveraine française · CamemBERTav2</span>
            </div>

            <h1 className="text-4xl sm:text-6xl font-display font-bold text-white tracking-tight leading-tight max-w-4xl mx-auto">
              Vos emails,{" "}
              <span className="relative inline-block">
                <span className="text-primary">protégés en 2s</span>
                <span className="absolute -bottom-1 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent" />
              </span>
              .
            </h1>

            <p className="text-lg text-slate-400 max-w-2xl mx-auto leading-relaxed">
              Sicurre est un gardien silencieux pour vos boîtes Gmail. Notre pipeline IA détecte et neutralise
              phishing, spam et usurpations <em className="text-slate-300 not-italic font-medium">avant même que vous ne les lisiez</em>.
            </p>
          </MotionDiv>

          {/* CTAs */}
          <MotionDiv
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="flex flex-col sm:flex-row gap-4 justify-center items-center"
          >
            <button
              onClick={onNavigateToSignUp}
              className="group w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-4 bg-accent hover:bg-accent-dark text-slate-950 font-bold rounded-xl shadow-lg shadow-accent/15 hover:shadow-accent/30 active:scale-[0.97] transition-all cursor-pointer text-base"
            >
              <span>Protéger ma boîte gratuitement</span>
              <ArrowRight className="w-4.5 h-4.5 group-hover:translate-x-0.5 transition-transform" />
            </button>
            <button
              onClick={onNavigateToLogin}
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-4 bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-200 font-semibold rounded-xl active:scale-[0.97] transition-all cursor-pointer text-base"
            >
              <span>Accéder à la console</span>
            </button>
          </MotionDiv>

          {/* Trust strip */}
          <MotionDiv
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.35 }}
            className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-xs text-slate-500 pt-2"
          >
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-green-500" /> Hébergé en Europe</span>
            <span className="flex items-center gap-1.5"><Lock className="w-3.5 h-3.5 text-blue-400" /> RGPD natif</span>
            <span className="flex items-center gap-1.5"><Zap className="w-3.5 h-3.5 text-accent" /> &lt; 2s de remédiation</span>
            <span className="flex items-center gap-1.5"><Brain className="w-3.5 h-3.5 text-primary" /> Modèle open-source CamemBERTav2</span>
          </MotionDiv>
        </section>

        {/* ── Feature grid ───────────────────────────────────── */}
        <section className="relative z-10 max-w-5xl mx-auto px-6 pb-20">
          <MotionDiv
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className="grid grid-cols-1 md:grid-cols-3 gap-5 text-left"
          >
            <div className="group p-6 bg-slate-900/60 border border-slate-800/80 hover:border-primary/30 rounded-2xl space-y-3 transition-colors">
              <div className="w-10 h-10 bg-primary/15 rounded-xl flex items-center justify-center border border-primary/25 text-primary group-hover:scale-105 transition-transform">
                <Mail className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-white font-display">Intégration Gmail directe</h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                Activez la protection en un clic via OAuth Google. Aucun changement de MX ou DNS.
              </p>
              <span className="inline-block text-[10px] font-semibold tracking-wider uppercase text-primary/70 bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">Disponible</span>
            </div>

            <div className="group p-6 bg-slate-900/60 border border-slate-800/80 hover:border-accent/30 rounded-2xl space-y-3 transition-colors">
              <div className="w-10 h-10 bg-accent/15 rounded-xl flex items-center justify-center border border-accent/25 text-accent group-hover:scale-105 transition-transform">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-white font-display">IA souveraine française</h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                CamemBERTav2 entraîné et hébergé en Europe. Vos emails ne quittent jamais le territoire.
              </p>
              <span className="inline-block text-[10px] font-semibold tracking-wider uppercase text-accent/70 bg-accent/10 border border-accent/20 px-2 py-0.5 rounded-full">INT8 ONNX</span>
            </div>

            <div className="group p-6 bg-slate-900/60 border border-slate-800/80 hover:border-green-500/30 rounded-2xl space-y-3 transition-colors">
              <div className="w-10 h-10 bg-green-500/10 rounded-xl flex items-center justify-center border border-green-500/20 text-green-400 group-hover:scale-105 transition-transform">
                <Zap className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-white font-display">Remédiation en 2 secondes</h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                Les phishing confirmés vont directement en corbeille avant que vous ne les ouvriez.
              </p>
              <span className="inline-block text-[10px] font-semibold tracking-wider uppercase text-green-400/70 bg-green-500/10 border border-green-500/20 px-2 py-0.5 rounded-full">Temps réel</span>
            </div>
          </MotionDiv>
        </section>

        {/* ── How it works ───────────────────────────────────── */}
        <section className="relative z-10 max-w-5xl mx-auto px-6 pb-24">
          <MotionDiv
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.5 }}
          >
            <div className="text-center mb-10">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-2">Fonctionnement</p>
              <h2 className="text-2xl font-display font-bold text-white">Opérationnel en 3 étapes</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative">
              {/* Connecting line (desktop only) */}
              <div className="hidden md:block absolute top-8 left-[calc(16.666%+1rem)] right-[calc(16.666%+1rem)] h-px bg-gradient-to-r from-primary/30 via-accent/30 to-green-500/30" />

              {STEPS.map((step) => (
                <div key={step.num} className="flex flex-col items-center text-center space-y-3">
                  <div className={`w-14 h-14 rounded-2xl flex items-center justify-center border text-2xl font-display font-bold ${step.color} relative z-10`}>
                    {step.num}
                  </div>
                  <h3 className="text-sm font-semibold text-white">{step.title}</h3>
                  <p className="text-xs text-slate-400 leading-relaxed max-w-[220px]">{step.desc}</p>
                </div>
              ))}
            </div>
          </MotionDiv>
        </section>
      </main>

      {/* ── Footer ────────────────────────────────────────────── */}
      <footer className="relative z-10 py-6 border-t border-slate-900/80">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-3.5 h-3.5 text-slate-600" />
            <span>&copy; 2026 Sicurre SAS · Tous droits réservés</span>
          </div>
          <div className="flex items-center gap-4">
            <span>RGPD compliant</span>
            <span>·</span>
            <span>Hébergé en Europe</span>
            <span>·</span>
            <span>Open-source</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
