import { useState } from "react";
import { motion } from "framer-motion";
import { Mail, MapPin, Send, MessageSquare, Clock, Home } from "lucide-react";
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) return;
    const subject = encodeURIComponent(`[Sicurre - ${formData.subject}] ${formData.name}`);
    const body = encodeURIComponent(
      `Nom: ${formData.name}\nE-mail: ${formData.email}\n\n${formData.message}`,
    );
    window.location.href = `mailto:contact@sicurre.com?subject=${subject}&body=${body}`;
  };

  return (
    <div className="min-h-screen bg-black text-white font-sans py-16 px-6 lg:px-8 select-none relative overflow-x-hidden">
      {/* Background glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-5xl h-96 pointer-events-none" style={{
        background: "radial-gradient(ellipse 60% 50% at 50% 0%, rgba(74,144,217,0.08) 0%, transparent 70%)",
      }} />

      <div className="max-w-4xl mx-auto space-y-8 relative z-10">

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

        {/* Contact Page Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

          {/* Left Column: Contact Info Glass Card */}
          <div className="lg:col-span-4 space-y-6">
            <div
              style={{
                background: "rgba(255, 255, 255, 0.025)",
                backdropFilter: "blur(24px)",
                WebkitBackdropFilter: "blur(24px)",
                border: "1px solid rgba(255, 255, 255, 0.09)",
              }}
              className="rounded-2xl p-6 relative overflow-hidden shadow-2xl space-y-6 text-left"
            >
              {/* Decorative background glow */}
              <div className="absolute -top-10 -right-10 w-32 h-32 bg-primary/20 blur-2xl rounded-full" />

              <div className="relative z-10 space-y-6">
                <div>
                  <span className="text-[10px] font-extrabold tracking-widest text-[#F59E0B] uppercase">CONTACT SICURRE</span>
                  <h2 className="font-display font-medium text-2xl text-slate-100 mt-1 leading-tight">
                    Discutons ensemble
                  </h2>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Préparez votre message ici, puis envoyez-le depuis votre messagerie habituelle.
                </p>

                <div className="space-y-4 pt-2">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-white/10 rounded-lg text-[#F59E0B]">
                      <Clock className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold uppercase leading-none">Canal</p>
                      <p className="text-sm font-bold mt-1 text-white">E-mail</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-white/10 rounded-lg text-primary">
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

            <div
              style={{
                background: "rgba(255, 255, 255, 0.02)",
                backdropFilter: "blur(20px)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
              }}
              className="rounded-2xl p-5 space-y-3 text-left"
            >
              <h3 className="font-display font-medium text-sm text-slate-200 flex items-center gap-2">
                <MessageSquare className="w-4.5 h-4.5 text-primary" />
                Sécurité & Chiffrement
              </h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Cette page n’enregistre pas votre message. Votre application de messagerie prend en charge l’envoi.
              </p>
            </div>
          </div>

          {/* Right Column: Interactive Contact Form Glass Card */}
          <div className="lg:col-span-8">
            <div
              style={{
                background: "rgba(255, 255, 255, 0.02)",
                backdropFilter: "blur(24px)",
                WebkitBackdropFilter: "blur(24px)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
              }}
              className="rounded-2xl p-8 shadow-2xl h-full min-h-[420px] flex flex-col justify-center relative overflow-hidden"
            >
                  <MotionDiv
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.25 }}
                    className="space-y-6 text-left"
                  >
                    <div>
                      <h3 className="font-display font-medium text-xl text-slate-100 tracking-tight">
                        Envoyer un message
                      </h3>
                      <p className="text-xs text-slate-400 mt-1">
                        Remplissez le formulaire ci-dessous pour joindre notre équipe.
                      </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <label className="text-xs font-medium text-slate-300">Votre nom complet</label>
                          <input
                            type="text"
                            required
                            value={formData.name}
                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            placeholder="Jean Dupont"
                            className="w-full px-4 py-2.5 rounded-xl border border-white/10 bg-white/[0.04] text-white text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all placeholder:text-white/20"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-medium text-slate-300">Adresse e-mail professionnelle</label>
                          <input
                            type="email"
                            required
                            value={formData.email}
                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                            placeholder="jean@entreprise.fr"
                            className="w-full px-4 py-2.5 rounded-xl border border-white/10 bg-white/[0.04] text-white text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all placeholder:text-white/20"
                          />
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-300">Sujet de votre demande</label>
                        <select
                          value={formData.subject}
                          onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                          className="w-full px-4 py-2.5 rounded-xl border border-white/10 bg-[#121624] text-white text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all"
                        >
                          <option value="support">Support Technique / Fausse classification</option>
                          <option value="sales">Demande Commerciale / Tarifs</option>
                          <option value="security">Signalement de Sécurité / Bug Bounty</option>
                          <option value="other">Autre demande</option>
                        </select>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-300">Votre message</label>
                        <textarea
                          required
                          rows={4}
                          value={formData.message}
                          onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                          placeholder="Décrivez votre demande en détail..."
                          className="w-full px-4 py-2.5 rounded-xl border border-white/10 bg-white/[0.04] text-white text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all resize-none placeholder:text-white/20"
                        />
                      </div>

                      <button
                        type="submit"
                        className="w-full py-3.5 bg-navy-dark text-white hover:brightness-95 font-semibold rounded-xl transition-all flex items-center justify-center gap-2 text-sm shadow-md shadow-primary/20 cursor-pointer active:scale-[0.98]"
                      >
                        <Send className="w-4 h-4" />
                        <span>Ouvrir ma messagerie</span>
                      </button>
                    </form>
                  </MotionDiv>

            </div>
          </div>

        </div>

        {/* Footer */}
        <div className="text-center text-xs text-slate-500">
          © 2026 Sicurre. Tous droits réservés.
        </div>
      </div>
    </div>
  );
}
