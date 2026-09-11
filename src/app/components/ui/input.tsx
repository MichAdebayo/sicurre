import { type InputHTMLAttributes, forwardRef, type ReactNode, useId } from "react";
import { clsx } from "clsx";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: ReactNode;
  suffix?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, suffix, className, id, ...props }, ref) => {
    // Generate an id when the caller passes none, so the label stays associated.
    const generatedId = useId();
    const inputId = id ?? generatedId;
    const errorId = `${inputId}-error`;

    return (
      <div className="w-full flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-label-caps text-on-surface-variant font-semibold">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {icon && (
            <div className="absolute left-3.5 text-on-surface-variant/70 pointer-events-none flex items-center justify-center">
              {icon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            className={clsx(
              "w-full px-4 py-2.5 bg-surface-lowest border border-border-subtle rounded-lg text-body-md text-on-surface placeholder:text-on-surface-variant/40 transition-all duration-200 focus:outline-none focus:border-primary focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50 disabled:bg-surface-low",
              icon && "pl-11",
              suffix && "pr-11",
              error && "border-error focus:border-error focus-visible:ring-error",
              className,
            )}
            {...props}
          />
          {suffix && (
            <div className="absolute right-3.5 flex items-center justify-center">
              {suffix}
            </div>
          )}
        </div>
        {error && (
          <span id={errorId} className="text-body-sm text-error font-medium">
            {error}
          </span>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";
