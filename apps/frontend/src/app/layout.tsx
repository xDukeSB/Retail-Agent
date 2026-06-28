import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    template: "%s | RetailAI Agent",
    default: "RetailAI Agent — Local-First Retail Intelligence",
  },
  description:
    "Transform existing CCTV cameras into anonymous retail business intelligence. Customer counts, heatmaps, queue analytics, and more — all local-first.",
  keywords: ["retail analytics", "customer counting", "store heatmap", "queue analytics", "business intelligence"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>
          <div className="flex h-screen overflow-hidden bg-gray-50">
            <Sidebar />
            <div className="flex flex-col flex-1 overflow-hidden">
              <Topbar />
              <main className="flex-1 overflow-y-auto p-6">
                {children}
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
