import React from "react";
import { clsx } from "clsx";

type CardVariant = "default" | "safe" | "alert" | "dark";
type CardElevation = "flat" | "border" | "hover" | "shadow";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  elevation?: CardElevation;
}

export function Card({
  className,
  variant = "default",
  elevation = "border",
  ...props
}: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-xl transition-all duration-200",
        // Variant styling
        variant === "default" && "bg-surface-lowest text-on-surface border border-border-subtle/80 shadow-[0_1px_2px_rgba(0,0,0,0.04)]",
        variant === "safe" && "bg-emerald-500/[0.03] text-on-surface border border-emerald-500/20",
        variant === "alert" && "bg-amber-500/[0.03] text-on-surface border border-amber-500/20",
        variant === "dark" && "bg-surface-low text-white border border-border-subtle",
        // Elevation styling
        elevation === "flat" && "",
        elevation === "border" && "border",
        elevation === "hover" && "hover:border-border-subtle hover:shadow-sm border",
        elevation === "shadow" && "shadow-sm border",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx("pb-4 mb-4 border-b border-border-subtle flex items-center justify-between", className)}
      {...props}
    />
  );
}

export function CardTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={clsx("text-title-md font-semibold text-on-surface font-display", className)}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={clsx("text-body-sm text-on-surface-variant/80 mt-1", className)}
      {...props}
    />
  );
}

export function CardContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("space-y-4", className)} {...props} />;
}
