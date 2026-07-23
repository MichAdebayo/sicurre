import type { ThreatLog } from "./api";

export function countTrendVerdicts(
  threats: Pick<ThreatLog, "verdict">[],
): { legitimate: number; spam: number; phishing: number } {
  return threats.reduce(
    (counts, threat) => {
      if (threat.verdict === "legitimate") counts.legitimate += 1;
      else if (threat.verdict === "spam") counts.spam += 1;
      else if (threat.verdict === "phishing" || threat.verdict === "quarantine") {
        counts.phishing += 1;
      }
      return counts;
    },
    { legitimate: 0, spam: 0, phishing: 0 },
  );
}
