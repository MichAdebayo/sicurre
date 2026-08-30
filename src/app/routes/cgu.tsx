import { motion } from "framer-motion";
import { Home } from "lucide-react";
import sicurreLogo from "../assets/sicurre.svg";

const MotionDiv = motion.div as any;

interface CGURouteProps {
  onBack: () => void;
}

export default function CGURoute({ onBack }: CGURouteProps) {
  return (
    <div className="min-h-screen bg-black text-white font-sans py-16 px-6 lg:px-8 select-none relative overflow-x-hidden">
      {/* Top spotlight glow */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-5xl h-96 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse 60% 50% at 50% 0%, rgba(74,144,217,0.08) 0%, transparent 70%)",
        }}
      />

      <div className="max-w-3xl mx-auto space-y-8 relative z-10">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 pb-6">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-9 h-9" />
            <span className="font-display font-bold text-xl text-white tracking-tight">Sicurre</span>
          </div>
          <button
            onClick={onBack}
            aria-label="Retour à l'accueil"
            className="p-2.5 text-white/90 bg-white/[0.06] hover:bg-primary hover:border-primary border border-white/15 rounded-xl cursor-pointer transition-all shadow-sm flex items-center justify-center"
          >
            <Home className="w-4.5 h-4.5" />
          </button>
        </div>

        {/* Content Card */}
        <MotionDiv
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{
            background: "rgba(255, 255, 255, 0.02)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
          }}
          className="rounded-2xl p-8 lg:p-10 space-y-7 shadow-2xl text-left"
        >
          <div>
            <h1 className="font-display font-medium text-3xl text-slate-100 tracking-tight mb-2">
              Conditions Générales d'Utilisation
            </h1>
            <p className="text-xs text-slate-400 font-medium">Dernière mise à jour : 18 juin 2026</p>
          </div>

          <hr className="border-white/10" />

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">1. Objet des CGU</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Les présentes Conditions Générales d'Utilisation (CGU) encadrent l'accès et l'utilisation de la plateforme 
              <strong className="text-white"> Sicurre</strong> (éditée par Sicurre). La plateforme fournit un service automatisé 
              d'analyse et de remédiation en temps réel des menaces par e-mail (phishing, spam, ingénierie sociale).
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">2. Connexion & Intégration Cloudflare</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              L'activation de la protection Sicurre nécessite l'association d'un jeton d'accès Cloudflare restreint. 
              En configurant cette intégration, l'utilisateur autorise Sicurre à :
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-400 space-y-1.5">
              <li>Inspecter les métadonnées des e-mails entrants en temps réel (expéditeur, sujet, verdict de score).</li>
              <li>Configurer les enregistrements DNS requis (SPF, DKIM, DMARC) pour la sécurisation du domaine.</li>
              <li>Conserver en quarantaine isolée temporaire les messages identifiés comme malveillants.</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">3. Engagements & Responsabilités</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Sicurre met en œuvre des contrôles de sécurité, de supervision et de reprise adaptés à son environnement.
              Aucun niveau de service contractuel n'est garanti pendant cette phase de validation. L'utilisateur demeure
              responsable de la confidentialité de ses identifiants d'accès et du maintien des jetons API associés à ses domaines.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">4. Modification et Résiliation</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Sicurre se réserve le droit de modifier les présentes CGU à tout moment. L'utilisateur peut mettre fin à son 
              utilisation ou révoquer la protection Sicurre à tout moment depuis le tableau de bord ou en supprimant le jeton Cloudflare.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">5. Droit applicable & Juridiction</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Les présentes CGU sont soumises au droit français. Tout litige relatif à leur interprétation ou exécution 
              relève des tribunaux compétents de Paris, France.
            </p>
          </section>
        </MotionDiv>

        {/* Footer */}
        <div className="text-center text-xs text-slate-500">
          © 2026 Sicurre. Tous droits réservés.
        </div>
      </div>
    </div>
  );
}
