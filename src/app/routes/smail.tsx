import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { ThreatLog } from "../lib/api";
import { MailViewer } from "../components/smail/mail-viewer";

const MotionDiv = motion.div as any;

export default function SmailRoute() {
  const { t } = useTranslation();
  const [emails, setEmails] = useState<ThreatLog[]>([
    {
      id: "sim-1",
      message_id: "msg-11",
      subject: "⚠ URGET : Mise à jour de votre abonnement Simplon",
      body_preview: "Cher affilié, votre compte a expiré. Veuillez mettre à jour vos coordonnées de paiement en urgence sur le lien sous 24h.",
      verdict: "phishing",
      confidence: 0.98,
      status: "active",
      received_at: new Date().toISOString()
    },
    {
      id: "sim-2",
      message_id: "msg-22",
      subject: "Félicitations, vous avez gagné un chèque cadeau de 500€",
      body_preview: "Cliquez ici pour récupérer votre bon d'achat Amazon gratuit immédiatement.",
      verdict: "spam",
      confidence: 0.82,
      status: "active",
      received_at: new Date().toISOString()
    },
    {
      id: "sim-3",
      message_id: "msg-33",
      subject: "Rapport d'activité mensuel - Sicurre SAS",
      body_preview: "Bonjour Michael, voici le récapitulatif complet de vos statistiques de filtrage pour le mois dernier. N'hésitez pas à nous contacter.",
      verdict: "legitimate",
      confidence: 0.99,
      status: "active",
      received_at: new Date().toISOString()
    }
  ]);

  const [selectedId, setSelectedId] = useState<string>("sim-1");
  const selectedEmail = emails.find(e => e.id === selectedId);

  const reclassify = (id: string, newVerdict: "phishing" | "spam" | "legitimate") => {
    setEmails(prev => prev.map(e => {
      if (e.id === id) {
        return { ...e, verdict: newVerdict, confidence: 1.0 };
      }
      return e;
    }));
  };

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.25 }}
      className="space-y-6 h-full"
    >
      <div>
        <h2 className="text-3xl font-display font-bold text-slate-900">{t("smail.title")}</h2>
        <p className="text-sm text-slate-500 mt-1">{t("smail.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 min-h-[550px] items-stretch">
        {/* Email Inbox Sidebar */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-y-auto divide-y divide-slate-100 max-h-[550px]">
          {emails.map((e) => (
            <div
              key={e.id}
              onClick={() => setSelectedId(e.id)}
              className={`p-4 cursor-pointer transition-colors ${
                selectedId === e.id ? "bg-primary-light/40 border-l-4 border-primary" : "hover:bg-slate-50"
              }`}
            >
              <p className="text-sm font-medium text-slate-900 truncate">{e.subject}</p>
              <div className="flex justify-between items-center mt-2.5">
                <span className="text-[10px] text-slate-400 font-mono">Reçu à l'instant</span>
                <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-semibold border ${
                  e.verdict === "phishing" ? "bg-amber-50 border-amber-200 text-amber-700 font-mono" :
                  e.verdict === "spam" ? "bg-yellow-50 border-yellow-200 text-yellow-700 font-mono" :
                  "bg-green-50 border-green-200 text-green-700 font-mono"
                }`}>
                  {e.verdict}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Email Content Panel */}
        <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
          <MailViewer email={selectedEmail} onReclassify={reclassify} />
        </div>
      </div>
    </MotionDiv>
  );
}
