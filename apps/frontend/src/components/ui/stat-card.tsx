"use client";

import { cn, formatNumber, formatDuration } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: number;
  trendLabel?: string;
  color?: "blue" | "violet" | "emerald" | "amber" | "rose" | "cyan" | "slate";
  loading?: boolean;
  format?: "number" | "duration" | "percent" | "raw";
}

const colorMap = {
  blue:    { bg: "bg-blue-50", text: "text-blue-600" },
  violet:  { bg: "bg-violet-50", text: "text-violet-600" },
  emerald: { bg: "bg-emerald-50", text: "text-emerald-600" },
  amber:   { bg: "bg-amber-50", text: "text-amber-600" },
  rose:    { bg: "bg-rose-50", text: "text-rose-600" },
  cyan:    { bg: "bg-cyan-50", text: "text-cyan-600" },
  slate:   { bg: "bg-slate-50", text: "text-slate-600" },
};

export function StatCard({
  title, value, subtitle, icon: Icon, trend, trendLabel,
  color = "blue", loading = false, format = "raw",
}: StatCardProps) {
  const colors = colorMap[color] || colorMap.blue;

  const displayValue = loading ? "—" : (() => {
    const n = typeof value === "number" ? value : parseFloat(String(value));
    if (isNaN(n)) return String(value);
    if (format === "number") return formatNumber(n);
    if (format === "duration") return formatDuration(n);
    if (format === "percent") return `${n.toFixed(1)}%`;
    return String(value);
  })();

  const trendPositive = trend !== undefined && trend > 0;
  const trendNegative = trend !== undefined && trend < 0;

  return (
    <div className="relative flex flex-col justify-between overflow-hidden rounded-xl bg-white border border-gray-200 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-3">{title}</p>
          <div className="flex items-baseline gap-2">
            {loading ? (
              <div className="h-8 w-20 rounded-md bg-gray-100 animate-pulse" />
            ) : (
              <div className="flex items-center">
                <p className="text-3xl font-bold text-gray-900 tabular-nums tracking-tight animate-count-in">{displayValue}</p>
                {trend !== undefined && !loading && trendPositive && <span className="ml-2 w-1.5 h-1.5 rounded-full bg-emerald-500" />}
                {trend !== undefined && !loading && trendNegative && <span className="ml-2 w-1.5 h-1.5 rounded-full bg-rose-500" />}
              </div>
            )}
          </div>
        </div>
        <div className={cn("p-2 rounded-lg", colors.bg, colors.text)}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      
      <div className="mt-4 flex items-center justify-between">
        {trend !== undefined && !loading ? (
          <div className={cn(
            "flex items-center gap-1.5 text-xs font-semibold",
            trendPositive ? "text-emerald-500" : trendNegative ? "text-rose-500" : "text-gray-400"
          )}>
            {trendPositive ? <TrendingUp className="w-3.5 h-3.5" /> :
             trendNegative ? <TrendingDown className="w-3.5 h-3.5" /> :
             <Minus className="w-3.5 h-3.5" />}
            <span>{Math.abs(trend).toFixed(1)}% <span className="text-gray-400 font-medium ml-1">{trendLabel ?? "vs yesterday"}</span></span>
          </div>
        ) : (
          <p className="text-xs text-gray-400 font-medium">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
