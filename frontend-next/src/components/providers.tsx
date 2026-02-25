"use client";

import { ToastProvider, ToastContainer } from "@/components/toast";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      {children}
      <ToastContainer />
    </ToastProvider>
  );
}
