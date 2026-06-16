import { useTranslation } from "react-i18next";
import { ShieldCheck, ShieldAlert, MailWarning } from "lucide-react";

interface VerdictBadgeProps {
  verdict: "phishing" | "spam" | "legitimate";
  confidence: number;
}

export function VerdictBadge({ verdict, confidence }: VerdictBadgeProps) {
  const { t } = useTranslation();

  let bgClass = "bg-green-50 text-green-700 border-green-200";
  let Icon = ShieldCheck;
  let label = t("threats.badge_legitimate");

  if (verdict === "phishing") {
    bgClass = "bg-red-50 text-red-700 border-red-200";
    Icon = ShieldAlert;
    label = t("threats.badge_phishing");
  } else if (verdict === "spam") {
    bgClass = "bg-amber-50 text-amber-700 border-amber-200";
    Icon = MailWarning;
    label = t("threats.badge_spam");
  }

  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${bgClass}`}>
      <Icon className="w-3.5 h-3.5 stroke-[1.5]" />
      <span>{label}</span>
      <span className="font-mono opacity-85 ml-0.5">{(confidence * 100).toFixed(0)} %</span>
    </div>
  );
}
