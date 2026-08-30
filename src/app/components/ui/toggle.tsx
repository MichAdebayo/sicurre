import React, { useId } from "react";
import { clsx } from "clsx";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  description?: string;
  className?: string;
}

export function Toggle({
  checked,
  onChange,
  disabled = false,
  label,
  description,
  className,
}: ToggleProps) {
  const labelId = useId();
  const descriptionId = useId();
  const handleToggle = () => {
    if (!disabled) {
      onChange(!checked);
    }
  };

  return (
    <div className={clsx("flex items-start justify-between gap-4", className)}>
      {(label || description) && (
        <div className="flex flex-col gap-0.5">
          {label && (
            <span id={labelId} className="text-body-md font-semibold text-on-surface select-none">
              {label}
            </span>
          )}
          {description && (
            <span id={descriptionId} className="text-body-sm text-on-surface-variant/70 select-none">
              {description}
            </span>
          )}
        </div>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={label ? labelId : undefined}
        aria-describedby={description ? descriptionId : undefined}
        disabled={disabled}
        onClick={handleToggle}
        className={clsx(
          "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary/20",
          checked ? "bg-primary" : "bg-surface-high",
          disabled && "opacity-50 cursor-not-allowed",
        )}
      >
        <span
          className={clsx(
            "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-surface-lowest shadow ring-0 transition duration-200 ease-in-out",
            checked ? "translate-x-5" : "translate-x-0",
          )}
        />
      </button>
    </div>
  );
}
