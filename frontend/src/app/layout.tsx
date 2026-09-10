import type { Metadata } from "next";
import Link from "next/link";

import { HealthPill } from "@/components/ui/HealthPill";
import "./globals.css";

export const metadata: Metadata = {
  title: "Order Supervisor",
  description: "Long-running AI supervision for a single order, on Temporal.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-edge bg-panel">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
              <Link href="/" className="text-base font-semibold text-slate-100">
                Order Supervisor
              </Link>
              <nav className="flex gap-4 text-sm text-slate-400">
                <Link href="/" className="hover:text-slate-100">
                  Runs
                </Link>
                <Link href="/supervisors" className="hover:text-slate-100">
                  Supervisors
                </Link>
                <Link href="/runs/new" className="hover:text-slate-100">
                  Start a run
                </Link>
              </nav>
              <div className="ml-auto">
                <HealthPill />
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
