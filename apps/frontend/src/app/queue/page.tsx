"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import { Card, Skeleton, EmptyState, Badge } from "@/components/ui/index";
import { StatCard } from "@/components/ui/stat-card";
import { Users, Clock, AlertTriangle, TrendingUp } from "lucide-react";
import { todayISO, cn, formatDuration } from "@/lib/utils";

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

export default function QueuePage() {
  const [selectedCamera, setSelectedCamera] = useState<string>("");
  const today = todayISO();

  const { data: camerasData } = useQuery<any>({
    queryKey: ["cameras"],
    queryFn: () => api.getCameras(),
  });
  const cameras = camerasData?.cameras;

  useEffect(() => {
    if (cameras && cameras.length > 0 && !selectedCamera) setSelectedCamera(cameras[0].id);
  }, [cameras]);

  const { data: queue, isLoading } = useQuery({
    queryKey: ["queue", selectedCamera, today],
    queryFn: () => api.getQueue(selectedCamera, { target_date: today }),
    enabled: !!selectedCamera,
    refetchInterval: 30_000,
  });

  const peakQueue = queue?.peak_queue ?? 0;
  const avgDepth = queue?.avg_queue_depth ?? 0;
  const snapshots = queue?.snapshots ?? [];
  const avgWait = snapshots.length
    ? snapshots.reduce((a: number, s: any) => a + (s.avg_wait_seconds ?? 0), 0) / snapshots.length
    : 0;

  return (
    <div className="space-y-6 animate-slide-up">

      {/* Camera picker */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-white/40">Camera:</span>
        <div className="flex gap-2 flex-wrap">
          {cameras?.map((cam: any) => (
            <button
              key={cam.id}
              onClick={() => setSelectedCamera(cam.id)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
                selectedCamera === cam.id
                  ? "bg-blue-500/20 text-blue-400 border-blue-500/30"
                  : "text-white/40 border-white/[0.08] hover:text-white/70"
              )}
            >
              {cam.name}
            </button>
          ))}
          {!cameras?.length && <span className="text-xs text-white/30">No cameras</span>}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Current Queue"
          value={peakQueue}
          subtitle="Live depth"
          icon={Users}
          color="blue"
          format="number"
          loading={isLoading}
        />
        <StatCard
          title="Avg Queue Depth"
          value={avgDepth.toFixed(1)}
          subtitle="Today's average"
          icon={TrendingUp}
          color="violet"
          loading={isLoading}
        />
        <StatCard
          title="Avg Wait Time"
          value={avgWait}
          subtitle="Per customer"
          icon={Clock}
          color="emerald"
          format="duration"
          loading={isLoading}
        />
        <StatCard
          title="Peak Queue"
          value={peakQueue}
          subtitle="Highest today"
          icon={AlertTriangle}
          color={peakQueue > 10 ? "rose" : peakQueue > 5 ? "amber" : "emerald"}
          format="number"
          loading={isLoading}
        />
      </div>

      {/* Queue depth over time */}
      <Card
        title="Queue Depth Over Time"
        description="People waiting in queue zones throughout the day"
        action={<Badge variant="info">Auto-refresh 30s</Badge>}
      >
        {isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : !snapshots.length ? (
          <EmptyState
            icon={Users}
            title="No queue data yet"
            description="Queue data appears once queue zones are configured and customers are detected"
          />
        ) : (
          <ResponsiveContainer width="100%" height={224}>
            <LineChart data={snapshots} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="time" tick={{ fontSize: 9, fill: "rgba(255,255,255,0.3)" }} />
              <YAxis tick={{ fontSize: 10, fill: "rgba(255,255,255,0.3)" }} />
              <Tooltip content={<CustomTooltip />} />
              {peakQueue > 5 && (
                <ReferenceLine y={5} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: "Threshold", fill: "#f59e0b", fontSize: 10 }} />
              )}
              <Line type="monotone" dataKey="queue_depth" stroke="#3b82f6" strokeWidth={2} dot={false} name="Queue Depth" />
              <Line type="monotone" dataKey="avg_wait_seconds" stroke="#10b981" strokeWidth={2} dot={false} name="Avg Wait (s)" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Queue breakdown table */}
      {snapshots.length > 0 && (
        <Card title="Queue Snapshots" description="Recent measurements">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  {["Time", "Zone", "Depth", "Avg Wait", "Max Wait"].map((h) => (
                    <th key={h} className="text-left py-2 pr-4 text-white/40 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {snapshots.slice(-20).reverse().map((s: any, i: number) => (
                  <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                    <td className="py-2 pr-4 text-white/60 font-mono">{s.time}</td>
                    <td className="py-2 pr-4 text-white/70">{s.zone_name ?? "—"}</td>
                    <td className="py-2 pr-4">
                      <span className={cn(
                        "font-semibold",
                        s.queue_depth > 8 ? "text-rose-400" :
                        s.queue_depth > 4 ? "text-amber-400" : "text-emerald-400"
                      )}>
                        {s.queue_depth}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-white/60">{s.avg_wait_seconds ? formatDuration(s.avg_wait_seconds) : "—"}</td>
                    <td className="py-2 pr-4 text-white/60">{s.max_wait_seconds ? formatDuration(s.max_wait_seconds) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
