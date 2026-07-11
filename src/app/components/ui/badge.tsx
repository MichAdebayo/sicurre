import React from "react";
import { clsx } from "clsx";

export type BadgeVariant = "info" | "warning" | "critical" | "success" | "neutral";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
  info: "bg-primary/10 text-primary border border-primary/20",
  warning: "bg-secondary/10 text-secondary border border-secondary/20",
  critical: "bg-error/10 text-error border border-error/20",
  success: "bg-safe/10 text-safe border border-safe/20",
  neutral: "bg-on-surface/5 text-on-surface-variant border border-on-surface/10",
};

export function Badge({ variant = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-label-caps font-semibold font-sans tracking-wider",
        variantStyles[variant],
        className,
      )}
      {...props}
    />
  );
}
