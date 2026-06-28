"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, Skeleton, EmptyState, Badge } from "@/components/ui/index";
import { StatCard } from "@/components/ui/stat-card";
import { ShoppingCart, Users, Clock, TrendingUp } from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { todayISO } from "@/lib/utils";

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-card px-3 py-2 text-xs">
      <p className="text-white/60 mb-1">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-white/80">{p.name}: <strong>{p.value}</strong></span>
        </div>
      ))}
    </div>
  );
};

export default function CheckoutPage() {
  const today = todayISO();

  const { data: camerasData } = useQuery({ queryKey: ["cameras"], queryFn: () => api.getCameras() });
  const cameras = camerasData?.cameras;

  // Checkout uses queue analytics on "checkout" zones
  const checkoutCamera = cameras?.find((c: any) =>
    c.zone_config?.zones?.some((z: any) => z.zone_type === "checkout")
  );

  const { data: queueData, isLoading } = useQuery({
    queryKey: ["checkout-queue", checkoutCamera?.id, today],
    queryFn:  () => api.getQueue(checkoutCamera!.id, { zone_name: "checkout", target_date: today }),
    enabled:  !!checkoutCamera,
    refetchInterval: 30_000,
  });

  const { data: hourly, isLoading: hourlyLoading } = useQuery({
    queryKey: ["hourly", today],
    queryFn:  () => api.getHourlyTraffic({ target_date: today }),
    refetchInterval: 60_000,
  });

  const snapshots = queueData?.snapshots ?? [];
  const avgWait   = snapshots.length
    ? snapshots.reduce((a: number, s: any) => a + (s.avg_wait_seconds ?? 0), 0) / snapshots.length
    : 0;

  return (
    <div className="space-y-6 animate-slide-up">

      {!checkoutCamera && !isLoading && (
        <div className="px-4 py-3 rounded-xl border border-amber-500/25 bg-amber-500/10 text-amber-300 text-sm">
          No checkout zone detected. Configure a zone with type <strong>checkout</strong> in{" "}
          <a href="/cameras" className="underline">Camera Settings →</a>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Checkout Visitors"
          value={snapshots.length}
          subtitle="Snapshots today"
          icon={ShoppingCart}
          color="blue"
          format="number"
          loading={isLoading}
        />
        <StatCard
          title="Peak Queue"
          value={queueData?.peak_queue ?? 0}
          subtitle="Max at once"
          icon={Users}
          color="rose"
          format="number"
          loading={isLoading}
        />
        <StatCard
          title="Avg Wait Time"
          value={avgWait}
          subtitle="Per customer"
          icon={Clock}
          color="amber"
          format="duration"
          loading={isLoading}
        />
        <StatCard
          title="Avg Queue Depth"
          value={queueData?.avg_queue_depth ?? 0}
          subtitle="Throughout day"
          icon={TrendingUp}
          color="violet"
          loading={isLoading}
        />
      </div>

      {/* Checkout queue over time */}
      <Card
        title="Checkout Queue Trend"
        description="Queue depth at the checkout zone"
        action={<Badge variant="info">Live</Badge>}
      >
        {isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : !snapshots.length ? (
          <EmptyState
            icon={ShoppingCart}
            title="No checkout data yet"
            description="Configure a checkout zone and start the CV pipeline to see data here"
          />
        ) : (
          <ResponsiveContainer width="100%" height={224}>
            <AreaChart data={snapshots} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="checkoutGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="time" tick={{ fontSize: 9, fill: "rgba(255,255,255,0.3)" }} />
              <YAxis tick={{ fontSize: 10, fill: "rgba(255,255,255,0.3)" }} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="queue_depth"
                stroke="#3b82f6"
                strokeWidth={2}
                fill="url(#checkoutGrad)"
                name="Queue Depth"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Traffic context */}
      <Card title="Store Traffic Context" description="Total entries vs checkout activity">
        {hourlyLoading ? <Skeleton className="h-48 w-full" /> :
          !hourly?.length ? <EmptyState icon={TrendingUp} title="No hourly data" /> : (
            <ResponsiveContainer width="100%" height={192}>
              <AreaChart data={hourly} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                <defs>
                  <linearGradient id="entriesGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "rgba(255,255,255,0.3)" }} />
                <YAxis tick={{ fontSize: 10, fill: "rgba(255,255,255,0.3)" }} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="entries" stroke="#8b5cf6" strokeWidth={2} fill="url(#entriesGrad)" name="Entries" />
              </AreaChart>
            </ResponsiveContainer>
          )
        }
      </Card>
    </div>
  );
}
