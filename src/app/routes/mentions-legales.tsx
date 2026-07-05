import { motion } from "framer-motion";
import sicurreLogo from "../assets/sicurre.svg";

const MotionDiv = motion.div as any;

interface MentionsLegalesProps {
  onBack: () => void;
}

export default function MentionsLegalesRoute({ onBack }: MentionsLegalesProps) {
  return (
    <div className="min-h-screen bg-black text-white font-sans py-16 px-6 lg:px-8 select-none relative overflow-x-hidden">
      {/* Subtle top spotlight glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-5xl h-96 pointer-events-none" style={{
        background: "radial-gradient(ellipse 60% 50% at 50% 0%, rgba(74,144,217,0.08) 0%, transparent 70%)",
      }} />

      <div className="max-w-3xl mx-auto space-y-8 relative z-10">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 pb-6">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-9 h-9" />
            <span className="font-display font-bold text-xl text-white tracking-tight">Sicurre</span>
          </div>
          <button
            onClick={onBack}
            className="px-4.5 py-2 text-xs font-semibold text-white/90 bg-white/[0.06] hover:bg-primary hover:border-primary border border-white/15 rounded-xl cursor-pointer transition-all shadow-sm"
          >
            &larr; Retour à l'accueil
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
              Mentions Légales
            </h1>
            <p className="text-xs text-slate-400 font-medium">Dernière mise à jour : 18 juin 2026</p>
          </div>

          <hr className="border-white/10" />

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">1. Éditeur du site</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Le site <strong className="text-white">sicurre.io</strong> est édité par la société <strong className="text-white">Sicurre SAS</strong>, 
              société par actions simplifiée au capital de 15 000 euros, immatriculée au Registre du Commerce 
              et des Sociétés de Paris sous le numéro 987 654 321, dont le siège social est situé à 
              Roubaix, France.
            </p>
            <p className="text-sm text-slate-400">
              <strong className="text-white">Directeur de la publication :</strong> Michael Adebayo, en sa qualité de Président de Sicurre SAS.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">2. Hébergement</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Le site et la plateforme applicative sont hébergés par :
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-400 space-y-1.5">
              <li>
                <strong className="text-white">Neon Inc.</strong> (Base de données) : 2443 Fillmore St, San Francisco, CA 94115, États-Unis.
              </li>
              <li>
                <strong className="text-white">Google Cloud Platform</strong> (Infrastructures de calcul et stockage) : Google Ireland Limited, 
                Gordon House, Barrow Street, Dublin 4, Irlande. (Serveurs situés en Europe, région de Paris).
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">3. Nous contacter</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Pour toute question ou demande de support, vous pouvez contacter nos équipes :
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-400 space-y-1.5">
              <li><strong className="text-white">Par e-mail :</strong> contact@sicurre.com</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">4. Propriété intellectuelle</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              L'ensemble du contenu présent sur le site (textes, logos, animations 3D, chartes graphiques) 
              est la propriété exclusive de Sicurre SAS. Toute reproduction, modification ou distribution 
              sans accord écrit préalable est strictly interdite.
            </p>
          </section>
        </MotionDiv>

        {/* Footer */}
        <div className="text-center text-xs text-slate-500">
          © 2026 Sicurre SAS. Tous droits réservés.
        </div>
      </div>
    </div>
  );
}
