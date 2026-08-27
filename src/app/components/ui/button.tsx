import { type ButtonHTMLAttributes, forwardRef } from "react";
import { clsx } from "clsx";

type ButtonVariant = "primary" | "warning" | "ghost" | "outline" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-navy-dark text-on-primary hover:brightness-95 shadow-sm",
  warning:
    "bg-secondary text-on-secondary hover:bg-amber-dark shadow-sm",
  danger:
    "bg-error text-on-error hover:bg-on-error-container shadow-sm",
  ghost:
    "bg-transparent text-on-surface hover:bg-surface-container",
  outline:
    "bg-surface-lowest border border-border-subtle text-on-surface hover:bg-surface-container",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-body-sm rounded-md gap-1.5",
  md: "px-5 py-2.5 text-body-md rounded-lg gap-2",
  lg: "px-8 py-4 text-body-lg rounded-lg gap-2.5",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", fullWidth, className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={clsx(
          "inline-flex items-center justify-center font-semibold transition-all duration-200 cursor-pointer select-none",
          "active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none",
          variantStyles[variant],
          sizeStyles[size],
          fullWidth && "w-full",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);

Button.displayName = "Button";
