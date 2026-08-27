import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Info, TriangleAlert, X, XCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";

export type AppToastTone = "success" | "error" | "warning" | "info";

interface AppToastProps {
  tone: AppToastTone;
  message: string;
  onClose?: () => void;
  visible?: boolean;
  durationMs?: number;
}

// Every tone pairs a surface token with its matching on- token. safe and
// warning invert between themes (deep in light, bright in dark), so a
// hardcoded text colour is readable in one theme and not the other.
const toneStyles: Record<AppToastTone, string> = {
  success: "bg-safe text-on-safe",
  error: "bg-error text-on-error",
  warning: "bg-warning text-on-warning",
  info: "bg-navy-dark text-on-primary",
};

const toneIcons = {
  success: CheckCircle2,
  error: XCircle,
  warning: TriangleAlert,
  info: Info,
};

export function AppToast({
  tone,
  message,
  onClose,
  visible = true,
  durationMs = tone === "error" ? 7000 : 4500,
}: AppToastProps) {
  const Icon = toneIcons[tone];
  const [paused, setPaused] = useState(false);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!visible || !message || !onCloseRef.current || paused || durationMs <= 0) return;
    const timeoutId = window.setTimeout(() => onCloseRef.current?.(), durationMs);
    return () => window.clearTimeout(timeoutId);
  }, [durationMs, message, paused, visible]);

  return (
    <AnimatePresence>
      {visible && message && (
        <motion.div
          role={tone === "error" ? "alert" : "status"}
          aria-live={tone === "error" ? "assertive" : "polite"}
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 18 }}
          transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocusCapture={() => setPaused(true)}
          onBlurCapture={() => setPaused(false)}
          className={clsx(
            "fixed bottom-5 left-4 right-4 z-50 flex min-h-12 items-center gap-3 overflow-hidden rounded-md px-4 py-3 text-[15px] font-semibold leading-5 shadow-md md:left-auto md:right-8 md:w-[min(28rem,calc(100vw-2rem))]",
            toneStyles[tone],
          )}
        >
          <Icon className="h-5 w-5 shrink-0 stroke-[2.2]" />
          <span className="min-w-0 flex-1">{message}</span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-current/85 transition-colors hover:bg-current/15 hover:text-current focus:outline-none focus:ring-2 focus:ring-current/55"
              aria-label="Fermer la notification"
            >
              <X className="h-5 w-5" />
            </button>
          )}
          {!paused && durationMs > 0 && (
            <motion.span
              key={`${tone}-${message}`}
              aria-hidden="true"
              className="absolute inset-x-0 bottom-0 h-1 origin-left bg-current/40"
              initial={{ scaleX: 1 }}
              animate={{ scaleX: 0 }}
              transition={{ duration: durationMs / 1000, ease: "linear" }}
            />
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
