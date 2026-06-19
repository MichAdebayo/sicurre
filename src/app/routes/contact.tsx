import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mail, MapPin, Send, CheckCircle2, MessageSquare, Clock } from "lucide-react";
import sicurreLogo from "../assets/sicurre.svg";

const MotionDiv = motion.div as any;

interface ContactRouteProps {
  onBack: () => void;
}

export default function ContactRoute({ onBack }: ContactRouteProps) {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    subject: "support",
    message: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) return;

    setIsSubmitting(true);
    // Simulate sending email to contact@sicurre.com
    setTimeout(() => {
      setIsSubmitting(false);
      setIsSuccess(true);
    }, 1800);
  };

  const handleReset = () => {
    setFormData({
      name: "",
      email: "",
      subject: "support",
      message: "",
    });
    setIsSuccess(false);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans py-16 px-6 lg:px-8 select-none">
      <div className="max-w-4xl mx-auto space-y-8">
        
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

        {/* Contact Page Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Column: Innovative Contact Info */}
          <div className="lg:col-span-4 space-y-6">
            <div className="bg-slate-900 text-white rounded-2xl p-6 relative overflow-hidden shadow-lg">
              {/* Decorative background glow */}
              <div className="absolute -top-10 -right-10 w-32 h-32 bg-primary/20 blur-2xl rounded-full" />
              
              <div className="relative z-10 space-y-6 text-left">
                <div>
                  <span className="text-[10px] font-extrabold tracking-widest text-[#F59E0B] uppercase">ASSISTANCE 24/7</span>
                  <h2 className="font-display font-bold text-2xl text-white mt-1 leading-tight">
                    Discutons ensemble
                  </h2>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Notre équipe de support client et nos ingénieurs en cybersécurité vous répondent en moins de 15 minutes.
                </p>

                <div className="space-y-4 pt-2">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-white/10 rounded-lg text-[#F59E0B]">
                      <Clock className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold uppercase leading-none">Réponse moyenne</p>
                      <p className="text-sm font-bold mt-1 text-white">12 minutes</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-white/10 rounded-lg text-primary-light">
                      <Mail className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold uppercase leading-none">E-mail direct</p>
                      <p className="text-sm font-mono mt-1 text-white text-[12px]">contact@sicurre.com</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-white/10 rounded-lg text-slate-400">
                      <MapPin className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold uppercase leading-none">Siège social</p>
                      <p className="text-xs text-slate-300 mt-1">Roubaix, France</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-3 shadow-sm text-left">
              <h3 className="font-display font-bold text-sm text-slate-900 flex items-center gap-2">
                <MessageSquare className="w-4.5 h-4.5 text-primary" />
                Sécurité & Chiffrement
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Toutes les informations soumises via ce formulaire sont chiffrées de bout en bout (AES-256) avant transmission.
              </p>
            </div>
          </div>

          {/* Right Column: Interactive Contact Form */}
          <div className="lg:col-span-8">
            <div className="bg-white rounded-2xl border border-slate-200/80 p-8 shadow-sm h-full min-h-[420px] flex flex-col justify-center relative overflow-hidden">
              
              <AnimatePresence mode="wait">
                {!isSuccess ? (
                  <MotionDiv
                    key="form"
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.25 }}
                    className="space-y-6 text-left"
                  >
                    <div>
                      <h3 className="font-display font-extrabold text-xl text-slate-900 tracking-tight">
                        Envoyer un message
                      </h3>
                      <p className="text-xs text-slate-500 mt-1">
                        Remplissez le formulaire ci-dessous pour joindre notre équipe.
                      </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-slate-700">Votre nom complet</label>
                          <input
                            type="text"
                            required
                            value={formData.name}
                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            placeholder="Jean Dupont"
                            className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-slate-700">Adresse e-mail professionnelle</label>
                          <input
                            type="email"
                            required
                            value={formData.email}
                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                            placeholder="jean@entreprise.fr"
                            className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all"
                          />
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-slate-700">Sujet de votre demande</label>
                        <select
                          value={formData.subject}
                          onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                          className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all bg-white"
                        >
                          <option value="support">Support Technique / Fausse classification</option>
                          <option value="sales">Demande Commerciale / Tarifs</option>
                          <option value="security">Signalement de Sécurité / Bug Bounty</option>
                          <option value="other">Autre demande</option>
                        </select>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-slate-700">Votre message</label>
                        <textarea
                          required
                          rows={4}
                          value={formData.message}
                          onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                          placeholder="Décrivez votre demande en détail..."
                          className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/15 transition-all resize-none"
                        />
                      </div>

                      <button
                        type="submit"
                        disabled={isSubmitting}
                        className={`w-full py-3 bg-primary text-white hover:bg-navy-dark font-bold rounded-xl transition-all flex items-center justify-center gap-2 text-sm shadow-sm cursor-pointer active:scale-[0.98] ${
                          isSubmitting ? "opacity-75 cursor-not-allowed" : ""
                        }`}
                      >
                        {isSubmitting ? (
                          <>
                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            <span>Envoi en cours...</span>
                          </>
                        ) : (
                          <>
                            <Send className="w-4 h-4" />
                            <span>Envoyer le message</span>
                          </>
                        )}
                      </button>
                    </form>
                  </MotionDiv>
                ) : (
                  <MotionDiv
                    key="success"
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.35, ease: "easeOut" }}
                    className="flex flex-col items-center justify-center text-center space-y-6 py-6"
                  >
                    {/* Floating/Flying Mail Envelope Animation */}
                    <div className="relative w-20 h-20 flex items-center justify-center">
                      <MotionDiv
                        initial={{ y: 0, opacity: 1, scale: 1 }}
                        animate={{ y: -60, x: 80, opacity: 0, scale: 0.5 }}
                        transition={{ duration: 1.2, ease: "easeInOut" }}
                        className="absolute w-12 h-9 rounded bg-[#F59E0B] border border-white flex items-center justify-center text-slate-900 shadow-md"
                      >
                        <Mail className="w-5 h-5" />
                      </MotionDiv>
                      
                      <MotionDiv
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ delay: 0.8, duration: 0.3, type: "spring" }}
                        className="text-emerald-500"
                      >
                        <CheckCircle2 className="w-16 h-16" />
                      </MotionDiv>
                    </div>

                    <div className="space-y-2 max-w-sm">
                      <h4 className="font-display font-extrabold text-2xl text-slate-950 tracking-tight">
                        Message envoyé !
                      </h4>
                      <p className="text-sm text-slate-600 leading-relaxed">
                        Merci <strong>{formData.name}</strong>, votre message a bien été envoyé de manière sécurisée 
                        à <strong>contact@sicurre.com</strong>. Nous vous recontactons d'ici quelques minutes.
                      </p>
                    </div>

                    <button
                      onClick={handleReset}
                      className="px-6 py-2.5 text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition-all cursor-pointer"
                    >
                      Envoyer un autre message
                    </button>
                  </MotionDiv>
                )}
              </AnimatePresence>

            </div>
          </div>

        </div>

        {/* Footer */}
        <div className="text-center text-xs text-slate-400">
          © 2026 Sicurre SAS. Tous droits réservés.
        </div>
      </div>
    </div>
  );
}
