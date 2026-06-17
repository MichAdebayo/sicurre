import { ShieldCheck, ShieldAlert, MailWarning } from "lucide-react";
import { clsx } from "clsx";

interface VerdictBadgeProps {
  verdict: "phishing" | "spam" | "legitimate";
  confidence: number;
}

export function VerdictBadge({ verdict, confidence }: VerdictBadgeProps) {
  let badgeStyles = "bg-safe-bg text-safe border-safe/20";
  let Icon = ShieldCheck;
  let label = "Légitime";

  if (verdict === "phishing") {
    badgeStyles = "bg-error/10 text-error border-error/20";
    Icon = ShieldAlert;
    label = "Phishing";
  } else if (verdict === "spam") {
    badgeStyles = "bg-warning-bg text-warning border-warning/20";
    Icon = MailWarning;
    label = "Spam";
  }

  // French format: space before percent symbol
  const formattedConfidence = `${(confidence * 100).toFixed(0)} %`;

  return (
    <div
      className={clsx(
        "inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-body-sm font-semibold transition-all select-none",
        badgeStyles,
      )}
    >
      <Icon className="w-4 h-4 stroke-[1.5]" />
      <span>{label}</span>
      <span className="font-mono text-mono-data opacity-90 ml-1.5">
        {formattedConfidence}
      </span>
    </div>
  );
}
