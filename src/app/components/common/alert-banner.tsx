import React, { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { clsx } from "clsx";

interface AlertBannerProps {
  message: string;
  type?: "warning" | "critical";
  onClose?: () => void;
  className?: string;
}

export function AlertBanner({
  message,
  type = "warning",
  onClose,
  className,
}: AlertBannerProps) {
  const [isVisible, setIsVisible] = useState(true);

  if (!isVisible) return null;

  const handleClose = () => {
    setIsVisible(false);
    onClose?.();
  };

  return (
    <div
      className={clsx(
        "relative w-full px-6 py-3 flex items-center justify-between transition-all duration-300",
        type === "warning" && "bg-secondary-container text-on-secondary-container border-b border-secondary/20",
        type === "critical" && "bg-error-container text-on-error-container border-b border-error/20",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 shrink-0 animate-bounce" />
        <span className="text-body-sm font-semibold tracking-wide font-sans">
          {message}
        </span>
      </div>
      <button
        onClick={handleClose}
        className="p-1 rounded-md hover:bg-black/10 transition-colors text-current cursor-pointer"
        aria-label="Fermer la bannière d'alerte"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
