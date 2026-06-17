import React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";

const MotionDiv = motion.div as any;

interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function Dialog({ isOpen, onClose, title, children }: DialogProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop overlay */}
          <MotionDiv
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-on-background/60 backdrop-blur-sm"
          />

          {/* Modal content box */}
          <MotionDiv
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="relative w-full max-w-lg overflow-hidden rounded-xl border border-border-subtle bg-surface-lowest p-6 shadow-2xl z-10"
          >
            <div className="flex items-center justify-between border-b border-border-subtle pb-3 mb-4">
              <h3 className="text-title-md font-semibold text-on-surface font-display">{title}</h3>
              <button
                onClick={onClose}
                className="rounded-lg p-1 hover:bg-surface-container text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="text-body-md text-on-surface-variant">{children}</div>
          </MotionDiv>
        </div>
      )}
    </AnimatePresence>
  );
}
