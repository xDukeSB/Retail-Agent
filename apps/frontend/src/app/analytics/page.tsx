"use client";

import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell
} from "recharts";
import { Users, Clock, Percent, DollarSign, TrendingUp, Sun, Moon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { todayISO } from "@/lib/utils";
import { EmptyState } from "@/components/ui/index";


// No hardcoded fallback — show EmptyState when no live zone data


function KPICard({ title, value, trend, isPositive, icon: Icon }: any) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4 text-gray-500">
        <h3 className="text-[10px] font-bold uppercase tracking-wider">{title}</h3>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex items-end justify-between">
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <div className={`flex items-center gap-1 text-[11px] font-bold ${isPositive ? 'text-emerald-500' : 'text-rose-500'}`}>
          {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingUp className="w-3 h-3 rotate-180" />}
          {trend}
        </div>
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const today = todayISO();

  const { data: summary } = useQuery({
    queryKey: ["summary", today],
    queryFn: () => api.getSummary({ date_from: today, date_to: today }),
    refetchInterval: 60_000,
  });

  const { data: hourlyData } = useQuery({
    queryKey: ["hourly-traffic", today],
    queryFn: () => api.getHourlyTraffic({ target_date: today }),
    refetchInterval: 60_000,
  });

  const { data: dwellData } = useQuery({
    queryKey: ["dwell", today],
    queryFn: () => api.getDwell({ target_date: today }),
    refetchInterval: 60_000,
  });

  const { data: conversion } = useQuery({
    queryKey: ["conversion", today],
    queryFn: () => api.getConversion({ target_date: today }),
    refetchInterval: 60_000,
  });

  const { data: dailyData } = useQuery({
    queryKey: ["daily-traffic", 7],
    queryFn: () => api.getDailyTraffic(7),
    refetchInterval: 60_000,
  });

  const { data: zonesData } = useQuery({
    queryKey: ["zones", today],
    queryFn: () => api.getZones({ target_date: today }),
    refetchInterval: 60_000,
  });

  const { data: conversionTrendData } = useQuery({
    queryKey: ["conversion-trend", 7],
    queryFn: () => api.getConversionTrend({ days: 7 }),
    refetchInterval: 60_000,
  });

  const [timeframe, setTimeframe] = useState("Hourly");
  
  const trafficChartData = hourlyData?.length ? hourlyData.map((d: any) => ({
    time: d.hour,
    visitors: d.entries + d.exits, // approximate proxy
    entries: d.entries,
    exits: d.exits
  })) : [];
  
  const dwellChartData = dailyData?.length ? dailyData.map((d: any) => ({
    day: new Date(d.date).toLocaleDateString('en-US', { weekday: 'short' }),
    minutes: Math.round(d.avg_dwell_seconds / 60 * 10) / 10
  })) : [];
  
  const conversionTrendChartData = conversionTrendData?.trend?.length
    ? conversionTrendData.trend.map((d: any) => ({ day: d.day, rate: d.conversion_rate }))
    : [];


  // Dynamic Zone Data — no hardcoded fallback; show EmptyState if no live data
  const ZONE_DIST: any[] = zonesData?.zones?.length ? zonesData.zones : [];
  const totalZoneVisits = ZONE_DIST.reduce((acc: number, z: any) => acc + z.value, 0);


  // Dynamic Peak & Quiet Hours
  const sortedHourly = hourlyData?.length 
    ? [...hourlyData].sort((a: any, b: any) => (b.entries + b.exits) - (a.entries + a.exits))
    : [];
    
  const peakHours = sortedHourly.slice(0, 3).map((h: any, i: number) => ({
    rank: i + 1, time: h.hour, val: h.entries + h.exits
  }));
  
  // For quiet hours, filter out hours with 0 traffic to find genuinely quiet but active hours
  const activeHours = sortedHourly.filter((h: any) => (h.entries + h.exits) > 0);
  const quietHours = activeHours.length >= 3 
    ? activeHours.slice(-3).reverse().map((h: any, i: number) => ({
        rank: i + 1, time: h.hour, val: h.entries + h.exits
      }))
    : [];

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10">
      
      {/* Top Controls */}
      <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-2 shadow-sm">
        <div className="flex items-center bg-gray-100 rounded-lg p-1">
          {["Hourly", "Daily", "Weekly", "Monthly"].map(t => (
            <button 
              key={t}
              onClick={() => setTimeframe(t)}
              className={`px-4 py-1.5 rounded-md text-xs transition-colors ${timeframe === t ? "bg-white text-gray-900 font-bold shadow-sm" : "text-gray-500 font-medium hover:text-gray-700"}`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="pr-4 flex items-center gap-2 text-[11px] font-medium text-gray-500">
          <TrendingUp className="w-3.5 h-3.5" /> Showing: {timeframe.toLowerCase()} traffic for today
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="Total Visitors" value={summary?.total_entries || 0} trend="--" isPositive={true} icon={Users} />
        <KPICard title="Avg Dwell Time" value={`${summary?.avg_dwell_seconds ? (summary.avg_dwell_seconds / 60).toFixed(1) : 0}m`} trend="--" isPositive={true} icon={Clock} />
        <KPICard title="Conversion Rate" value={`${conversion?.conversion_rate_pct || 0}%`} trend="--" isPositive={true} icon={Percent} />
        <KPICard title="Revenue / Visitor" value="--" trend="--" isPositive={false} icon={DollarSign} />
      </div>

      {/* Traffic Trend */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
        <div className="mb-6">
          <h2 className="text-sm font-bold text-gray-900">Traffic Trend</h2>
          <p className="text-[11px] text-gray-500 mt-0.5">Visitors over time</p>
        </div>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trafficChartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorVisitors" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.2}/>
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }} />
              <Area type="monotone" dataKey="visitors" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorVisitors)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="flex items-center gap-4 mt-4 px-2">
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500 uppercase">
            <span className="w-2 h-2 rounded-full bg-emerald-500" /> Visitors
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500 uppercase">
            <span className="w-2 h-2 rounded-full bg-orange-500" /> Entries
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500 uppercase">
            <span className="w-2 h-2 rounded-full bg-rose-500" /> Exits
          </div>
        </div>
      </div>

      {/* Middle Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <div className="mb-6">
            <h2 className="text-sm font-bold text-gray-900">Daily Dwell Time</h2>
            <p className="text-[11px] text-gray-500 mt-0.5">Average minutes per visit (last 7 days)</p>
          </div>
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dwellChartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}m`} />
                <Tooltip cursor={{ fill: '#f3f4f6' }} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }} />
                <Bar dataKey="minutes" fill="#ea580c" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <div className="mb-6">
            <h2 className="text-sm font-bold text-gray-900">Conversion Trend</h2>
            <p className="text-[11px] text-gray-500 mt-0.5">Daily conversion rate (%) — live from AI pipeline</p>
          </div>
          <div className="h-48 w-full">
            {conversionTrendChartData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-xs text-gray-400">
                Collecting data... (populates after first full day)
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={conversionTrendChartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                  <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }} />
                  <Line type="monotone" dataKey="rate" stroke="#10b981" strokeWidth={2} dot={{ r: 4, fill: '#10b981', strokeWidth: 2, stroke: '#fff' }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Bottom 3 Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Peak Hours */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <div className="flex items-center gap-2 mb-6">
            <TrendingUp className="w-4 h-4 text-emerald-500" />
            <h2 className="text-sm font-bold text-gray-900">Peak Hours</h2>
          </div>
          <div className="space-y-3">
            {peakHours.length > 0 ? peakHours.map((h: any) => (
              <div key={h.rank} className={`flex items-center justify-between p-3 rounded-xl border ${h.rank === 1 ? 'border-emerald-100 bg-emerald-50/50' : 'border-gray-100 bg-gray-50/50'}`}>
                <div className="flex items-center gap-4">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${h.rank === 1 ? 'bg-emerald-100 text-emerald-600' : 'bg-white text-gray-400 border border-gray-200'}`}>
                    {h.rank}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-gray-900">{h.time}</p>
                    <p className="text-[10px] text-gray-500 font-medium">{h.val} visitors</p>
                  </div>
                </div>
                <Sun className={`w-4 h-4 ${h.rank === 1 ? 'text-emerald-500' : 'text-gray-300'}`} />
              </div>
            )) : <div className="text-xs text-gray-400 p-3 text-center">No traffic data yet</div>}
          </div>
        </div>

        {/* Quiet Hours */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <div className="flex items-center gap-2 mb-6">
            <Moon className="w-4 h-4 text-purple-500" />
            <h2 className="text-sm font-bold text-gray-900">Quiet Hours</h2>
          </div>
          <div className="space-y-3">
            {quietHours.length > 0 ? quietHours.map((h: any) => (
              <div key={h.rank} className={`flex items-center justify-between p-3 rounded-xl border ${h.rank === 1 ? 'border-purple-100 bg-purple-50/50' : 'border-gray-100 bg-gray-50/50'}`}>
                <div className="flex items-center gap-4">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${h.rank === 1 ? 'bg-purple-100 text-purple-600' : 'bg-white text-gray-400 border border-gray-200'}`}>
                    {h.rank}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-gray-900">{h.time}</p>
                    <p className="text-[10px] text-gray-500 font-medium">{h.val} visitors</p>
                  </div>
                </div>
                <Moon className={`w-4 h-4 ${h.rank === 1 ? 'text-purple-500' : 'text-gray-300'}`} />
              </div>
            )) : <div className="text-xs text-gray-400 p-3 text-center">No traffic data yet</div>}
          </div>
        </div>

        {/* Zone Distribution */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 flex flex-col">
          <div className="mb-4">
            <h2 className="text-sm font-bold text-gray-900">Zone Distribution</h2>
            <p className="text-[11px] text-gray-500 mt-0.5">Visits by zone — from CCTV tracking</p>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center">
            {ZONE_DIST.length === 0 ? (
              <EmptyState
                icon={TrendingUp}
                title="No Zone Data Yet"
                description="Zone visits appear here once CCTV cameras detect and track visitors."
              />
            ) : (
              <>
                <div className="h-32 w-full mb-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={ZONE_DIST} dataKey="value" cx="50%" cy="50%" innerRadius={35} outerRadius={55} paddingAngle={2}>
                        {ZONE_DIST.map((entry: any, index: number) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-[10px] font-bold text-gray-500">
                  {ZONE_DIST.map((z: any) => (
                    <div key={z.name} className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: z.fill }} /> {z.name}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

      </div>

      {/* Zone Analytics Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 overflow-x-auto">
        <div className="mb-6">
          <h2 className="text-sm font-bold text-gray-900">Zone Analytics</h2>
          <p className="text-[11px] text-gray-500 mt-0.5">Detailed breakdown by store zone</p>
        </div>
      {ZONE_DIST.length === 0 ? (
          <EmptyState
            icon={TrendingUp}
            title="No Zone Analytics Yet"
            description="Zone analytics will populate here once the CCTV pipeline detects and tracks visitors through configured zones."
          />
        ) : (
        <table className="w-full min-w-[600px] text-left">
          <thead>
            <tr className="border-b border-gray-100 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
              <th className="pb-3 font-bold">Zone</th>
              <th className="pb-3 font-bold text-right">Visits</th>
              <th className="pb-3 font-bold text-right">Avg Dwell</th>
              <th className="pb-3 font-bold text-right">Share</th>
              <th className="pb-3 font-bold w-48 pl-6">Distribution</th>
            </tr>
          </thead>
          <tbody className="text-xs font-bold text-gray-700">
            {ZONE_DIST.map((z: any) => {
              const share = totalZoneVisits > 0 ? ((z.value / totalZoneVisits) * 100).toFixed(1) + "%" : "0%";
              
              // format time
              let timeStr = "0s";
              if (z.avg_dwell_seconds) {
                if (z.avg_dwell_seconds < 60) timeStr = `${Math.round(z.avg_dwell_seconds)}s`;
                else timeStr = `${(z.avg_dwell_seconds / 60).toFixed(1)}m`;
              }
              
              return (
                <tr key={z.name} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                  <td className="py-3 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: z.fill }} /> {z.name}
                  </td>
                  <td className="py-3 text-right">{z.value}</td>
                  <td className="py-3 text-right">{timeStr}</td>
                  <td className="py-3 text-right text-gray-500">{share}</td>
                  <td className="py-3 pl-6">
                    <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: share, backgroundColor: z.fill }} />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        )}
      </div>

    </div>
  );
}
