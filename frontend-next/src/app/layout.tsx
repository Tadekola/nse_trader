import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { StatusBar } from "@/components/layout/status-bar";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "NSE Trader — Portfolio Intelligence",
  description: "Institutional-grade Nigerian stock portfolio analytics",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen flex">
        <Providers>
          <Sidebar />
          <div className="flex-1 flex flex-col min-h-screen ml-56">
            <StatusBar />
            <main className="flex-1 p-6 overflow-auto">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
