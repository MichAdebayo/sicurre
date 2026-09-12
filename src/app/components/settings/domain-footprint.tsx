import { useTranslation } from "react-i18next";
import { Check, CircleDashed, Eye, PenLine } from "lucide-react";
import { clsx } from "clsx";
import { useDomainShieldStatus, type DomainShieldStatus } from "../../lib/api";

const SICURRE_DMARC_MAILBOX = "dmarc@sicurre.com";

type Tone = "ok" | "todo" | "neutral";

interface Fact {
  key: string;
  label: string;
  status: string;
  tone: Tone;
}

/** The records Sicurre can manage on a zone, and the ones it only reads, from a shield status. */
export function describeDomainFootprint(
  status: DomainShieldStatus,
  t: (key: string, options?: Record<string, unknown>) => string,
): { writes: Fact[]; reads: Fact[] } {
  const policy = status.dmarc.policy;
  const enforced = policy === "reject" || policy === "quarantine";
  const reporting =
    !!status.dmarc.reporting_enabled || (status.dmarc.record ?? "").includes(SICURRE_DMARC_MAILBOX);
  const writes: Fact[] = [
    {
      key: "spf",
      label: t("settings.footprint_spf"),
      status: status.spf.valid ? t("settings.footprint_in_place") : t("settings.footprint_missing"),
      tone: status.spf.valid ? "ok" : "todo",
    },
    {
      key: "dmarc-reporting",
      label: t("settings.footprint_dmarc_reporting"),
      status: reporting ? t("settings.footprint_in_place") : t("settings.footprint_missing"),
      tone: reporting ? "ok" : "todo",
    },
    {
      key: "dmarc-policy",
      label: t("settings.footprint_dmarc_policy"),
      status: enforced ? t("settings.footprint_in_place") : t("settings.footprint_monitor_only"),
      tone: enforced ? "ok" : "todo",
    },
  ];
  const reads: Fact[] = [
    {
      key: "dkim",
      label: t("settings.footprint_dkim"),
      status: status.dkim.valid
        ? t("settings.footprint_provider_managed")
        : t("settings.footprint_absent"),
      tone: "neutral",
    },
    {
      key: "certificate",
      label: t("settings.footprint_certificate"),
      status: status.ssl.valid
        ? t("settings.footprint_days", { days: status.ssl.days_remaining })
        : t("settings.footprint_not_inspected"),
      tone: "neutral",
    },
  ];
  return { writes, reads };
}

const toneStyles: Record<Tone, string> = {
  ok: "border-safe/25 bg-safe-bg text-safe",
  todo: "border-warning/25 bg-warning-bg text-warning",
  neutral: "border-border-subtle bg-surface-low text-on-surface-variant",
};

function FactList({ title, icon, facts }: { title: string; icon: React.ReactNode; facts: Fact[] }) {
  return (
    <div className="space-y-3">
      <h4 className="flex items-center gap-2 text-body-sm font-semibold text-on-surface">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-surface-low text-primary">{icon}</span>
        {title}
      </h4>
      <ul className="divide-y divide-border-subtle/60">
        {facts.map((fact) => (
          <li key={fact.key} className="flex items-center justify-between gap-4 py-2.5 text-body-sm">
            <span className="min-w-0 text-on-surface">{fact.label}</span>
            <span
              className={clsx(
                "inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 text-body-sm font-semibold",
                toneStyles[fact.tone],
              )}
            >
              {fact.tone === "ok" && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
              {fact.tone === "todo" && <CircleDashed className="h-3.5 w-3.5" aria-hidden="true" />}
              {fact.status}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface DomainFootprintProps {
  domain: string;
}

/**
 * One connected domain: the records Sicurre can manage and the ones it only
 * reads, as facts from the cached shield status. Never triggers a refresh.
 */
export function DomainFootprint({ domain }: DomainFootprintProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useDomainShieldStatus(domain);

  return (
    <article
      aria-labelledby={`footprint-${domain}`}
      className="rounded-xl border border-border-subtle bg-surface-lowest p-6 space-y-5"
    >
      <h3 id={`footprint-${domain}`} className="font-display text-title-md font-semibold text-on-surface">
        {domain}
      </h3>
      {isLoading && !data ? (
        <p role="status" className="text-body-sm text-on-surface-variant">
          {t("settings.footprint_loading")}
        </p>
      ) : !data ? (
        <p className="text-body-sm text-on-surface-variant">{t("settings.footprint_unavailable")}</p>
      ) : (
        (() => {
          const { writes, reads } = describeDomainFootprint(data, t);
          return (
            <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
              <FactList
                title={t("settings.footprint_writes")}
                icon={<PenLine className="h-4 w-4" aria-hidden="true" />}
                facts={writes}
              />
              <FactList
                title={t("settings.footprint_reads")}
                icon={<Eye className="h-4 w-4" aria-hidden="true" />}
                facts={reads}
              />
            </div>
          );
        })()
      )}
    </article>
  );
}

interface DomainFootprintSectionProps {
  domains: { id?: string; zone_name?: string; status?: string }[];
}

/**
 * The Settings section that lists, for every connected domain, what Sicurre
 * manages on it and what it only reads. Always shown once a domain exists.
 */
export function DomainFootprintSection({ domains }: DomainFootprintSectionProps) {
  const { t } = useTranslation();
  const connected = domains.filter((domain) => domain.zone_name);
  if (connected.length === 0) return null;
  return (
    <section aria-labelledby="footprint-section-title" className="space-y-5">
      <div>
        <h2 id="footprint-section-title" className="app-h2">
          {t("settings.footprint_title")}
        </h2>
        <p className="app-body-sub mt-1 max-w-prose">{t("settings.footprint_intro")}</p>
      </div>
      <div className="space-y-4">
        {connected.map((domain) => (
          <DomainFootprint key={domain.id ?? domain.zone_name} domain={domain.zone_name ?? ""} />
        ))}
      </div>
      <p className="text-body-sm leading-relaxed text-on-surface-variant max-w-prose">
        {t("settings.footprint_disconnect_note")}
      </p>
    </section>
  );
}
