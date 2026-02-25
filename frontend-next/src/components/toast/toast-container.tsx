"use client";

import { useToast, type ToastVariant } from "./toast-context";
import { AlertCircle, CheckCircle, AlertTriangle, Info, X } from "lucide-react";

const VARIANT_STYLES: Record<ToastVariant, string> = {
  error: "border-red-500/50 bg-red-950/80 text-red-200",
  success: "border-emerald-500/50 bg-emerald-950/80 text-emerald-200",
  warning: "border-amber-500/50 bg-amber-950/80 text-amber-200",
  info: "border-blue-500/50 bg-blue-950/80 text-blue-200",
};

const VARIANT_ICONS: Record<ToastVariant, React.ReactNode> = {
  error: <AlertCircle size={16} />,
  success: <CheckCircle size={16} />,
  warning: <AlertTriangle size={16} />,
  info: <Info size={16} />,
};

export function ToastContainer() {
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-start gap-2 px-4 py-3 rounded border backdrop-blur-sm shadow-lg animate-slide-in ${VARIANT_STYLES[toast.variant]}`}
        >
          <span className="mt-0.5 shrink-0">{VARIANT_ICONS[toast.variant]}</span>
          <p className="text-sm flex-1 font-mono leading-snug">{toast.message}</p>
          <button
            onClick={() => removeToast(toast.id)}
            className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
