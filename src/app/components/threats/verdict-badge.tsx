import { ShieldCheck, ShieldAlert, MailWarning } from "lucide-react";
import { clsx } from "clsx";

interface VerdictBadgeProps {
  verdict: "phishing" | "spam" | "legitimate" | "quarantine";
  confidence: number;
  showRisk?: boolean;
}

export function VerdictBadge({ verdict, confidence, showRisk = true }: VerdictBadgeProps) {
  let badgeStyles = "bg-safe-bg text-safe border-safe/20";
  let Icon = ShieldCheck;
  let label = "Légitime";

  if (verdict === "phishing" || verdict === "quarantine") {
    badgeStyles = "bg-error/10 text-error border-error/20";
    Icon = ShieldAlert;
    label = "Phishing";
  } else if (verdict === "spam") {
    badgeStyles = "bg-warning-bg text-spam-text border-warning/20";
    Icon = MailWarning;
    label = "Spam";
  }

  const formattedRisk = `Risque ${Math.round(confidence * 100)} %`;

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
