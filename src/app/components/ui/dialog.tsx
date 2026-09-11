import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";

const MotionDiv = motion.div as any;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])';

type DialogSize = "sm" | "md" | "lg";

const sizeStyles: Record<DialogSize, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
};

interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Short text read after the title; also rendered under it. */
  description?: ReactNode;
  children?: ReactNode;
  /** Action row rendered below the content, separated by a rule. */
  footer?: ReactNode;
  /** `alertdialog` for confirmations that interrupt the user. */
  role?: "dialog" | "alertdialog";
  size?: DialogSize;
  /** Element to focus on open. Defaults to the first focusable control. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  className?: string;
}

interface PanelProps extends Omit<DialogProps, "isOpen"> {}

/**
 * Modal panel with the keyboard contract a dialog needs: labelled by its
 * title, focus moved inside on open and returned on close, Tab kept within
 * the panel, Escape and the backdrop close it.
 */
function DialogPanel({
  onClose,
  title,
  description,
  children,
  footer,
  role = "dialog",
  size = "md",
  initialFocusRef,
  className,
}: PanelProps) {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const target =
      initialFocusRef?.current ??
      (panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel);
    target?.focus();
    return () => {
      previouslyFocused?.focus?.();
    };
  }, [initialFocusRef]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !panelRef.current) return;
    const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (focusable.length === 0) {
      event.preventDefault();
      panelRef.current.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === panelRef.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <MotionDiv
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        aria-hidden="true"
        className="absolute inset-0 bg-on-background/60 backdrop-blur-sm"
      />
      <MotionDiv
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className={clsx(
          "relative z-10 flex max-h-[90vh] w-full flex-col overflow-y-auto rounded-2xl border border-border-subtle bg-surface-lowest p-6 shadow-2xl outline-none",
          sizeStyles[size],
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border-subtle pb-4">
          <div className="min-w-0">
            <h2 id={titleId} className="app-h2 text-on-surface">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="app-body-sub mt-0.5">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("common.close")}
            className="shrink-0 rounded-md p-1 text-on-surface-variant transition-colors hover:bg-surface-low hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {children && <div className="pt-4 text-body-md text-on-surface-variant">{children}</div>}
        {footer && <div className="mt-5 border-t border-border-subtle pt-5">{footer}</div>}
      </MotionDiv>
    </div>
  );
}

export function Dialog({ isOpen, ...panelProps }: DialogProps) {
  return <AnimatePresence>{isOpen && <DialogPanel {...panelProps} />}</AnimatePresence>;
}
