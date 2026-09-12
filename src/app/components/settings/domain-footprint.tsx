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

/** The records Sicurre writes on a zone, and the ones it only reads, from a shield status. */
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
    <div className="space-y-2">
      <h4 className="flex items-center gap-1.5 text-xs font-semibold text-on-surface-variant">
        {icon}
        {title}
      </h4>
      <ul className="space-y-1.5">
        {facts.map((fact) => (
          <li key={fact.key} className="flex items-center justify-between gap-3 text-xs">
            <span className="min-w-0 text-on-surface">{fact.label}</span>
            <span
              className={clsx(
                "inline-flex shrink-0 items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-semibold",
                toneStyles[fact.tone],
              )}
            >
              {fact.tone === "ok" && <Check className="h-3 w-3" aria-hidden="true" />}
              {fact.tone === "todo" && <CircleDashed className="h-3 w-3" aria-hidden="true" />}
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
  id: string;
}

/**
 * What Sicurre has written on a connected domain and what it only reads,
 * shown under the domain's row in Settings. Reads the cached shield status;
 * never triggers a refresh.
 */
export function DomainFootprint({ domain, id }: DomainFootprintProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useDomainShieldStatus(domain);

  return (
    <div
      id={id}
      className="rounded-xl border border-border-subtle bg-surface-lowest p-4 space-y-4"
      aria-live="polite"
    >
      <p className="text-sm font-semibold text-on-surface">
        {t("settings.footprint_title", { domain })}
      </p>
      {isLoading && !data ? (
        <p role="status" className="text-xs text-on-surface-variant">
          {t("settings.footprint_loading")}
        </p>
      ) : !data ? (
        <p className="text-xs text-on-surface-variant">{t("settings.footprint_unavailable")}</p>
      ) : (
        (() => {
          const { writes, reads } = describeDomainFootprint(data, t);
          return (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <FactList
                title={t("settings.footprint_writes")}
                icon={<PenLine className="h-3.5 w-3.5" aria-hidden="true" />}
                facts={writes}
              />
              <FactList
                title={t("settings.footprint_reads")}
                icon={<Eye className="h-3.5 w-3.5" aria-hidden="true" />}
                facts={reads}
              />
            </div>
          );
        })()
      )}
      <p className="text-[11px] leading-relaxed text-on-surface-variant">
        {t("settings.footprint_disconnect_note")}
      </p>
    </div>
  );
}
