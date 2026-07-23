import React from "react";
import { Card } from "./card";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { clsx } from "clsx";

interface KPICardProps {
  title: string;
  value: string | number;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
    label?: string;
  };
  className?: string;
}

export function KPICard({ title, value, icon, trend, className }: KPICardProps) {
  return (
    <Card className={clsx("p-5 flex flex-col justify-between h-full border border-border-subtle/80 shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:border-border-subtle transition-all", className)}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-[0.1em] font-sans">
          {title}
        </span>
        {icon && (
          <div className="p-1.5 rounded-md bg-surface-low text-on-surface-variant flex items-center justify-center shrink-0">
            {icon}
          </div>
        )}
      </div>

      <div className="mt-3">
        <div className="text-3xl font-bold text-on-surface tracking-tight font-display">
          {value}
        </div>

        {trend && (
          <div className="flex items-center gap-1.5 mt-2">
            <span
              className={clsx(
                "inline-flex items-center text-xs font-semibold px-1.5 py-0.5 rounded-full",
                trend.isPositive ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-rose-500/10 text-rose-700 dark:text-rose-300",
              )}
            >
              {trend.isPositive ? (
                <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />
              ) : (
                <ArrowDownRight className="w-3.5 h-3.5 mr-0.5" />
              )}
              {trend.value}%
            </span>
            {trend.label && (
              <span className="text-xs text-on-surface-variant/60 font-sans">
                {trend.label}
              </span>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

