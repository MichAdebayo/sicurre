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
    <Card className={clsx("p-6 flex flex-col justify-between h-full hover:shadow-md transition-shadow", className)}>
      <div className="flex items-start justify-between">
        <span className="text-label-caps text-on-surface-variant font-semibold tracking-wider">
          {title}
        </span>
        {icon && (
          <div className="p-2 rounded-lg bg-surface-low text-primary flex items-center justify-center">
            {icon}
          </div>
        )}
      </div>

      <div className="mt-4">
        <div className="text-headline-lg font-bold text-on-surface tracking-tight font-display">
          {value}
        </div>

        {trend && (
          <div className="flex items-center gap-1.5 mt-2">
            <span
              className={clsx(
                "inline-flex items-center text-body-sm font-semibold",
                trend.isPositive ? "text-safe" : "text-error",
              )}
            >
              {trend.isPositive ? (
                <ArrowUpRight className="w-4 h-4 mr-0.5" />
              ) : (
                <ArrowDownRight className="w-4 h-4 mr-0.5" />
              )}
              {trend.value}%
            </span>
            {trend.label && (
              <span className="text-body-sm text-on-surface-variant/60">
                {trend.label}
              </span>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
