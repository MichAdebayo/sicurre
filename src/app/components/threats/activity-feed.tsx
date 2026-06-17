import React from "react";
import { clsx } from "clsx";
import { Info, AlertTriangle, AlertOctagon, CheckCircle2 } from "lucide-react";

export interface ActivityItem {
  id: string;
  type: "info" | "warning" | "critical" | "success";
  title: string;
  description: string;
  timestamp: string;
}

interface ActivityFeedProps {
  activities: ActivityItem[];
  className?: string;
}

const icons = {
  info: Info,
  warning: AlertTriangle,
  critical: AlertOctagon,
  success: CheckCircle2,
};

const borderColors = {
  info: "border-l-primary",
  warning: "border-l-secondary",
  critical: "border-l-error",
  success: "border-l-safe",
};

const bgColors = {
  info: "bg-primary/5",
  warning: "bg-secondary/5",
  critical: "bg-error/5",
  success: "bg-safe/5",
};

const iconColors = {
  info: "text-primary",
  warning: "text-secondary",
  critical: "text-error",
  success: "text-safe",
};

export function ActivityFeed({ activities, className }: ActivityFeedProps) {
  return (
    <div className={clsx("flex flex-col gap-3", className)}>
      {activities.length > 0 ? (
        activities.map((item) => {
          const Icon = icons[item.type];
          return (
            <div
              key={item.id}
              className={clsx(
                "p-4 rounded-r-xl border-l-4 flex gap-3.5 items-start justify-between shadow-sm transition-all hover:translate-x-0.5",
                borderColors[item.type],
                bgColors[item.type],
              )}
            >
              <div className="flex gap-3 items-start min-w-0">
                <div className={clsx("p-1.5 rounded-lg bg-surface-lowest shrink-0", iconColors[item.type])}>
                  <Icon className="w-4 h-4 stroke-[1.5]" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-body-md font-semibold text-on-surface truncate">
                    {item.title}
                  </span>
                  <span className="text-body-sm text-on-surface-variant/80 mt-0.5 leading-relaxed">
                    {item.description}
                  </span>
                </div>
              </div>
              <span className="text-mono-data text-xs text-on-surface-variant/60 whitespace-nowrap shrink-0">
                {item.timestamp}
              </span>
            </div>
          );
        })
      ) : (
        <div className="text-center py-8 text-body-md text-on-surface-variant/50">
          Aucune activité récente.
        </div>
      )}
    </div>
  );
}
