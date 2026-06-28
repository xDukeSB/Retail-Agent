"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Camera, BarChart3, Map, Users,
  FileText, Settings, Activity, ShoppingCart, TrendingUp,
  Zap, ChevronRight, Cloud, CloudOff, Package, CreditCard
} from "lucide-react";
import { cn } from "@/lib/utils";

const localNav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/cameras", label: "Live Cameras", icon: Camera },
  { href: "/timeline", label: "Timeline", icon: Activity },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/transactions", label: "Transactions", icon: CreditCard },
  { href: "/heatmap", label: "Zones & Heatmap", icon: Map },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 flex-shrink-0 h-screen flex flex-col bg-[var(--brand-sidebar)] border-r border-white/5">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-6">
        <div className="w-8 h-8 rounded-lg bg-[#10b981] flex items-center justify-center">
          <Package className="w-4 h-4 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold text-white leading-none tracking-wide">RetailAI</p>
          <p className="text-[10px] text-white/50 leading-none mt-1 uppercase tracking-wider font-medium">Local Agent</p>
        </div>
      </div>

      {/* Store Info */}
      <div className="px-5 mb-6">
        <p className="text-[10px] font-bold text-white/40 uppercase tracking-wider mb-2">This Store</p>
        <p className="text-sm font-semibold text-white/90 leading-tight">Downtown Flagship</p>
        <p className="text-[11px] text-white/40 mt-0.5">North America - West</p>
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span className="text-[10px] text-emerald-400 font-medium">Health 90</span>
          </div>
          <div className="px-1.5 py-0.5 rounded-md bg-amber-500/20 text-amber-400 text-[10px] font-semibold">
            2 pending
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 space-y-6">
        {/* Local Dashboard */}
        <div>
          <p className="text-[10px] font-bold text-white/40 uppercase tracking-wider px-2 mb-2">Local Dashboard</p>
          <ul className="space-y-1">
            {localNav.map(({ href, label, icon: Icon }) => {
              const active = pathname === href;
              return (
                <li key={href}>
                  <Link
                    href={href}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group",
                      active
                        ? "bg-[#10b981] text-white shadow-md shadow-emerald-900/20"
                        : "text-white/50 hover:text-white/90 hover:bg-white/5"
                    )}
                  >
                    <Icon
                      className={cn(
                        "w-4 h-4 flex-shrink-0 transition-colors",
                        active ? "text-white" : "text-white/40 group-hover:text-white/70"
                      )}
                    />
                    <span className="flex-1">{label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Cloud */}
        <div>
          <p className="text-[10px] font-bold text-white/40 uppercase tracking-wider px-2 mb-2">Cloud</p>
          <ul className="space-y-1">
            <li>
              <Link
                href="/cloud"
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-white/50 hover:text-white/90 hover:bg-white/5 transition-all duration-150 group"
              >
                <Cloud className="w-4 h-4 flex-shrink-0 text-white/40 group-hover:text-white/70" />
                <span className="flex-1">Cloud Dashboard</span>
              </Link>
            </li>
          </ul>
        </div>
      </nav>

      {/* Footer */}
      <div className="p-5 border-t border-white/5 mt-auto">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          <span className="text-[11px] text-white/80 font-bold">Local-First Active</span>
        </div>
        <p className="text-[10px] text-white/40 leading-relaxed">
          All analytics run locally. Cloud is a synchronized copy.
        </p>
      </div>
    </aside>
  );
}
