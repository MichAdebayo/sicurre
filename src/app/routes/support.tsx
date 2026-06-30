import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  Send,
  CheckCircle2,
  Cpu,
  Mail,
  MessageSquare,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { AuthSession } from "../lib/api";

const MotionDiv = motion.div as any;

interface SupportRouteProps {
  session?: AuthSession;
}

export default function SupportRoute({ session }: SupportRouteProps) {
  const { t, i18n } = useTranslation();
  const isFR = i18n.language === "fr";

  // Form states
  const [name, setName] = useState(session?.display_name || "");
  const [email, setEmail] = useState(session?.email || "");
  const [category, setCategory] = useState("dns");
  const [message, setMessage] = useState("");
  const [isPending, setIsPending] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSendSupport = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !message.trim()) return;

    setIsPending(true);
    // Simulate sending support request to support@sicurre.com
    setTimeout(() => {
      setIsPending(false);
      setSubmitted(true);
      setMessage("");
    }, 1200);
  };

  const systemNodes = [
    { name: isFR ? "Pare-feu Global" : "Global Firewall", status: isFR ? "Opérationnel" : "Operational", metric: "Uptime", value: "99.99 %" },
    { name: isFR ? "Modèle d'Analyse" : "Analysis Model", status: isFR ? "Opérationnel" : "Operational", metric: isFR ? "Latence" : "Latency", value: "82 ms" },
    { name: isFR ? "Collecteur de Logs" : "Log Collector", status: isFR ? "Opérationnel" : "Operational", metric: isFR ? "Débit" : "Throughput", value: "14 req/s" },
  ];

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-6 animate-in fade-in duration-200"
    >
      {/* Header */}
      <div className="pb-6 border-b border-border-subtle">
        <h1 className="app-h1">
          {isFR ? "Support & Assistance Technique" : "Technical Support & Help"}
        </h1>
        <p className="app-body-sub mt-1">
          {isFR
            ? "Transmettez votre demande d'assistance directement à notre équipe technique"
            : "Submit your technical support request directly to our security response team"}
        </p>
      </div>

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
        
        {/* Left: Contact Form Card (8 Columns) */}
        <div className="lg:col-span-8 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between animate-in fade-in duration-300">
          {submitted ? (
            <div className="py-16 text-center space-y-4 max-w-md mx-auto animate-in fade-in duration-300">
              <div className="w-16 h-16 bg-safe/10 text-safe rounded-full flex items-center justify-center mx-auto shadow-inner">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <div className="space-y-2">
                <h3 className="app-h2">
                  {isFR ? "Message Envoyé avec Succès !" : "Support Ticket Submitted!"}
                </h3>
                <p className="app-body-normal text-on-surface-variant/80 leading-relaxed font-medium">
                  {isFR
                    ? "Votre message a été transmis avec succès à support@sicurre.com. Un technicien prendra contact avec vous sous un délai moyen de 2 heures."
                    : "Your message was successfully transmitted to support@sicurre.com. An engineer will follow up with you within 2 hours."}
                </p>
              </div>
              <Button
                onClick={() => setSubmitted(false)}
                className="mt-6 px-5 py-2 font-bold text-xs bg-surface-low border border-border-subtle text-on-surface hover:bg-surface-container"
              >
                {isFR ? "Envoyer un autre message" : "Send another message"}
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSendSupport} className="space-y-5">
              <div className="flex items-center gap-2 pb-2 border-b border-border-subtle/50 mb-3">
                <MessageSquare className="w-5 h-5 text-primary" />
                <h3 className="app-h2">
                  {isFR ? "Formulaire de Contact" : "Contact Support Form"}
                </h3>
              </div>

              {/* Name & Email Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="app-label-tiny">
                    {isFR ? "Nom complet" : "Full Name"}
                  </label>
                  <Input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={isFR ? "Ex: Jean Dupont" : "e.g. John Doe"}
                    className="bg-white border-border-subtle"
                  />
                </div>
                <div className="space-y-2">
                  <label className="app-label-tiny">
                    {isFR ? "Adresse e-mail" : "Email Address"}
                  </label>
                  <Input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="jean@entreprise.com"
                    className="bg-white border-border-subtle"
                  />
                </div>
              </div>

              {/* Purpose Category Dropdown */}
              <div className="space-y-2">
                <label className="app-label-tiny">
                  {isFR ? "Motif de la demande" : "Request Category"}
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 bg-white border border-border-subtle rounded-lg text-xs font-semibold text-on-surface focus:outline-none focus:border-primary cursor-pointer shadow-sm h-10"
                >
                  <option value="incident">
                    {isFR ? "Incident de sécurité / Phishing suspect" : "Security Incident / Phishing Suspicion"}
                  </option>
                  <option value="dns">
                    {isFR ? "Configuration DNS & Cloudflare" : "DNS & Cloudflare Setup"}
                  </option>
                  <option value="billing">
                    {isFR ? "Facturation et abonnements" : "Billing & Subscription"}
                  </option>
                  <option value="feedback">
                    {isFR ? "Suggestions / Retour d'expérience" : "Feedback & Suggestions"}
                  </option>
                  <option value="other">
                    {isFR ? "Autre demande d'assistance" : "Other Support Inquiry"}
                  </option>
                </select>
              </div>

              {/* Message Content */}
              <div className="space-y-2">
                <label className="app-label-tiny">
                  {isFR ? "Votre Message" : "Your Message"}
                </label>
                <textarea
                  required
                  rows={5}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={isFR ? "Décrivez précisément votre problème technique..." : "Describe your technical issue in detail..."}
                  className="w-full px-3.5 py-2.5 bg-white border border-border-subtle rounded-xl text-xs text-on-surface font-medium placeholder:text-on-surface-variant/40 focus:outline-none focus:border-primary shadow-sm min-h-[120px]"
                />
              </div>

              {/* Submit Action */}
              <div className="pt-3 border-t border-border-subtle/50 flex justify-end">
                <Button
                  type="submit"
                  disabled={isPending}
                  className="flex items-center gap-2 cursor-pointer bg-[#2e6bb5] hover:bg-[#23589b] text-white border-none text-xs font-bold rounded-lg px-5 py-2 h-10 shadow-sm"
                >
                  {isPending ? (
                    <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  <span>{isFR ? "Envoyer le message" : "Send Support Request"}</span>
                </Button>
              </div>
            </form>
          )}
        </div>

        {/* Right: Technical Metadata & status (4 Columns) */}
        <div className="lg:col-span-4 space-y-6 animate-in fade-in duration-300">
          {/* Support Email Card */}
          <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-5 shadow-sm space-y-3">
            <div className="p-3 bg-primary/[0.06] text-primary border border-primary/10 rounded-xl w-fit">
              <Mail className="w-5 h-5" />
            </div>
            <h3 className="app-h3">{isFR ? "Adresse Directe" : "Direct Contact"}</h3>
            <p className="app-body-sub leading-relaxed">
              {isFR
                ? "Vous pouvez également envoyer un email directement à support@sicurre.com à tout moment."
                : "You can also reach us directly via email at support@sicurre.com."}
            </p>
          </div>

          {/* System Status Nodes */}
          <div className="bg-surface-lowest border border-border-subtle rounded-2xl p-5 shadow-sm">
            <div className="flex items-center gap-2 pb-3 border-b border-border-subtle/50 mb-4">
              <Cpu className="w-4 h-4 text-primary" />
              <h3 className="app-h3">{isFR ? "Statuts du Système" : "System Status Nodes"}</h3>
            </div>
            <div className="space-y-3">
              {systemNodes.map((node, idx) => (
                <div key={idx} className="p-3 bg-surface-low border border-border-subtle/60 rounded-xl space-y-2 select-none">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-on-surface">{node.name}</span>
                    <span className="text-[10px] text-safe font-bold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">{node.status}</span>
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-on-surface-variant font-bold">
                    <span>{node.metric}</span>
                    <span className="font-mono text-primary">{node.value}</span>
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
