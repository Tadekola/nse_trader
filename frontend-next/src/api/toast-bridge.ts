/**
 * Bridge between the non-React API client and the React toast system.
 * The API client calls `emitToast()`, and the ToastProvider subscribes via `onToast()`.
 */

export type ToastEvent = {
  message: string;
  variant: "error" | "success" | "warning" | "info";
};

type Listener = (event: ToastEvent) => void;

const listeners: Set<Listener> = new Set();

export function onToast(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function emitToast(message: string, variant: ToastEvent["variant"] = "error") {
  listeners.forEach((fn) => fn({ message, variant }));
}
