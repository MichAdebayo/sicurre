import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "safe";
}

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={twMerge(
        clsx(
          "inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-xs font-semibold shadow-md active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50",
          {
            "bg-accent hover:bg-accent-dark text-slate-950 hover:shadow-accent/20": variant === "primary",
            "bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300": variant === "secondary",
            "bg-red-50 hover:bg-red-100 border border-red-200 text-red-700": variant === "danger",
            "bg-green-50 hover:bg-green-100 border border-green-200 text-green-700": variant === "safe"
          }
        ),
        className
      )}
      {...props}
    />
  );
}
