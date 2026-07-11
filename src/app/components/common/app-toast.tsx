import { CheckCircle2, Info, TriangleAlert, X, XCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";

export type AppToastTone = "success" | "error" | "warning" | "info";

interface AppToastProps {
  tone: AppToastTone;
  message: string;
  onClose?: () => void;
  visible?: boolean;
}

const toneStyles: Record<AppToastTone, string> = {
  success: "bg-safe text-white",
  error: "bg-error text-on-error",
  warning: "bg-warning text-slate-950",
  info: "bg-primary text-on-primary",
};

const toneIcons = {
  success: CheckCircle2,
  error: XCircle,
  warning: TriangleAlert,
  info: Info,
};

export function AppToast({ tone, message, onClose, visible = true }: AppToastProps) {
  const Icon = toneIcons[tone];

  return (
    <AnimatePresence>
      {visible && message && (
        <motion.div
          role="status"
          aria-live={tone === "error" ? "assertive" : "polite"}
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 18 }}
          transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
          className={clsx(
            "fixed bottom-6 left-4 right-4 z-50 flex min-h-12 items-center gap-3 rounded-none px-4 py-3 text-[15px] font-semibold leading-5 shadow-lg md:left-[272px] md:right-12",
            toneStyles[tone],
          )}
        >
          <Icon className="h-5 w-5 shrink-0 stroke-[2.2]" />
          <span className="min-w-0 flex-1">{message}</span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-current/85 transition-colors hover:bg-white/15 hover:text-current focus:outline-none focus:ring-2 focus:ring-white/55"
              aria-label="Fermer la notification"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
