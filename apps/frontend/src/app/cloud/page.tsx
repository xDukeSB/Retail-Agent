"use client";

import { Store, Wifi, AlertTriangle, WifiOff, RefreshCcw, Activity } from "lucide-react";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Skeleton, EmptyState } from "@/components/ui/index";
import { formatDuration } from "@/lib/utils";

export default function CloudDashboardPage() {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 1000);
  };

  const { data: cloudData, isLoading } = useQuery({
    queryKey: ["cloud"],
    queryFn: () => api.getCloudDashboard(),
    refetchInterval: 30_000,
  });

  const chartData = cloudData?.stores?.map((s: any) => ({ 
    name: s.name, 
    visitors: s.metrics?.today_entries || 0 
  })) || [];

  return (
    <div className="max-w-[1600px] mx-auto pb-10 space-y-6">
      
      {/* KPI Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center mb-2">
            <Store className="w-4 h-4 text-blue-500" />
          </div>
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Total Stores</div>
          <div className="text-xl font-bold text-gray-900">{cloudData?.total_stores ?? 0}</div>
        </div>
        
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="w-8 h-8 rounded-full bg-emerald-50 flex items-center justify-center mb-2">
            <Wifi className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Online</div>
          <div className="text-xl font-bold text-gray-900">{cloudData?.online_stores ?? 0}</div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="w-8 h-8 rounded-full bg-amber-50 flex items-center justify-center mb-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Stale</div>
          <div className="text-xl font-bold text-gray-900">{cloudData?.stale_stores ?? 0}</div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="w-8 h-8 rounded-full bg-rose-50 flex items-center justify-center mb-2">
            <WifiOff className="w-4 h-4 text-rose-500" />
          </div>
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Offline</div>
          <div className="text-xl font-bold text-gray-900">{cloudData?.offline_stores ?? 0}</div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="w-8 h-8 rounded-full bg-indigo-50 flex items-center justify-center mb-2">
            <RefreshCcw className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Pending Sync</div>
          <div className="text-xl font-bold text-gray-900">{cloudData?.pending_events ?? 0}</div>
        </div>
      </div>

      {/* Multi-Store Comparison Chart */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-sm font-bold text-gray-900">Multi-Store Comparison</h2>
            <p className="text-[11px] text-gray-500 mt-0.5">Today's visitors across all stores</p>
          </div>
          <div className="text-xs font-bold text-gray-600">Total {chartData.reduce((sum: number, curr: any) => sum + curr.visitors, 0)} visitors</div>
        </div>
        <div className="h-[250px] w-full">
          {isLoading ? (
            <Skeleton className="h-full w-full" />
          ) : chartData.length === 0 ? (
            <EmptyState icon={Store} title="No Store Data" description="No stores have reported data yet." />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 20, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#9ca3af', fontWeight: 600 }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#9ca3af', fontWeight: 600 }} dx={-10} domain={[0, 'auto']} />
                <Tooltip cursor={{ fill: '#f3f4f6' }} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                <Bar dataKey="visitors" fill="#15803d" radius={[4, 4, 0, 0]} barSize={120} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Data Freshness Alert */}
      <div className="bg-purple-50 border border-purple-100 rounded-xl shadow-sm p-4 flex items-start sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <Activity className="w-5 h-5 text-purple-600 mt-0.5" />
          <div>
            <h3 className="text-xs font-bold text-purple-900">Data Freshness — Mandatory</h3>
            <p className="text-[11px] text-purple-700/80 mt-0.5 font-medium">Every store card displays last sync time, last heartbeat, and freshness status. Users must never mistake stale data for live data.</p>
          </div>
        </div>
        <button 
          onClick={handleRefresh}
          className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 bg-white border border-gray-200 rounded-lg text-xs font-bold text-gray-700 shadow-sm hover:bg-gray-50 transition-colors"
        >
          <RefreshCcw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} /> 
          {isRefreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* Store Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {isLoading ? (
          [1, 2, 3].map(i => <Skeleton key={i} className="h-80 w-full rounded-xl" />)
        ) : !cloudData?.stores || cloudData.stores.length === 0 ? (
           <div className="col-span-full">
             <EmptyState icon={Store} title="No Stores Found" description="Connect an edge agent to the cloud dashboard." />
           </div>
        ) : (
          cloudData.stores.map((store: any) => {
            const isOnline = store.status === 'online';
            const isStale = store.status === 'stale';
            
            const colorClass = isOnline ? 'emerald' : isStale ? 'amber' : 'rose';
            
            return (
              <div key={store.id} className={`bg-white border-l-4 border-l-${colorClass}-500 border-y border-r border-gray-200 rounded-xl shadow-sm flex flex-col`}>
                <div className="p-5 flex-1">
                  <div className="flex justify-between items-start mb-6">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">{store.name}</h3>
                      <p className="text-[10px] text-gray-500 mt-0.5">{store.id}</p>
                    </div>
                    <div className={`flex items-center gap-1.5 px-2 py-1 bg-${colorClass}-50 border border-${colorClass}-100 rounded-full text-[9px] font-bold text-${colorClass}-600 uppercase tracking-widest`}>
                      <span className={`w-1.5 h-1.5 rounded-full bg-${colorClass}-500`} /> {store.status}
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-y-6 gap-x-4 mb-6">
                    <div>
                      <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Last Sync</div>
                      <div className="text-xs font-bold text-gray-900">{store.last_sync_time ? new Date(store.last_sync_time).toLocaleTimeString() : 'Never'}</div>
                    </div>
                    <div>
                      <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Heartbeat</div>
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full bg-${colorClass}-500`} />
                        <span className="text-xs font-bold text-gray-900">{store.last_heartbeat_time ? new Date(store.last_heartbeat_time).toLocaleTimeString() : 'Never'}</span>
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Visitors</div>
                      <div className="text-sm font-bold text-gray-900">{store.metrics?.today_entries ?? 0}</div>
                    </div>
                    <div>
                      <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Avg Dwell</div>
                      <div className="text-sm font-bold text-gray-900">{store.metrics?.avg_dwell_time ? formatDuration(store.metrics.avg_dwell_time) : '0m'}</div>
                    </div>
                    <div>
                      <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Conversion</div>
                      <div className="text-sm font-bold text-gray-900">{store.metrics?.conversion_rate ? `${(store.metrics.conversion_rate * 100).toFixed(1)}%` : '0%'}</div>
                    </div>
                    <div>
                      <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1">Health</div>
                      <div className="text-sm font-bold text-gray-900">{store.metrics?.health_score ?? 0}</div>
                    </div>
                  </div>
                </div>
                <div className={`px-5 py-4 border-t border-gray-100 flex items-center justify-between bg-gray-50/50 rounded-b-xl`}>
                  <div className={`flex items-center gap-1.5 text-[10px] font-bold text-${colorClass}-600`}>
                    <RefreshCcw className="w-3 h-3" /> Updated just now
                  </div>
                  <Link href="/" className="text-[10px] font-bold text-gray-700 hover:text-emerald-600">View Store</Link>
                </div>
              </div>
            );
          })
        )}
      </div>

    </div>
  );
}
