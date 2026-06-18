import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  MessageSquare,
  Activity,
  UserCheck,
  ChevronDown,
  ChevronUp,
  BookOpen,
  Cpu,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";

const MotionDiv = motion.div as any;

export default function SupportRoute() {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const faqs = [
    {
      q: "Comment fonctionne l'analyse anti-phishing en temps réel ?",
      a: "Chaque fois qu'un e-mail arrive dans votre boîte Gmail connectée, une notification webhook déclenche instantanément le Gmail Listener de Sicurre. L'e-mail est traité en moins de 2 secondes par notre modèle d'analyse souverain et, en cas de menace, déplacé directement vers la corbeille.",
    },
    {
      q: "Quelles données de mes e-mails sont conservées par Sicurre ?",
      a: "Pour des raisons RGPD, Sicurre ne stocke jamais le corps complet de vos e-mails. Seuls les métadonnées (expéditeur, sujet, verdict et indices de confiance) sont conservées de façon anonyme au sein de notre console de supervision.",
    },
    {
      q: "Comment puis-je révoquer l'accès de Sicurre à ma boîte Gmail ?",
      a: "Vous pouvez révoquer l'accès à tout moment via la gestion des applications autorisées de votre compte Google, ou directement depuis l'onglet Réglages de la console Sicurre.",
    },
  ];

  const quickActions = [
    {
      icon: MessageSquare,
      title: "Ticket Critique",
      desc: "Signalez une anomalie ou une fausse classification urgente.",
      action: "Ouvrir",
    },
    {
      icon: Activity,
      title: "Diagnostic Système",
      desc: "Lancez un auto-test du Gmail Listener et du classificateur.",
      action: "Lancer",
    },
    {
      icon: UserCheck,
      title: "Expert Niveau 3",
      desc: "Planifiez une session de 15 minutes avec notre CISO.",
      action: "Réserver",
    },
  ];

  const systemNodes = [
    { name: "Pare-feu Global", status: "Opérationnel", metric: "Uptime", value: "99.99 %" },
    { name: "Modèle d'Analyse", status: "Opérationnel", metric: "Latence", value: "82 ms" },
    { name: "Collecteur de Logs", status: "Opérationnel", metric: "Débit entrant", value: "14 req/s" },
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
          Support & Assistance Technique
        </h1>
        <p className="text-sm text-on-surface-variant mt-1">
          Accédez à notre base de connaissances et contactez nos experts en cyber-résilience
        </p>
      </div>

      {/* Search */}
      <div className="relative w-full max-w-2xl">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-on-surface-variant/30" />
        <input
          type="text"
          placeholder="Rechercher dans la base de connaissances (ex. bypass pare-feu, jetons API...)"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-12 pr-4 py-3 bg-white border border-border-subtle rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/35 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all shadow-sm"
        />
      </div>

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Main Area */}
        <div className="lg:col-span-8 space-y-6">
          {/* Quick Actions */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {quickActions.map((action, idx) => {
              const Icon = action.icon;
              return (
                <div
                  key={idx}
                  className="bg-white rounded-xl border border-border-subtle p-5 flex flex-col justify-between hover:border-primary/20 hover:shadow-md hover:shadow-primary/[0.03] transition-all cursor-pointer group h-full"
                >
                  <div className="space-y-3">
                    <div className="p-2.5 bg-primary/[0.06] text-primary border border-primary/10 rounded-xl w-fit group-hover:scale-105 transition-transform">
                      <Icon className="w-5 h-5 stroke-[1.5]" />
                    </div>
                    <h3 className="font-display font-bold text-sm text-on-surface">{action.title}</h3>
                    <p className="text-[12px] text-on-surface-variant/70 leading-relaxed">
                      {action.desc}
                    </p>
                  </div>
                  <span className="text-[12px] text-primary font-bold flex items-center gap-1 mt-4 group-hover:gap-2 transition-all">
                    {action.action}
                    <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              );
            })}
          </div>

          {/* FAQ */}
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <h3 className="font-display font-semibold text-[17px] text-on-surface mb-5 pb-4 border-b border-border-subtle">
              Résolutions de Problèmes Courants
            </h3>
            <div className="space-y-2.5">
              {faqs.map((faq, idx) => (
                <div key={idx} className="border border-border-subtle rounded-xl overflow-hidden">
                  <button
                    onClick={() => setOpenFaq(openFaq === idx ? null : idx)}
                    className="w-full px-5 py-4 flex items-center justify-between text-left font-semibold text-sm text-on-surface hover:bg-surface-low/30 transition-colors cursor-pointer select-none"
                  >
                    <span>{faq.q}</span>
                    {openFaq === idx ? (
                      <ChevronUp className="w-4 h-4 text-on-surface-variant/50 shrink-0" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-on-surface-variant/50 shrink-0" />
                    )}
                  </button>
                  <AnimatePresence initial={false}>
                    {openFaq === idx && (
                      <MotionDiv
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.2, ease: "easeOut" }}
                        className="border-t border-border-subtle/50"
                      >
                        <p className="px-5 py-4 text-sm text-on-surface-variant leading-relaxed bg-surface-low/20">
                          {faq.a}
                        </p>
                      </MotionDiv>
                    )}
                  </AnimatePresence>
                </div>
              ))}
            </div>
          </div>

          {/* Documentation Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border border-border-subtle p-5 flex items-start gap-4 hover:border-primary/20 hover:shadow-sm transition-all cursor-pointer">
              <div className="p-2 bg-primary/[0.06] text-primary border border-primary/10 rounded-lg shrink-0">
                <BookOpen className="w-5 h-5 stroke-[1.5]" />
              </div>
              <div className="space-y-1">
                <h4 className="font-display font-bold text-sm text-on-surface">Guide d'Intégration API</h4>
                <p className="text-[12px] text-on-surface-variant/60 leading-relaxed">
                  Connectez les alertes Sicurre à votre SIEM ou Slack.
                </p>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-border-subtle p-5 flex items-start gap-4 hover:border-primary/20 hover:shadow-sm transition-all cursor-pointer">
              <div className="p-2 bg-primary/[0.06] text-primary border border-primary/10 rounded-lg shrink-0">
                <ShieldCheck className="w-5 h-5 stroke-[1.5]" />
              </div>
              <div className="space-y-1">
                <h4 className="font-display font-bold text-sm text-on-surface">Protocoles de Sécurité</h4>
                <p className="text-[12px] text-on-surface-variant/60 leading-relaxed">
                  Modèle souverain et conformité RGPD.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar: System Status */}
        <div className="lg:col-span-4">
          <div className="bg-white rounded-xl border border-border-subtle p-6">
            <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-border-subtle">
              <Cpu className="w-5 h-5 text-primary" />
              <h3 className="font-display font-semibold text-[17px] text-on-surface">Statuts des Nœuds</h3>
            </div>
            <div className="space-y-3">
              {systemNodes.map((node, idx) => (
                <div key={idx} className="p-3.5 bg-surface-low/50 border border-border-subtle rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sm text-on-surface">{node.name}</span>
                    <span className="text-[11px] text-safe font-bold">{node.status}</span>
                  </div>
                  <div className="flex justify-between items-center text-[12px] text-on-surface-variant/60">
                    <span>{node.metric}</span>
                    <span className="font-mono font-bold">{node.value}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </MotionDiv>
  );
}
