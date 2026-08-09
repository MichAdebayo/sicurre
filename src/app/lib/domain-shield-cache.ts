interface CachedDomainShieldStatus {
  reputation_score?: number;
  score_grade?: string;
  blacklists?: { error?: string | null };
}

export function isReusableDomainShieldStatus(status: CachedDomainShieldStatus): boolean {
  return typeof status.reputation_score === "number"
    && Boolean(status.score_grade)
    && !status.blacklists?.error;
}
