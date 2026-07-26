import { ShieldCheck, ShieldAlert, MailWarning } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

interface VerdictBadgeProps {
  verdict: "phishing" | "spam" | "legitimate" | "quarantine";
  confidence: number;
  showRisk?: boolean;
}

export function VerdictBadge({ verdict, confidence, showRisk = true }: VerdictBadgeProps) {
  const { t } = useTranslation();
  let badgeStyles = "bg-safe-bg text-safe border-safe/20";
  let Icon = ShieldCheck;
  let label = t("threats.badge_legitimate");

  if (verdict === "phishing" || verdict === "quarantine") {
    badgeStyles = "bg-error/10 text-error border-error/20";
    Icon = ShieldAlert;
    label = t("threats.badge_phishing");
  } else if (verdict === "spam") {
    badgeStyles = "bg-warning-bg text-spam-text border-warning/20";
    Icon = MailWarning;
    label = t("threats.badge_spam");
  }

  const formattedRisk = t("threats.risk_value", {
    value: Math.round(confidence * 100),
  });

  return (
    <div
      className={clsx(
        "inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-body-sm font-semibold transition-all select-none whitespace-nowrap",
        badgeStyles,
      )}
    >
      <Icon className="w-4 h-4 stroke-[1.5]" />
      <span>{label}</span>
      {showRisk && (
        <span className="font-mono text-mono-data opacity-90 ml-1.5">
          {formattedRisk}
        </span>
      )}
    </div>
  );
}
