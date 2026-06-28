"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Users, UserCheck, Clock, Zap, CreditCard, Percent,
  AlertTriangle, HeartPulse, Activity, LogIn, ArrowRight,
  DollarSign, ShoppingBag, ShoppingCart, UserMinus
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";
import { api } from "@/lib/api";
import { StatCard } from "@/components/ui/stat-card";
import { Card, Skeleton, EmptyState } from "@/components/ui/index";
import { useLiveCounts, useLiveFeed } from "@/hooks/use-live-feed";
import { todayISO, formatDuration } from "@/lib/utils";
import { useState, useEffect } from "react";

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 px-3 py-2 rounded-lg shadow-md text-xs font-medium">
      <p className="text-gray-500 mb-1">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-gray-900 capitalize">{p.name}: {p.value}</span>
        </div>
      ))}
    </div>
  );
};

export default function DashboardPage() {
  const liveCounts = useLiveCounts();
  const today = todayISO();

  // ── Real-time last-update tracker ─────────────────────────────────────────
  const [lastEventAt, setLastEventAt] = useState<Date | null>(null);
  const [updateAgoText, setUpdateAgoText] = useState("waiting...");

  useLiveFeed((e) => {
    setLastEventAt(new Date());
  });

  useEffect(() => {
    const tick = () => {
      if (!lastEventAt) {
        setUpdateAgoText("waiting for events...");
        return;
      }
      const diffMs = Date.now() - lastEventAt.getTime();
      const secs = Math.round(diffMs / 1000);
      if (secs < 60) setUpdateAgoText(`${secs}s ago`);
      else if (secs < 3600) setUpdateAgoText(`${Math.round(secs / 60)}m ago`);
      else setUpdateAgoText(`${Math.round(secs / 3600)}h ago`);
    };
    tick();
    const id = setInterval(tick, 5_000);
    return () => clearInterval(id);
  }, [lastEventAt]);

  // ── Queries ───────────────────────────────────────────────────────────────
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["summary", today],
    queryFn: () => api.getSummary({ date_from: today, date_to: today }),
    refetchInterval: 60_000,
  });

  const { data: hourlyData, isLoading: hourlyLoading } = useQuery({
    queryKey: ["hourly-traffic", today],
    queryFn: () => api.getHourlyTraffic({ target_date: today }),
    refetchInterval: 60_000,
  });

  const { data: camerasData } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.getCameras(),
  });
  const cameras = camerasData?.cameras;

  const { data: conversion } = useQuery({
    queryKey: ["conversion", today],
    queryFn: () => api.getConversion({ target_date: today }),
    refetchInterval: 60_000,
  });

  const { data: queue } = useQuery({
    queryKey: ["queue", today],
    queryFn: () => api.getQueue({ target_date: today }),
    refetchInterval: 60_000,
  });

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    refetchInterval: 30_000,
  });

  // Transaction intelligence stats for Conversion Insights block
  const { data: txnStats } = useQuery({
    queryKey: ["txn_stats", today],
    queryFn: () => api.getTxnStats({ target_date: today }),
    refetchInterval: 30_000,
  });

  // Daily traffic (for yesterday trend)
  const { data: dailyData } = useQuery({
    queryKey: ["daily-traffic", 7],
    queryFn: () => api.getDailyTraffic(7),
    refetchInterval: 60_000,
  });

  // ── Computed values ───────────────────────────────────────────────────────
  const activeCameras = cameras?.filter((c: any) => c.status === "active").length ?? 0;
  const totalCameras = cameras?.length ?? 0;
  const firstActiveCamera = cameras?.find((c: any) => c.status === "active");

  // Health score: if backend returns `score`, use it. Otherwise compute from cameras.
  const healthScore = health?.score ?? (totalCameras > 0 ? Math.round((activeCameras / totalCameras) * 100) : 0);

  const chartData = hourlyData?.length ? hourlyData : [];

  const funnel = conversion?.funnel || [];
  const entered = funnel[0]?.count || 0;
  const browsed = funnel[1]?.count || 0;
  const checkout = funnel[2]?.count || 0;

  // Queue alerts: real snapshot count
  const queueAlerts = queue?.snapshots?.length || 0;

  // Yesterday vs today trend for visitors
  const todayEntries = summary?.total_entries ?? 0;
  const sortedDaily = dailyData?.length ? [...dailyData].sort((a: any, b: any) => b.date.localeCompare(a.date)) : [];
  const yesterdayEntries = sortedDaily[1]?.total_entries ?? 0;
  const visitorTrend = yesterdayEntries > 0
    ? parseFloat(((todayEntries - yesterdayEntries) / yesterdayEntries * 100).toFixed(1))
    : null;

  const [recentEvents, setRecentEvents] = useState<any[]>([]);

  useLiveFeed((e) => {
    setRecentEvents((prev) => [{
      id: Math.random().toString(),
      type: e.event_type || e.type,
      title: e.type,
      sub: `Visitor #${e.track_id ? e.track_id.toString().substring(0, 4) : "????"} · ${e.zone_name || "Unknown"}`,
      time: new Date().toLocaleTimeString("en-US", { hour12: false }),
      icon: e.type === "entry" || e.type === "track_start" ? LogIn : ShoppingCart,
      color: e.type === "entry" || e.type === "track_start" ? "text-emerald-500" : "text-blue-500",
      bg: e.type === "entry" || e.type === "track_start" ? "bg-emerald-50" : "bg-blue-50",
      pending: false
    }, ...prev].slice(0, 5));
  });

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10">

      {/* ── KPI Cards Grid ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Row 1 */}
        <StatCard
          title="Today's Visitors"
          value={(summary?.total_entries ?? liveCounts.todayEntries) || 0}
          trend={visitorTrend ?? undefined}
          trendLabel="vs yesterday"
          icon={Users}
          color="emerald"
        />
        <StatCard
          title="Current Visitors"
          value={liveCounts.currentInStore || 0}
          subtitle="In-store right now"
          icon={UserCheck}
          color="blue"
        />
        <StatCard
          title="Avg Dwell Time"
          value={summary?.avg_dwell_seconds ? summary.avg_dwell_seconds / 60 : 0}
          format="number"
          subtitle="Across completed visits"
          icon={Clock}
          color="violet"
        />
        <StatCard
          title="Peak Hour"
          value={summary?.peak_hour || "N/A"}
          subtitle="Highest entries today"
          icon={Zap}
          color="amber"
        />

        {/* Row 2 */}
        <StatCard
          title="Transactions"
          value={txnStats?.likely_purchases ?? 0}
          subtitle="Likely purchases today"
          icon={CreditCard}
          color="violet"
        />
        <StatCard
          title="Conversion Rate"
          value={conversion?.conversion_rate_pct || 0}
          format="percent"
          subtitle="Transactions / Visitors"
          icon={Percent}
          color="emerald"
        />
        <StatCard
          title="Queue Alerts"
          value={queueAlerts}
          subtitle={queueAlerts === 0 ? "No queue snapshots yet" : `${queueAlerts} snapshots today`}
          icon={AlertTriangle}
          color="slate"
        />
        <StatCard
          title="Store Health Score"
          value={healthScore}
          format="percent"
          subtitle={`${activeCameras}/${totalCameras} cameras online`}
          icon={HeartPulse}
          color={healthScore >= 80 ? "emerald" : healthScore >= 50 ? "amber" : "rose"}
        />
      </div>

      {/* ── Main Charts Row ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Today's Traffic & Funnel */}
        <div className="lg:col-span-2 space-y-6">
          <Card
            title="Today's Traffic"
            description="Hourly visitor entries"
            action={<a href="/analytics" className="text-sm font-semibold text-emerald-600 flex items-center gap-1">View Analytics <ArrowRight className="w-3.5 h-3.5" /></a>}
            className="h-full flex flex-col"
          >
            <div className="flex-1 mt-6">
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={chartData} margin={{ top: 10, right: 0, left: -25, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorEntries" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                  <XAxis dataKey="hour" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#9ca3af" }} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#9ca3af" }} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="entries" stroke="#10b981" strokeWidth={2.5} fill="url(#colorEntries)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Funnel */}
            <div className="mt-8 pt-6 border-t border-gray-100">
              <div className="flex items-end justify-between px-2 mb-2">
                <div className="w-1/3">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">Visitors</p>
                  <p className="text-xl font-bold text-gray-900">{entered}</p>
                </div>
                <div className="w-1/3">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">Browsed</p>
                  <p className="text-xl font-bold text-gray-900">{browsed}</p>
                </div>
                <div className="w-1/3">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">Checkout</p>
                  <p className="text-xl font-bold text-gray-900">{checkout}</p>
                </div>
              </div>
              <div className="flex h-1.5 rounded-full bg-gray-100 overflow-hidden mx-2">
                <div className="h-full bg-emerald-500" style={{ width: entered > 0 ? '33.3%' : '0%' }} />
                <div className="h-full bg-blue-500" style={{ width: browsed > 0 ? '33.3%' : '0%' }} />
                <div className="h-full bg-gray-300" style={{ width: checkout > 0 ? '33.3%' : '0%' }} />
              </div>
              <div className="flex justify-between px-2 mt-2">
                <p className="text-[10px] font-semibold text-gray-500 w-1/3">{funnel[0]?.rate || 0}%</p>
                <p className="text-[10px] font-semibold text-gray-500 w-1/3">{funnel[1]?.rate || 0}%</p>
                <p className="text-[10px] font-semibold text-gray-500 w-1/3">{funnel[2]?.rate || 0}%</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Live Camera Card */}
        <div className="lg:col-span-1 h-full">
          <Card
            title="Live Camera"
            description={firstActiveCamera ? firstActiveCamera.name : "No Active Cameras"}
            action={<a href="/cameras" className="text-sm font-semibold text-emerald-600 flex items-center gap-1">All Cameras <ArrowRight className="w-3.5 h-3.5" /></a>}
            className="h-full flex flex-col"
          >
            <div className="mt-4 flex-1 rounded-xl bg-gray-100 overflow-hidden relative border border-gray-200 flex items-center justify-center min-h-[220px]">
              {firstActiveCamera ? (
                 <div className="flex flex-col items-center justify-center space-y-2 text-emerald-500 h-full w-full bg-black/5">
                   <div className="absolute top-2 left-2 flex gap-1">
                     <span className="px-1.5 py-0.5 rounded bg-red-500 text-white text-[8px] font-bold uppercase">REC</span>
                   </div>
                   <Activity className="w-8 h-8 opacity-50" />
                   <span className="text-xs font-bold tracking-widest uppercase opacity-75">STREAM ACTIVE</span>
                 </div>
              ) : (
                <div className="flex flex-col items-center justify-center space-y-2">
                  <span className="text-xs font-bold text-gray-500 tracking-widest uppercase">OFFLINE</span>
                  <span className="text-[10px] text-gray-400 font-mono">No cameras connected</span>
                </div>
              )}
            </div>

            <div className="grid grid-cols-3 gap-2 mt-4 text-center">
              <div className="bg-gray-50 rounded-lg py-2 border border-gray-100">
                <p className="text-[10px] font-bold text-gray-400 uppercase">FPS</p>
                <p className="text-sm font-bold text-gray-900 mt-0.5">{firstActiveCamera?.fps || "--"}</p>
              </div>
              <div className="bg-gray-50 rounded-lg py-2 border border-gray-100">
                <p className="text-[10px] font-bold text-gray-400 uppercase">Health</p>
                <p className="text-sm font-bold text-gray-900 mt-0.5">
                  {firstActiveCamera ? `${healthScore}%` : '--'}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg py-2 border border-gray-100">
                <p className="text-[10px] font-bold text-gray-400 uppercase">Status</p>
                <p className="text-sm font-bold text-gray-900 mt-0.5 capitalize">{firstActiveCamera ? 'Active' : 'N/A'}</p>
              </div>
            </div>
          </Card>
        </div>

      </div>

      {/* ── Bottom Row ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Recent Activity */}
        <div className="lg:col-span-2">
          <Card
            title="Recent Activity"
            description="Latest events from the AI engine"
            action={<a href="/timeline" className="text-sm font-semibold text-emerald-600 flex items-center gap-1">Full Timeline <ArrowRight className="w-3.5 h-3.5" /></a>}
            className="h-full"
          >
            <div className="mt-4 space-y-4">
              {recentEvents.length === 0 && (
                <div className="text-center text-gray-400 text-xs py-10">No recent events yet. Waiting for CCTV activity...</div>
              )}
              {recentEvents.map((event: any, i: number) => (
                <div key={event.id || i} className="flex items-center justify-between group">
                  <div className="flex items-center gap-4">
                    <div className={`p-2 rounded-lg ${event.bg}`}>
                      <event.icon className={`w-4 h-4 ${event.color}`} />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-gray-900 group-hover:text-emerald-600 transition-colors cursor-pointer">{event.title}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{event.sub}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-mono font-medium text-gray-900">{event.time}</p>
                    {event.pending && <p className="text-[10px] font-bold text-amber-500 mt-0.5">pending sync</p>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Analytics Insights */}
        <div className="lg:col-span-1 space-y-6">
          <Card title="Last Analytics Update">
            <div className="mt-2">
              <p className="text-2xl font-bold text-gray-900">{updateAgoText}</p>
              <p className="text-xs font-medium text-gray-500 mt-4">Local AI engine processes frames in real-time</p>
            </div>
          </Card>

          <Card title="Conversion Insights">
            <div className="mt-6 space-y-5">
              <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                <div className="flex items-center gap-3">
                  <div className="p-1.5 rounded-md bg-emerald-50"><DollarSign className="w-4 h-4 text-emerald-500" /></div>
                  <span className="text-sm font-semibold text-gray-700">Revenue / Visitor</span>
                </div>
                <span className="text-sm font-bold text-gray-400" title="Requires POS integration">--</span>
              </div>
              <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                <div className="flex items-center gap-3">
                  <div className="p-1.5 rounded-md bg-amber-50"><ShoppingBag className="w-4 h-4 text-amber-500" /></div>
                  <span className="text-sm font-semibold text-gray-700">Likely Purchases</span>
                </div>
                <span className="text-sm font-bold text-gray-900">
                  {txnStats?.likely_purchases ?? "--"}
                </span>
              </div>
              <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                <div className="flex items-center gap-3">
                  <div className="p-1.5 rounded-md bg-purple-50"><ShoppingBag className="w-4 h-4 text-purple-500" /></div>
                  <span className="text-sm font-semibold text-gray-700">Confirmed Purchases</span>
                </div>
                <span className="text-sm font-bold text-gray-900">
                  {txnStats?.total_sessions != null
                    ? txnStats.likely_purchases ?? 0
                    : "--"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-1.5 rounded-md bg-rose-50"><UserMinus className="w-4 h-4 text-rose-500" /></div>
                  <span className="text-sm font-semibold text-gray-700">Checkout Abandonment</span>
                </div>
                <span className="text-sm font-bold text-gray-900">
                  {txnStats?.checkout_abandonment ?? "--"}
                </span>
              </div>
            </div>
          </Card>
        </div>

      </div>
    </div>
  );
}
