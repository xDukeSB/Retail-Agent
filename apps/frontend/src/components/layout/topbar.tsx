"use client";

import { usePathname } from "next/navigation";
import { Clock, Activity, Wifi, WifiOff, RefreshCcw, Cloud } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

const pageTitles: Record<string, { title: string; description: string }> = {
  "/cloud": { title: "Cloud Dashboard", description: "Multi-store visibility with data freshness" },
  "/analytics": { title: "Analytics", description: "Traffic, dwell, peak hours & conversion trends" },
  "/timeline": { title: "Timeline", description: "Real-time customer & event activity feed" },
  "/heatmap": { title: "Zones & Heatmap", description: "Store zone analytics and customer flow" },
  "/queue": { title: "Queue Analytics", description: "Queue depth & wait time tracking" },
  "/checkout": { title: "Checkout", description: "Checkout zone performance" },
  "/conversion": { title: "Conversion", description: "Entry to purchase funnel" },
  "/transactions": { title: "Transaction Intelligence", description: "Live purchase intent estimation — state machine, signals & confidence scoring" },
  "/cameras": { title: "Live Cameras", description: "RTSP feeds via MediaMTX -> WebRTC pipeline" },
  "/reports": { title: "Reports", description: "Generate daily, weekly & monthly business reports" },
  "/settings": { title: "Settings", description: "Store, cameras, cloud sync & AI engine configuration" },
};


export function Topbar() {
  const pathname = usePathname();
  const page = pageTitles[pathname] ?? { title: "RetailAI Agent", description: "" };

  const queryClient = useQueryClient();
  const syncMutation = useMutation({
    mutationFn: api.syncCloud,
    onSuccess: () => {
      queryClient.invalidateQueries();
    }
  });

  const { data: health, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.getHealth,
    refetchInterval: 30_000,
    retry: 1,
  });

  const isOnline = !isError && !!health;

  return (
    <header className="h-20 flex-shrink-0 flex items-center justify-between px-8 border-b border-gray-200 bg-white">
      {/* Page title */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 leading-none">{page.title}</h1>
        {page.description && (
          <p className="text-sm text-gray-500 mt-1.5 font-medium">{page.description}</p>
        )}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Current time */}
        <div className="flex items-center gap-2 text-gray-500 font-medium">
          <Clock className="w-4 h-4" />
          <LiveClock />
        </div>

        <div className="h-4 w-px bg-gray-200 mx-1" />

        {/* Health */}
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-50 text-emerald-600 text-xs font-bold tracking-wide">
          <Activity className="w-3.5 h-3.5" />
          Health 90
        </div>

        {/* Backend status */}
        <div
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold tracking-wide ${
            isOnline
              ? "bg-emerald-50 text-emerald-600"
              : "bg-rose-50 text-rose-600"
          }`}
        >
          {isOnline ? (
            <><Wifi className="w-3.5 h-3.5" /> Online</>
          ) : (
            <><WifiOff className="w-3.5 h-3.5" /> Offline</>
          )}
        </div>

        {/* Synced */}
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-50 text-emerald-600 text-xs font-bold tracking-wide">
          <Cloud className="w-3.5 h-3.5" />
          Synced (1)
        </div>

        {/* Sync Button */}
        <button 
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 ml-2 rounded-lg bg-[#10b981] hover:bg-emerald-600 transition-colors text-white text-sm font-semibold shadow-sm disabled:opacity-50"
        >
          <RefreshCcw className={`w-4 h-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
          {syncMutation.isPending ? 'Syncing...' : 'Sync Now'}
        </button>
      </div>
    </header>
  );
}

function LiveClock() {
  const [time, setTime] = useState("");

  useEffect(() => {
    setTime(new Date().toLocaleTimeString("en-US", { hour12: false }));
    const timer = setInterval(() => {
      setTime(new Date().toLocaleTimeString("en-US", { hour12: false }));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return <span className="tabular-nums text-sm">{time || "00:00:00"}</span>;
}
