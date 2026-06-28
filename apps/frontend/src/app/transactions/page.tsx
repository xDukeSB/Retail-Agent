"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend
} from "recharts";
import {
  ShoppingCart, CreditCard, Smartphone, Banknote, Users, TrendingUp,
  CheckCircle2, Clock, Activity, Zap, BarChart3, AlertCircle
} from "lucide-react";
import { api, WS_LIVE_URL } from "@/lib/api";
import { StatCard } from "@/components/ui/stat-card";
import { todayISO } from "@/lib/utils";

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATE_LABELS: Record<string, string> = {
  ENTERED_STORE: "In Store",
  SHOPPING: "Shopping",
  MOVING_TO_CHECKOUT: "Moving to Checkout",
  WAITING_IN_QUEUE: "Waiting in Queue",
  AT_CHECKOUT: "At Checkout",
  PAYMENT_INTERACTION: "Paying",
  PURCHASE_COMPLETED: "Purchased",
  EXITED_STORE: "Exited",
};

const STATE_COLORS: Record<string, string> = {
  ENTERED_STORE: "#6b7280",
  SHOPPING: "#3b82f6",
  MOVING_TO_CHECKOUT: "#f59e0b",
  WAITING_IN_QUEUE: "#f97316",
  AT_CHECKOUT: "#ec4899",
  PAYMENT_INTERACTION: "#8b5cf6",
  PURCHASE_COMPLETED: "#10b981",
  EXITED_STORE: "#374151",
};

const LEVEL_CONFIG: Record<string, { color: string; bg: string; border: string; dot: string }> = {
  HIGH:     { color: "#10b981", bg: "bg-emerald-50", border: "border-emerald-200", dot: "bg-emerald-500" },
  MEDIUM:   { color: "#f59e0b", bg: "bg-amber-50", border: "border-amber-200", dot: "bg-amber-500" },
  LOW:      { color: "#f97316", bg: "bg-orange-50", border: "border-orange-200", dot: "bg-orange-400" },
  UNLIKELY: { color: "#9ca3af", bg: "bg-gray-50", border: "border-gray-200", dot: "bg-gray-400" },
};

const SIGNAL_LABELS: Record<string, string> = {
  checkout_zone_entered: "Checkout Zone",
  queue_completed: "Queue Completed",
  cash_exchange_detected: "Cash Exchange",
  card_machine_interaction: "Card Payment",
  upi_payment_interaction: "UPI / QR",
};

const SIGNAL_ICONS: Record<string, any> = {
  checkout_zone_entered: ShoppingCart,
  queue_completed: CheckCircle2,
  cash_exchange_detected: Banknote,
  card_machine_interaction: CreditCard,
  upi_payment_interaction: Smartphone,
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ConfidenceMeter({ probability, level }: { probability: number; level: string }) {
  const cfg = LEVEL_CONFIG[level] || LEVEL_CONFIG.UNLIKELY;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className={`text-[10px] font-bold uppercase tracking-widest`} style={{ color: cfg.color }}>
          {level}
        </span>
        <span className="text-[10px] font-mono text-gray-500">{probability.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${probability}%`, background: cfg.color }}
        />
      </div>
    </div>
  );
}

function SignalBadge({ signal }: { signal: string }) {
  const Icon = SIGNAL_ICONS[signal] || Activity;
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-100">
      <Icon className="w-2.5 h-2.5" />
      {SIGNAL_LABELS[signal] || signal}
    </span>
  );
}

function LiveSessionRow({ session }: { session: any }) {
  const stateColor = STATE_COLORS[session.state] || "#6b7280";
  const levelCfg = LEVEL_CONFIG[session.confidence_level] || LEVEL_CONFIG.UNLIKELY;
  const dwellMin = Math.floor(session.dwell_seconds / 60);
  const dwellSec = Math.floor(session.dwell_seconds % 60);

  return (
    <div className="flex items-start justify-between gap-4 py-3 px-4 border-b border-gray-100 last:border-0 hover:bg-gray-50/50 transition-colors">
      <div className="flex items-center gap-3">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
          style={{ background: stateColor }}
        >
          #{session.track_id}
        </div>
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-bold text-gray-900">{STATE_LABELS[session.state] || session.state}</span>
            <span
              className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-widest border ${levelCfg.bg} ${levelCfg.border}`}
              style={{ color: levelCfg.color }}
            >
              {session.confidence_level}
            </span>
          </div>
          <div className="flex items-center flex-wrap gap-1">
            {session.detected_signals.map((s: string) => (
              <SignalBadge key={s} signal={s} />
            ))}
            {session.detected_signals.length === 0 && (
              <span className="text-[10px] text-gray-400">No signals yet</span>
            )}
          </div>
        </div>
      </div>
      <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
        <ConfidenceMeter probability={session.transaction_probability} level={session.confidence_level} />
        <span className="text-[10px] text-gray-400 font-mono">
          {dwellMin > 0 ? `${dwellMin}m ` : ""}{dwellSec}s
        </span>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function TransactionsPage() {
  const today = todayISO();
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [lastWsEvent, setLastWsEvent] = useState<string | null>(null);

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data: liveData, isLoading: liveLoading } = useQuery({
    queryKey: ["txn_live"],
    queryFn: () => api.getTxnLiveSessions(),
    refetchInterval: 3_000,
  });

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["txn_stats", today],
    queryFn: () => api.getTxnStats({ target_date: today }),
    refetchInterval: 15_000,
  });

  const { data: funnelData, isLoading: funnelLoading } = useQuery({
    queryKey: ["txn_funnel", today],
    queryFn: () => api.getTxnFunnel({ target_date: today }),
    refetchInterval: 30_000,
  });

  const { data: distData, isLoading: distLoading } = useQuery({
    queryKey: ["txn_dist", today],
    queryFn: () => api.getTxnDistribution({ target_date: today }),
    refetchInterval: 30_000,
  });

  const { data: timelineData } = useQuery({
    queryKey: ["txn_timeline"],
    queryFn: () => api.getTxnTimeline(15),
    refetchInterval: 5_000,
  });

  const { data: queueData } = useQuery({
    queryKey: ["txn_queue", today],
    queryFn: () => api.getTxnQueueMetrics({ target_date: today }),
    refetchInterval: 30_000,
  });

  // ── WebSocket for real-time updates ────────────────────────────────────────
  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket(WS_LIVE_URL);
        wsRef.current = ws;
        ws.onopen = () => setWsConnected(true);
        ws.onclose = () => {
          setWsConnected(false);
          setTimeout(connect, 3000);
        };
        ws.onerror = () => ws.close();
        ws.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data.type === "transaction_update") {
              setLastWsEvent(new Date().toLocaleTimeString());
              // Invalidate live session query to trigger re-fetch
              queryClient.invalidateQueries({ queryKey: ["txn_live"] });
            }
          } catch {}
        };
        ws.onopen = () => {
          setWsConnected(true);
          ws.send("ping");
        };
      } catch {}
    };

    connect();
    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 25_000);
    return () => {
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, [queryClient]);

  const liveSessions = liveData?.sessions ?? [];
  const funnel = funnelData?.funnel ?? [];
  const topFunnelCount = funnel[0]?.count ?? 1;

  const paymentDist = stats?.payment_type_distribution ?? {};
  const paymentPieData = [
    { name: "Cash", value: paymentDist.cash || 0, fill: "#10b981" },
    { name: "Card", value: paymentDist.card || 0, fill: "#3b82f6" },
    { name: "UPI / QR", value: paymentDist.upi || 0, fill: "#8b5cf6" },
  ].filter(d => d.value > 0);

  const confDistribution = distData?.distribution ?? [];

  return (
    <div className="space-y-6 animate-slide-up max-w-[1600px]">

      {/* Header Status Bar */}
      <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl px-5 py-3 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-400'}`} />
            <span className="text-xs font-bold text-gray-700">
              {wsConnected ? 'Live Feed Active' : 'Reconnecting...'}
            </span>
          </div>
          {lastWsEvent && (
            <span className="text-[10px] text-gray-400">Last event: {lastWsEvent}</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[10px] text-gray-500 font-medium">
          <span className="flex items-center gap-1"><Activity className="w-3 h-3 text-emerald-500" /> Offline-First Active</span>
          <span>•</span>
          <span>All inference runs locally</span>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Live Sessions"
          value={liveData?.total ?? 0}
          subtitle={`${liveData?.at_checkout ?? 0} at checkout now`}
          icon={Users}
          color="blue"
          format="number"
          loading={liveLoading}
        />
        <StatCard
          title="Likely Purchases"
          value={stats?.likely_purchases ?? 0}
          subtitle="Medium/High confidence today"
          icon={ShoppingCart}
          color="emerald"
          format="number"
          loading={statsLoading}
        />
        <StatCard
          title="Est. Conversion Rate"
          value={stats?.estimated_conversion_rate ?? 0}
          subtitle="Entries → likely purchases"
          icon={TrendingUp}
          color="violet"
          format="percent"
          loading={statsLoading}
        />
        <StatCard
          title="Avg Confidence"
          value={stats?.avg_confidence ?? 0}
          subtitle="Transaction probability score"
          icon={BarChart3}
          color="amber"
          format="percent"
          loading={statsLoading}
        />
      </div>

      {/* Live Sessions + Timeline */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

        {/* Live Session State Machine View */}
        <div className="xl:col-span-2 bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-500" />
                Live Transaction Sessions
              </h2>
              <p className="text-[10px] text-gray-500 mt-0.5">State machine tracking every active visitor</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-gray-500">{liveSessions.length} active</span>
              <div className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-gray-300'}`} />
            </div>
          </div>
          <div className="overflow-y-auto max-h-[400px]">
            {liveLoading ? (
              <div className="p-6 space-y-3">
                {[1,2,3].map(i => <div key={i} className="h-16 rounded-lg bg-gray-100 animate-pulse" />)}
              </div>
            ) : liveSessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Users className="w-8 h-8 text-gray-200" />
                <p className="text-sm font-medium text-gray-400">No active visitors</p>
                <p className="text-[10px] text-gray-300">Sessions appear here when cameras detect visitors</p>
              </div>
            ) : (
              liveSessions.map((s: any) => <LiveSessionRow key={s.session_id} session={s} />)
            )}
          </div>
        </div>

        {/* Signal Timeline */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-500" />
              Signal Timeline
            </h2>
            <p className="text-[10px] text-gray-500 mt-0.5">Recent transaction signals detected</p>
          </div>
          <div className="overflow-y-auto max-h-[400px] p-3">
            {(timelineData?.events ?? []).length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 gap-2">
                <AlertCircle className="w-6 h-6 text-gray-200" />
                <p className="text-xs text-gray-400">No signals yet today</p>
              </div>
            ) : (
              <div className="space-y-2">
                {(timelineData?.events ?? []).map((ev: any) => {
                  const Icon = SIGNAL_ICONS[ev.signal_type] || Activity;
                  const t = new Date(ev.detected_at);
                  return (
                    <div key={ev.id} className="flex items-start gap-3 p-2.5 rounded-lg border border-gray-100 hover:border-gray-200 transition-colors">
                      <div className="w-6 h-6 rounded-md bg-gray-50 flex items-center justify-center flex-shrink-0 text-base mt-0.5">
                        {ev.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[11px] font-bold text-gray-800 truncate">{ev.label}</span>
                          <span className="text-[9px] font-mono text-gray-400 flex-shrink-0">
                            +{ev.score}pts
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {ev.zone_name && (
                            <span className="text-[9px] text-gray-400">Zone: {ev.zone_name}</span>
                          )}
                          {ev.metadata?.dwell_seconds && (
                            <span className="text-[9px] text-gray-400">• {ev.metadata.dwell_seconds}s dwell</span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <Clock className="w-2.5 h-2.5 text-gray-300" />
                          <span className="text-[9px] text-gray-400">
                            {t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Checkout Funnel + Payment Distribution */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

        {/* Transaction Funnel */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-bold text-gray-900">Transaction Funnel</h2>
            <p className="text-[10px] text-gray-500 mt-0.5">Visitor progression through purchase journey</p>
          </div>
          <div className="p-5 space-y-2.5">
            {funnelLoading ? (
              <div className="space-y-2">
                {[1,2,3,4,5,6].map(i => <div key={i} className="h-10 rounded-lg bg-gray-100 animate-pulse" />)}
              </div>
            ) : funnel.length === 0 ? (
              <div className="py-12 text-center text-sm text-gray-400">No funnel data yet today</div>
            ) : funnel.map((stage: any) => {
              const widthPct = topFunnelCount > 0 ? (stage.count / topFunnelCount) * 100 : 0;
              return (
                <div key={stage.stage}>
                  <div className="flex items-center justify-between text-[10px] mb-1">
                    <span className="font-bold text-gray-700">{stage.stage}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400">{stage.rate}%</span>
                      <span className="font-bold text-gray-900">{stage.count.toLocaleString()}</span>
                    </div>
                  </div>
                  <div className="h-8 rounded-lg bg-gray-50 overflow-hidden border border-gray-100">
                    <div
                      className="h-full rounded-lg flex items-center px-2.5 transition-all duration-700"
                      style={{ width: `${widthPct}%`, background: stage.color, minWidth: stage.count > 0 ? "24px" : "0" }}
                    >
                      {widthPct > 15 && (
                        <span className="text-[10px] font-bold text-white">{stage.count.toLocaleString()}</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Confidence Distribution + Payment Types */}
        <div className="space-y-5">

          {/* Confidence Distribution */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-bold text-gray-900">Confidence Distribution</h2>
              <p className="text-[10px] text-gray-500 mt-0.5">Session breakdown by purchase likelihood</p>
            </div>
            <div className="p-5">
              {distLoading ? (
                <div className="space-y-2">
                  {[1,2,3,4].map(i => <div key={i} className="h-8 rounded-lg bg-gray-100 animate-pulse" />)}
                </div>
              ) : (
                <div className="space-y-2.5">
                  {confDistribution.map((d: any) => (
                    <div key={d.level}>
                      <div className="flex items-center justify-between text-[10px] mb-1">
                        <span className="font-bold" style={{ color: d.color }}>{d.label}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-400">{d.share}%</span>
                          <span className="font-bold text-gray-900">{d.count}</span>
                        </div>
                      </div>
                      <div className="h-5 rounded-md bg-gray-50 overflow-hidden">
                        <div
                          className="h-full rounded-md transition-all duration-700"
                          style={{ width: `${d.share}%`, background: d.color, minWidth: d.count > 0 ? "8px" : "0" }}
                        />
                      </div>
                    </div>
                  ))}
                  {confDistribution.length === 0 && (
                    <div className="py-6 text-center text-sm text-gray-400">No completed sessions yet</div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Payment Type Distribution */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-bold text-gray-900">Payment Type Estimation</h2>
              <p className="text-[10px] text-gray-500 mt-0.5">Inferred from zone interaction signals</p>
            </div>
            <div className="p-5">
              {paymentPieData.length === 0 ? (
                <div className="py-8 text-center text-sm text-gray-400">No payment signals detected yet</div>
              ) : (
                <div className="flex items-center gap-6">
                  <ResponsiveContainer width={120} height={120}>
                    <PieChart>
                      <Pie
                        data={paymentPieData}
                        cx={55}
                        cy={55}
                        innerRadius={35}
                        outerRadius={55}
                        dataKey="value"
                        strokeWidth={0}
                      >
                        {paymentPieData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex-1 space-y-2">
                    {paymentPieData.map((d) => {
                      const Icon = d.name === "Cash" ? Banknote : d.name === "Card" ? CreditCard : Smartphone;
                      const total = paymentPieData.reduce((a, x) => a + x.value, 0) || 1;
                      return (
                        <div key={d.name} className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            <div className="w-2 h-2 rounded-full" style={{ background: d.fill }} />
                            <Icon className="w-3 h-3 text-gray-500" />
                            <span className="text-xs font-medium text-gray-700">{d.name}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400">{Math.round(d.value / total * 100)}%</span>
                            <span className="text-xs font-bold text-gray-900">{d.value}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Queue Metrics + Secondary Stats */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Queue Completions"
          value={queueData?.queue_completions ?? 0}
          subtitle="Visitors who completed queue"
          icon={CheckCircle2}
          color="emerald"
          format="number"
        />
        <StatCard
          title="Queue Success Rate"
          value={queueData?.queue_success_rate ?? 0}
          subtitle="Queue → Checkout conversion"
          icon={TrendingUp}
          color="blue"
          format="percent"
        />
        <StatCard
          title="Checkout Abandonment"
          value={stats?.checkout_abandonment ?? 0}
          subtitle="Reached checkout, didn't buy"
          icon={AlertCircle}
          color="rose"
          format="number"
          loading={statsLoading}
        />
        <StatCard
          title="Payment Interactions"
          value={(paymentDist.cash ?? 0) + (paymentDist.card ?? 0) + (paymentDist.upi ?? 0)}
          subtitle="Total payment signals detected"
          icon={CreditCard}
          color="violet"
          format="number"
          loading={statsLoading}
        />
      </div>

      {/* Completed Sessions Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-gray-900">Today's Completed Sessions</h2>
            <p className="text-[10px] text-gray-500 mt-0.5">All transaction sessions that have exited — persisted to local database</p>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-gray-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
            Local-first · Cloud synced
          </div>
        </div>
        <CompletedSessionsTable today={today} />
      </div>

    </div>
  );
}

// ── Completed Sessions Sub-Component ─────────────────────────────────────────

function CompletedSessionsTable({ today }: { today: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["txn_sessions", today],
    queryFn: () => api.getTxnSessions({ target_date: today, limit: 30 }),
    refetchInterval: 10_000,
  });

  const sessions = data?.sessions ?? [];

  if (isLoading) {
    return (
      <div className="p-6 space-y-2">
        {[1,2,3,4,5].map(i => <div key={i} className="h-10 rounded-lg bg-gray-100 animate-pulse" />)}
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <ShoppingCart className="w-8 h-8 text-gray-200" />
        <p className="text-sm font-medium text-gray-400">No completed sessions yet today</p>
        <p className="text-[10px] text-gray-300">Sessions are written here when a visitor exits the frame</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50/50">
            <th className="text-left py-3 px-4 font-bold text-gray-400 text-[10px] uppercase tracking-wider">Track</th>
            <th className="text-left py-3 px-4 font-bold text-gray-400 text-[10px] uppercase tracking-wider">Final State</th>
            <th className="text-left py-3 px-4 font-bold text-gray-400 text-[10px] uppercase tracking-wider">Confidence</th>
            <th className="text-left py-3 px-4 font-bold text-gray-400 text-[10px] uppercase tracking-wider">Signals</th>
            <th className="text-left py-3 px-4 font-bold text-gray-400 text-[10px] uppercase tracking-wider">Duration</th>
            <th className="text-left py-3 px-4 font-bold text-gray-400 text-[10px] uppercase tracking-wider">Time</th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s: any) => {
            const levelCfg = LEVEL_CONFIG[s.confidence_level] || LEVEL_CONFIG.UNLIKELY;
            const enteredAt = new Date(s.entered_at);
            const exitedAt = s.exited_at ? new Date(s.exited_at) : null;
            const durationSec = exitedAt ? Math.round((exitedAt.getTime() - enteredAt.getTime()) / 1000) : null;
            const durMin = durationSec !== null ? Math.floor(durationSec / 60) : 0;
            const durSec = durationSec !== null ? durationSec % 60 : 0;

            return (
              <tr key={s.id} className="border-b border-gray-50 hover:bg-gray-50/30">
                <td className="py-3 px-4 font-mono font-bold text-gray-700">#{s.track_id}</td>
                <td className="py-3 px-4">
                  <span
                    className="px-1.5 py-0.5 rounded text-[9px] font-bold text-white"
                    style={{ background: STATE_COLORS[s.state] || "#6b7280" }}
                  >
                    {STATE_LABELS[s.state] || s.state}
                  </span>
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-col gap-0.5 min-w-[80px]">
                    <span className="text-[10px] font-bold" style={{ color: levelCfg.color }}>{s.confidence_level}</span>
                    <div className="h-1 rounded-full bg-gray-100 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${s.transaction_probability}%`, background: levelCfg.color }} />
                    </div>
                    <span className="text-[9px] text-gray-400">{s.transaction_probability.toFixed(1)}%</span>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-wrap gap-1">
                    {s.detected_signals.map((sig: string) => (
                      <SignalBadge key={sig} signal={sig} />
                    ))}
                    {s.detected_signals.length === 0 && <span className="text-[10px] text-gray-300">—</span>}
                  </div>
                </td>
                <td className="py-3 px-4 font-mono text-gray-500 text-[10px]">
                  {durationSec !== null ? `${durMin > 0 ? `${durMin}m ` : ""}${durSec}s` : "—"}
                </td>
                <td className="py-3 px-4 text-gray-400 text-[10px] font-mono">
                  {enteredAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
