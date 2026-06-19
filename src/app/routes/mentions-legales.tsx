import { motion } from "framer-motion";
import sicurreLogo from "../assets/sicurre.svg";

const MotionDiv = motion.div as any;

interface MentionsLegalesProps {
  onBack: () => void;
}

export default function MentionsLegalesRoute({ onBack }: MentionsLegalesProps) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans py-16 px-6 lg:px-8 select-none">
      <div className="max-w-3xl mx-auto space-y-8">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 pb-6">
          <div className="flex items-center gap-3">
            <img src={sicurreLogo} alt="Sicurre Logo" className="w-10 h-10" />
            <span className="font-display font-bold text-xl text-slate-950">Sicurre</span>
          </div>
          <button
            onClick={onBack}
            className="px-4 py-2 text-xs font-bold text-slate-700 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 shadow-sm cursor-pointer transition-all"
          >
            &larr; Retour à l'accueil
          </button>
        </div>

        {/* Content */}
        <MotionDiv
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="bg-white rounded-2xl border border-slate-200/80 p-8 lg:p-10 space-y-6 shadow-sm text-left"
        >
          <h1 className="font-display font-extrabold text-3xl text-slate-950 tracking-tight mb-2">
            Mentions Légales
          </h1>
          <p className="text-xs text-slate-500">Dernière mise à jour : 18 juin 2026</p>

          <hr className="border-slate-100" />

          <section className="space-y-3">
            <h2 className="font-display font-bold text-lg text-slate-900">1. Éditeur du site</h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Le site <strong>sicurre.io</strong> est édité par la société <strong>Sicurre SAS</strong>, 
              société par actions simplifiée au capital de 15 000 euros, immatriculée au Registre du Commerce 
              et des Sociétés de Paris sous le numéro 987 654 321, dont le siège social est situé à 
              Roubaix, France.
            </p>
            <p className="text-sm text-slate-600">
              <strong>Directeur de la publication :</strong> Michael Adebayo, en sa qualité de Président de Sicurre SAS.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-bold text-lg text-slate-900">2. Hébergement</h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Le site et la plateforme applicative sont hébergés par :
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-600 space-y-1">
              <li>
                <strong>Neon Inc.</strong> (Base de données) : 2443 Fillmore St, San Francisco, CA 94115, États-Unis.
              </li>
              <li>
                <strong>Google Cloud Platform</strong> (Infrastructures de calcul et stockage) : Google Ireland Limited, 
                Gordon House, Barrow Street, Dublin 4, Irlande. (Serveurs situés en Europe, région de Paris).
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-bold text-lg text-slate-900">3. Nous contacter</h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Pour toute question ou demande de support, vous pouvez contacter nos équipes :
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-600 space-y-1">
              <li><strong>Par e-mail :</strong> contact@sicurre.com</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-bold text-lg text-slate-900">4. Propriété intellectuelle</h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              L'ensemble du contenu présent sur le site (textes, logos, animations 3D, chartes graphiques) 
              est la propriété exclusive de Sicurre SAS. Toute reproduction, modification ou distribution 
              sans accord écrit préalable est strictement interdite.
            </p>
          </section>
        </MotionDiv>

        {/* Footer */}
        <div className="text-center text-xs text-slate-400">
          © 2026 Sicurre SAS. Tous droits réservés.
        </div>
      </div>
    </div>
  );
}
