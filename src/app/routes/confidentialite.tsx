import { motion } from "framer-motion";
import sicurreLogo from "../assets/sicurre.svg";

const MotionDiv = motion.div as any;

interface ConfidentialiteProps {
  onBack: () => void;
}

export default function ConfidentialiteRoute({ onBack }: ConfidentialiteProps) {
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
              Politique de Confidentialité
            </h1>
            <p className="text-xs text-slate-400 font-medium">Dernière mise à jour : 18 juin 2026</p>
          </div>

          <hr className="border-white/10" />

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">1. Engagements RGPD et Souveraineté</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Chez Sicurre, nous traitons la sécurité et la confidentialité de vos e-mails avec la plus grande rigueur.
              En conformité totale avec le Règlement Général sur la Protection des Données (RGPD), toutes les analyses
              d'inférence de phishing sont exécutées sur des infrastructures souveraines situées en France.
              <strong className="text-white"> Aucun e-mail n'est partagé avec des tiers ou utilisé pour entraîner des modèles publics.</strong>
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">2. Cloudflare Email Routing & autorisations</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Pour protéger un domaine, Sicurre configure Cloudflare Email Routing et un Email Worker qui transmet les e-mails entrants
              à notre API de scan avant livraison. L'application utilise un jeton Cloudflare restreint au domaine choisi et aux permissions
              nécessaires pour gérer le routage, les enregistrements DNS liés à l'e-mail et le Worker.
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-400 space-y-2">
              <li>
                <strong className="text-white">DNS zone read/edit</strong> : utilisé pour vérifier et créer les enregistrements MX/TXT nécessaires au routage.
              </li>
              <li>
                <strong className="text-white">Email Routing read/edit</strong> : utilisé pour activer les destinations et règles de protection du domaine.
              </li>
              <li>
                <strong className="text-white">Workers read/edit</strong> : utilisé pour déployer le Worker qui appelle Sicurre avec un secret partagé.
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">3. Politique stricte de Non-Stockage des E-mails</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Par défaut, <strong className="text-white">Sicurre ne stocke jamais le corps ou le contenu de vos e-mails</strong> dans ses bases de données.
              Seules les métadonnées techniques indispensables à votre journal de sécurité sont enregistrées :
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-400 space-y-1.5">
              <li>Adresse de l'expéditeur et du destinataire</li>
              <li>Objet (sujet) du message</li>
              <li>Date et heure de réception</li>
              <li>Verdict de classification (Légitime, Indésirable, Phishing) et score de confiance associé</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">4. Masquage automatique des Données Personnelles (PII)</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Toutes les données à caractère personnel qui transitent ou sont inspectées par le démon de détection sont
              systématiquement anonymisées. Les adresses e-mails secondaires, numéros de téléphone, numéros de sécurité
              sociale, SIRET ou IBAN sont immédiatement transformés en balises de métadonnées génériques
              (ex: <code className="text-primary bg-primary/10 px-1.5 py-0.5 rounded border border-primary/20">[EMAIL]</code>, <code className="text-primary bg-primary/10 px-1.5 py-0.5 rounded border border-primary/20">[PHONE]</code>, <code className="text-primary bg-primary/10 px-1.5 py-0.5 rounded border border-primary/20">[IBAN]</code>) avant tout archivage dans votre tableau de bord.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-medium text-lg text-slate-200">5. Révocation de vos autorisations</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Vous pouvez à tout moment couper la protection Sicurre depuis Domain Shield en supprimant l'intégration Cloudflare,
              ou depuis Cloudflare en révoquant le jeton API et en désactivant le routage/Worker associé au domaine.
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
