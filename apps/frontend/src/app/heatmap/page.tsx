"use client";

import { BoxSelect, Eye, Plus, ArrowRight, ShieldAlert, Lightbulb, TrendingDown, Layers, Map as MapIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { Skeleton, EmptyState } from "@/components/ui/index";

export default function HeatmapPage() {
  const { data: camerasData } = useQuery({ queryKey: ["cameras"], queryFn: () => api.getCameras() });
  const camera = camerasData?.cameras?.[0];

  const { data: heatmapData, isLoading } = useQuery({
    queryKey: ["heatmap", camera?.id],
    queryFn: () => api.getHeatmap(camera!.id),
    enabled: !!camera?.id,
    refetchInterval: 30_000,
  });

  const [viewMode, setViewMode] = useState("Heatmap");
  const [isAddingZone, setIsAddingZone] = useState(false);

  const getZoneCount = (zoneName: string) => {
    if (!heatmapData?.zones) return 0;
    const z = heatmapData.zones.find((z: any) => z.zone_name.toLowerCase() === zoneName.toLowerCase());
    return z ? z.total_events : 0;
  };

  const getZonePct = (val: number) => {
    if (!heatmapData?.total_events || heatmapData.total_events === 0) return "0%";
    return `${Math.round((val / heatmapData.total_events) * 100)}%`;
  };

  const zonesList = heatmapData?.zones || [];
  const maxZoneVal = zonesList.reduce((max: number, z: any) => Math.max(max, z.total_events), 1);

  return (
    <div className="max-w-[1600px] mx-auto pb-10 space-y-6">
      
      {/* Top Controls */}
      <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-3 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-2 text-sm font-bold text-gray-700">
            <Layers className="w-4 h-4 text-gray-400" />
            Store Layout Editor
          </div>
          <div className="flex items-center bg-gray-100 rounded-lg p-1">
            {["Heatmap", "Zone Borders"].map(t => (
              <button 
                key={t}
                onClick={() => setViewMode(t)}
                className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs transition-colors ${
                  viewMode === t 
                    ? "bg-emerald-50 text-emerald-600 font-bold shadow-sm border border-emerald-100/50" 
                    : "text-gray-500 font-medium hover:text-gray-700"
                }`}
              >
                <Eye className="w-3.5 h-3.5" /> {t}
              </button>
            ))}
          </div>
          <div className="text-xs font-bold text-gray-500 border-l border-gray-200 pl-4">
            <span className="text-gray-900">{zonesList.length}</span> zones configured
          </div>
        </div>
        <button 
          onClick={() => {
            setIsAddingZone(true);
            setTimeout(() => setIsAddingZone(false), 2000);
          }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white border border-gray-200 text-gray-700 text-xs font-bold shadow-sm hover:bg-gray-50 transition-all"
        >
          {isAddingZone ? <span className="w-3.5 h-3.5 border-2 border-gray-400 border-t-gray-700 rounded-full animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
          {isAddingZone ? "Adding..." : "Add Zone"}
        </button>
      </div>

      <div className="flex flex-col xl:flex-row gap-6 items-start">
        
        {/* Left Column (Map) */}
        <div className="flex-1 w-full bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          <div className="mb-6">
            <h2 className="text-sm font-bold text-gray-900">Store Layout — Heatmap</h2>
            <p className="text-[11px] text-gray-500 mt-0.5">Customer density visualization from camera tracking data</p>
          </div>

          {isLoading ? (
            <Skeleton className="w-full aspect-[4/3] rounded-xl" />
          ) : (
            <div className="relative w-full aspect-[4/3] bg-[#020617] rounded-xl overflow-hidden border border-gray-100 shadow-inner" style={{ backgroundImage: 'radial-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px)', backgroundSize: '24px 24px' }}>
              
              {/* Dynamic zone overlay — rendered from live camera zone configuration */}
              {zonesList.length === 0 ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                  <MapIcon className="w-10 h-10 text-white/20" />
                  <p className="text-white/40 text-xs font-bold uppercase tracking-widest">No zones configured</p>
                  <p className="text-white/25 text-[10px]">Add zones to your camera via Settings → Camera Management</p>
                </div>
              ) : (
                <div className="absolute inset-0 p-4 grid gap-2" style={{
                  gridTemplateColumns: `repeat(${Math.min(3, zonesList.length)}, 1fr)`,
                  gridTemplateRows: `repeat(${Math.ceil(zonesList.length / Math.min(3, zonesList.length))}, 1fr)`,
                }}>
                  {zonesList.map((z: any, idx: number) => {
                    const intensity = maxZoneVal > 0 ? z.total_events / maxZoneVal : 0;
                    const palette = [
                      { bg: 'rgba(16,185,129,0.4)', border: 'rgba(16,185,129,0.7)', text: '#d1fae5' },
                      { bg: 'rgba(14,165,233,0.4)', border: 'rgba(14,165,233,0.7)', text: '#e0f2fe' },
                      { bg: 'rgba(132,204,22,0.4)', border: 'rgba(132,204,22,0.7)', text: '#ecfccb' },
                      { bg: 'rgba(245,158,11,0.5)', border: 'rgba(245,158,11,0.8)', text: '#fef3c7' },
                      { bg: 'rgba(249,115,22,0.4)', border: 'rgba(249,115,22,0.7)', text: '#ffedd5' },
                      { bg: 'rgba(217,70,239,0.4)', border: 'rgba(217,70,239,0.7)', text: '#fae8ff' },
                      { bg: 'rgba(99,102,241,0.4)', border: 'rgba(99,102,241,0.7)', text: '#e0e7ff' },
                      { bg: 'rgba(20,184,166,0.4)', border: 'rgba(20,184,166,0.7)', text: '#ccfbf1' },
                    ];
                    const c = palette[idx % palette.length];
                    return (
                      <div
                        key={z.zone_name || idx}
                        className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed transition-all duration-300"
                        style={{
                          background: c.bg,
                          borderColor: c.border,
                          boxShadow: `0 0 ${20 + intensity * 30}px ${c.border} inset`,
                        }}
                      >
                        <div className="text-[9px] uppercase tracking-widest font-bold opacity-70" style={{ color: c.text }}>Zone</div>
                        <div className="text-[11px] font-bold text-center px-1 leading-tight mt-0.5" style={{ color: c.text }}>{z.zone_name}</div>
                        <div className="text-xs font-bold mt-1" style={{ color: c.text }}>{z.total_events}</div>
                        <div className="text-[9px] opacity-60 mt-0.5" style={{ color: c.text }}>{getZonePct(z.total_events)}</div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Legend */}
              <div className="absolute bottom-4 left-4 border border-white/10 bg-black/40 backdrop-blur-sm rounded-lg p-3">
                <div className="text-[9px] font-bold text-white/70 uppercase tracking-widest mb-2">Heatmap Intensity</div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-white/50">low</span>
                  <div className="w-24 h-2 rounded-full" style={{ background: 'linear-gradient(to right, #10b981, #eab308, #ef4444)' }} />
                  <span className="text-[10px] font-bold text-white/50">high</span>
                </div>
              </div>

            </div>
          )}

          {heatmapData?.paths && heatmapData.paths.length > 0 && (
            <div className="mt-8 pt-6 border-t border-gray-100">
              <div className="flex items-center gap-2 mb-4">
                <TrendingDown className="w-4 h-4 text-gray-400 rotate-[-90deg]" />
                <h3 className="text-sm font-bold text-gray-900">Customer Flow Paths</h3>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {heatmapData.paths[0].map((node: string, i: number, arr: string[]) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="px-3 py-1.5 bg-gray-100 rounded-md text-[11px] font-bold text-gray-700">{node}</span>
                    {i < arr.length - 1 && <ArrowRight className="w-3.5 h-3.5 text-gray-300" />}
                  </div>
                ))}
                <span className="ml-2 text-[10px] font-medium text-gray-400">(most common journey)</span>
              </div>
            </div>
          )}

        </div>

        {/* Right Column */}
        <div className="w-full xl:w-[380px] shrink-0 space-y-6">
          
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-sm font-bold text-gray-900">Zone Performance</h2>
              <span className="text-[11px] text-gray-500 font-medium">{heatmapData?.total_events || 0} total visits</span>
            </div>
            
            {isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : !zonesList.length ? (
              <EmptyState icon={MapIcon} title="No Zone Data" description="Zones not yet recording data." />
            ) : (
              <div className="space-y-6">
                {zonesList.map((z: any, idx: number) => {
                  const colors = ["#10b981", "#14b8a6", "#84cc16", "#f97316", "#eab308"];
                  const fill = colors[idx % colors.length];
                  const w = maxZoneVal > 0 ? `${(z.total_events / maxZoneVal) * 100}%` : "0%";
                  const pct = getZonePct(z.total_events);

                  return (
                    <div key={z.zone_name}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: fill }} />
                          <span className="text-xs font-bold text-gray-900">{z.zone_name}</span>
                        </div>
                        <span className="text-xs font-bold text-gray-500">{z.total_events}</span>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2 text-[10px] font-bold text-gray-400 w-16 shrink-0">
                          {pct}
                        </div>
                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all" style={{ width: w, backgroundColor: fill }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {zonesList.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
              <h2 className="text-sm font-bold text-gray-900 mb-6">Insights</h2>
              <div className="space-y-3">
                <div className="flex items-start gap-3 p-3 bg-emerald-50 rounded-lg border border-emerald-100">
                  <ShieldAlert className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                  <p className="text-[11px] text-emerald-900 font-medium leading-relaxed">
                    <strong>{zonesList[0]?.zone_name}</strong> is currently your most engaging zone with {zonesList[0]?.total_events} visits.
                  </p>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>

    </div>
  );
}

