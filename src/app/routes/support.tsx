import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  Send,
  CheckCircle2,
  Mail,
  MessageSquare,
  ChevronDown,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { AppToast } from "../components/common/app-toast";
import { AuthSession, useCreateSupportRequest } from "../lib/api";

const MotionDiv = motion.div as any;

interface SupportRouteProps {
  session?: AuthSession;
}

export default function SupportRoute({ session }: SupportRouteProps) {
  const { t } = useTranslation();

  // Form states
  const [name, setName] = useState(session?.display_name || "");
  const [email, setEmail] = useState(session?.email || "");
  const [category, setCategory] = useState("dns");
  const [message, setMessage] = useState("");
  const [submittedTicket, setSubmittedTicket] = useState("");
  const [submitError, setSubmitError] = useState("");
  const createSupportRequest = useCreateSupportRequest();

  const handleSendSupport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !message.trim()) return;
    setSubmitError("");
    try {
      const ticket = await createSupportRequest.mutateAsync({
        requester_name: name.trim(),
        requester_email: email.trim(),
        category,
        message: message.trim(),
      });
      setSubmittedTicket(ticket.id);
      setMessage("");
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : t("support.submit_error"),
      );
    }
  };

  return (
    <MotionDiv
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3 }}
      className="space-y-6 animate-in fade-in duration-200"
    >
      <AppToast
        tone="error"
        message={submitError}
        visible={Boolean(submitError)}
        onClose={() => setSubmitError("")}
      />
      {/* Header */}
      <div className="pb-6 border-b border-border-subtle">
        <h1 className="app-h1">
          {t("support.title")}
        </h1>
        <p className="app-body-sub mt-1">
          {t("support.subtitle")}
        </p>
      </div>

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">

        {/* Left: Contact Form Card (8 Columns) */}
        <div className="lg:col-span-8 bg-surface-lowest border border-border-subtle rounded-2xl p-6 shadow-sm flex flex-col justify-between animate-in fade-in duration-300">
          {submittedTicket ? (
            <div className="py-16 text-center space-y-4 max-w-md mx-auto animate-in fade-in duration-300">
              <div className="w-16 h-16 bg-safe/10 text-safe rounded-full flex items-center justify-center mx-auto shadow-inner">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <div className="space-y-2">
                <h3 className="app-h2">
                  {t("support.recorded")}
                </h3>
                <p className="app-body-normal text-on-surface-variant/80 leading-relaxed font-medium">
                  {t("support.recorded_detail", { ticket: submittedTicket.slice(0, 8) })}
                </p>
              </div>
              <Button
                onClick={() => setSubmittedTicket("")}
                className="mt-6 px-5 py-2 font-bold text-xs bg-surface-low border border-border-subtle text-on-surface hover:bg-surface-container"
              >
                {t("support.send_another")}
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSendSupport} className="space-y-5">
              <div className="flex items-center gap-2 pb-2 border-b border-border-subtle/50 mb-3">
                <MessageSquare className="w-5 h-5 text-primary" />
                <h3 className="app-h2">
                  {t("support.form_title")}
                </h3>
              </div>

              {/* Name & Email Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="app-label-tiny">
                    {t("support.full_name")}
                  </label>
                  <Input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t("support.full_name_placeholder")}
                    className="bg-white border-border-subtle"
                  />
                </div>
                <div className="space-y-2">
                  <label className="app-label-tiny">
                    {t("support.email")}
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
                  {t("support.category")}
                </label>
                <div className="relative">
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full pl-3.5 pr-10 py-2 bg-white border border-border-subtle rounded-lg text-xs font-semibold text-on-surface focus:outline-none focus:border-primary cursor-pointer shadow-sm h-10 appearance-none"
                  >
                    <option value="incident">
                      {t("support.category_incident")}
                    </option>
                    <option value="dns">
                      {t("support.category_dns")}
                    </option>
                    <option value="billing">
                      {t("support.category_billing")}
                    </option>
                    <option value="feedback">
                      {t("support.category_feedback")}
                    </option>
                    <option value="other">
                      {t("support.category_other")}
                    </option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-on-surface-variant pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2" />
                </div>
              </div>

              {/* Message Content */}
              <div className="space-y-2">
                <label className="app-label-tiny">
                  {t("support.message")}
                </label>
                <textarea
                  required
                  rows={5}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={t("support.message_placeholder")}
                  className="w-full px-3.5 py-2.5 bg-white border border-border-subtle rounded-xl text-xs text-on-surface font-medium placeholder:text-on-surface-variant/40 focus:outline-none focus:border-primary shadow-sm min-h-[120px]"
                />
              </div>

              {/* Submit Action */}
              <div className="pt-3 border-t border-border-subtle/50 flex justify-end">
                <Button
                  type="submit"
                  disabled={createSupportRequest.isPending}
                  className="flex items-center gap-2 cursor-pointer bg-[#2e6bb5] hover:bg-[#23589b] text-white border-none text-xs font-bold rounded-lg px-5 py-2 h-10 shadow-sm"
                >
                  {createSupportRequest.isPending ? (
                    <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  <span>{t("support.submit")}</span>
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
            <h3 className="app-h3">{t("support.direct_contact")}</h3>
            <p className="app-body-sub leading-relaxed">
              {t("support.direct_contact_desc")}
            </p>
          </div>
        </div>
      </div>
    </MotionDiv>
  );
}
