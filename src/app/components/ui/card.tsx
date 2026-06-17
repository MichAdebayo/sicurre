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
        variant === "default" && "bg-surface-lowest text-on-surface border border-border-subtle",
        variant === "safe" && "bg-surface-safe text-on-surface border border-safe/20",
        variant === "alert" && "bg-surface-alert text-on-surface border border-secondary/20",
        variant === "dark" && "glass-card-dark text-white",
        // Elevation styling
        elevation === "flat" && "",
        elevation === "border" && "border",
        elevation === "hover" && "hover:shadow-md border",
        elevation === "shadow" && "shadow-lg border",
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
