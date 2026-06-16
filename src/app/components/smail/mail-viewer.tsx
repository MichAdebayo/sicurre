import { useTranslation } from "react-i18next";
import { ThreatLog } from "../../lib/api";
import { VerdictBadge } from "../threats/verdict-badge";
import { Button } from "../ui/button";

interface MailViewerProps {
  email: ThreatLog | undefined;
  onReclassify: (id: string, newVerdict: "phishing" | "spam" | "legitimate") => void;
}

export function MailViewer({ email, onReclassify }: MailViewerProps) {
  const { t } = useTranslation();

  if (!email) {
    return (
      <div className="flex h-full items-center justify-center text-center text-sm text-slate-400 py-12">
        {t("smail.empty_inbox")}
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col justify-between p-6">
      <div className="space-y-6 flex-1 flex flex-col">
        {/* Header Metadata */}
        <div className="border-b border-slate-100 pb-4">
          <h3 className="text-base font-semibold text-slate-900 font-display">{email.subject}</h3>
          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs text-slate-500">Expéditeur: inconnu</span>
            <VerdictBadge verdict={email.verdict} confidence={email.confidence} />
          </div>
        </div>

        {/* Mail Text Body */}
        <div className="flex-1 text-sm text-slate-700 bg-slate-50 border border-slate-100 rounded-lg p-5 leading-relaxed min-h-[150px] font-sans">
          {email.body_preview}
        </div>

        {/* Classification Status Explanation */}
        <div className="p-3 bg-slate-50 rounded-lg flex items-center gap-2 border border-slate-100">
          <span className="text-xs font-semibold text-slate-500">Classification Sicurre:</span>
          <span className="text-xs text-slate-700">
            {email.verdict === "phishing"
              ? t("smail.verdict_phishing_desc")
              : email.verdict === "spam"
              ? t("smail.verdict_spam_desc")
              : t("smail.verdict_safe_desc")}
          </span>
        </div>
      </div>

      {/* Remediation Action Buttons */}
      <div className="flex gap-3 pt-4 border-t border-slate-100 mt-4">
        <Button
          variant="secondary"
          className="flex-1 bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-700 font-semibold rounded-lg text-xs"
          onClick={() => onReclassify(email.id, "phishing")}
        >
          {t("smail.report_phishing")}
        </Button>
        <Button
          variant="secondary"
          className="flex-1 bg-yellow-50 hover:bg-yellow-100 border border-yellow-200 text-yellow-700 font-semibold rounded-lg text-xs"
          onClick={() => onReclassify(email.id, "spam")}
        >
          {t("smail.report_spam")}
        </Button>
        <Button
          variant="safe"
          className="flex-1 font-semibold rounded-lg text-xs"
          onClick={() => onReclassify(email.id, "legitimate")}
        >
          {t("smail.mark_safe")}
        </Button>
      </div>
    </div>
  );
}
