import { clsx } from "clsx";

interface VerdictBadgeProps {
  verdict: "phishing" | "spam" | "legitimate" | "quarantine";
  confidence: number;
  showRisk?: boolean;
}

export function VerdictBadge({ verdict, confidence, showRisk = true }: VerdictBadgeProps) {
  let badgeStyles = "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 border-emerald-500/20";
  let dotStyles = "bg-emerald-500";
  let label = "Légitime";

  if (verdict === "phishing" || verdict === "quarantine") {
    badgeStyles = "bg-rose-500/10 text-rose-800 dark:text-rose-300 border-rose-500/20";
    dotStyles = "bg-rose-500";
    label = "Phishing";
  } else if (verdict === "spam") {
    badgeStyles = "bg-amber-500/10 text-amber-900 dark:text-amber-300 border-amber-500/20";
    dotStyles = "bg-amber-500";
    label = "Spam";
  }

  const formattedRisk = `${Math.round(confidence * 100)}%`;

  return (
    <div
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-xs font-medium transition-all select-none whitespace-nowrap",
        badgeStyles,
      )}
    >
      <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", dotStyles)} />
      <span>{label}</span>
      {showRisk && (
        <span className="font-mono text-[11px] opacity-75 ml-0.5">
          {formattedRisk}
        </span>
      )}
    </div>
  );
}

