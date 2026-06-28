"use client";

import { useQuery } from "@tanstack/react-query";
import {
  FunnelChart, Funnel, LabelList, Tooltip, ResponsiveContainer,
} from "recharts";
import { api } from "@/lib/api";
import { Card, Skeleton, EmptyState, Badge } from "@/components/ui/index";
import { StatCard } from "@/components/ui/stat-card";
import { TrendingUp, Users, ShoppingCart, ArrowDown } from "lucide-react";
import { todayISO, formatPercent } from "@/lib/utils";

export default function ConversionPage() {
  const today = todayISO();

  const { data: conversion, isLoading } = useQuery({
    queryKey: ["conversion", today],
    queryFn: () => api.getConversion({ target_date: today }),
    refetchInterval: 60_000,
  });

  const funnel = conversion?.funnel ?? [];
  const topStage = funnel[0]?.count ?? 1;
  const bottomRate = funnel[funnel.length - 1]?.rate ?? 0;

  const STAGE_COLORS = ["#3b82f6", "#8b5cf6", "#10b981"];

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <StatCard
          title="Store Entries"
          value={funnel[0]?.count ?? 0}
          subtitle="Walked in today"
          icon={Users}
          color="blue"
          format="number"
          loading={isLoading}
        />
        <StatCard
          title="Zone Browsers"
          value={funnel[1]?.count ?? 0}
          subtitle="Visited a zone"
          icon={TrendingUp}
          color="violet"
          format="number"
          loading={isLoading}
        />
        <StatCard
          title="Checkout Reach"
          value={funnel[2]?.count ?? 0}
          subtitle={`${bottomRate}% conversion`}
          icon={ShoppingCart}
          color="emerald"
          format="number"
          loading={isLoading}
        />
      </div>

      {/* Visual funnel */}
      <Card
        title="Conversion Funnel"
        description="Visitor journey from entry to checkout"
        action={<Badge variant="info">Today</Badge>}
      >
        {isLoading ? (
          <Skeleton className="h-72 w-full" />
        ) : !funnel.length ? (
          <EmptyState icon={TrendingUp} title="No conversion data yet" description="Data builds up throughout the day" />
        ) : (
          <div className="space-y-3 py-4">
            {funnel.map((stage: any, i: number) => {
              const widthPct = topStage > 0 ? (stage.count / topStage) * 100 : 0;
              const dropoff = i > 0 ? funnel[i - 1].count - stage.count : 0;
              return (
                <div key={stage.stage}>
                  {i > 0 && dropoff > 0 && (
                    <div className="flex items-center gap-2 my-2 ml-4">
                      <ArrowDown className="w-3 h-3 text-white/20" />
                      <span className="text-xs text-white/30">{dropoff} dropped off</span>
                    </div>
                  )}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-white/60 font-medium">{stage.stage}</span>
                      <div className="flex items-center gap-3">
                        <span className="text-white/40">{stage.rate}%</span>
                        <span className="font-semibold text-white">{stage.count.toLocaleString()}</span>
                      </div>
                    </div>
                    <div className="h-10 rounded-lg bg-white/[0.04] overflow-hidden relative">
                      <div
                        className="h-full rounded-lg transition-all duration-700"
                        style={{
                          width: `${widthPct}%`,
                          background: `linear-gradient(90deg, ${STAGE_COLORS[i]}cc, ${STAGE_COLORS[i]}66)`,
                        }}
                      />
                      <span className="absolute inset-0 flex items-center px-3 text-xs font-semibold text-white/80">
                        {stage.count.toLocaleString()} visitors
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Conversion rate insight */}
      {!isLoading && funnel.length > 0 && (
        <Card title="Conversion Insights" description="Key takeaways for today">
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 text-sm">
            <div className="p-4 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <p className="text-xs text-blue-400 font-medium mb-1">Entry → Browse Rate</p>
              <p className="text-2xl font-bold text-white">{funnel[1]?.rate ?? 0}%</p>
              <p className="text-xs text-white/40 mt-1">of entries explored a zone</p>
            </div>
            <div className="p-4 rounded-lg bg-violet-500/10 border border-violet-500/20">
              <p className="text-xs text-violet-400 font-medium mb-1">Browse → Checkout Rate</p>
              <p className="text-2xl font-bold text-white">
                {funnel[1]?.count > 0
                  ? ((funnel[2]?.count / funnel[1]?.count) * 100).toFixed(1)
                  : 0}%
              </p>
              <p className="text-xs text-white/40 mt-1">of browsers reached checkout</p>
            </div>
            <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <p className="text-xs text-emerald-400 font-medium mb-1">Overall Conversion</p>
              <p className="text-2xl font-bold text-white">{bottomRate}%</p>
              <p className="text-xs text-white/40 mt-1">entry to checkout</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
