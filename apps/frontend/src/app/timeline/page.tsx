"use client";

import { LogIn, LogOut, MapPin, Users, Filter, ShoppingBag, CreditCard, Download, Trash2, ChevronDown, CheckCircle2 } from "lucide-react";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { useState } from "react";



function getEventIcon(type: string) {
  switch (type) {
    case "entry": return <div className="p-1 rounded bg-emerald-50 text-emerald-600"><LogIn className="w-3.5 h-3.5" /></div>;
    case "exit": return <div className="p-1 rounded bg-rose-50 text-rose-600"><LogOut className="w-3.5 h-3.5" /></div>;
    case "zone": return <div className="p-1 rounded bg-blue-50 text-blue-600"><MapPin className="w-3.5 h-3.5" /></div>;
    case "queue": return <div className="p-1 rounded bg-orange-50 text-orange-500"><CheckCircle2 className="w-3.5 h-3.5" /></div>;
    case "queue_formed": return <div className="p-1 rounded bg-orange-100 text-orange-600"><Users className="w-3.5 h-3.5" /></div>;
    default: return <div className="p-1 rounded bg-gray-100"><Filter className="w-3.5 h-3.5" /></div>;
  }
}

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function TimelinePage() {
  const { data: historyData } = useQuery({
    queryKey: ["timeline_history"],
    queryFn: () => api.getTimelineEvents({ limit: 100 })
  });

  const [liveEvents, setLiveEvents] = useState<any[]>([]);

  useLiveFeed((e) => {
    setLiveEvents((prev) => [{
      id: Math.random().toString(),
      time: new Date().toLocaleTimeString("en-US", { hour12: false }),
      type: e.event_type || e.type,
      title: e.type,
      subtitle: `Visitor #${e.track_id ? String(e.track_id).substring(0, 4) : "????"} · ${e.zone_name || "Unknown"}`,
      status: "synced",
      timestamp: new Date().toISOString(),
      track_id: e.track_id,
    }, ...prev].slice(0, 100));
  });

  const rawEvents = [
    ...liveEvents,
    ...(historyData || []).map((h: any) => ({
      id: h.id,
      time: new Date(h.timestamp).toLocaleTimeString("en-US", { hour12: false }),
      type: h.type,
      title: h.type,
      subtitle: `Visitor #${h.track_id ? String(h.track_id).substring(0, 4) : "????"} · ${h.zone_name || "Unknown"}`,
      status: "synced",
      timestamp: h.timestamp,
      track_id: h.track_id,
    }))
  ];

  // Sort by timestamp descending
  const events = rawEvents.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 100);

  // Compute dynamic visitors
  const visitorMap = new Map<string, any>();
  events.forEach((ev) => {
    if (ev.track_id) {
      const vid = String(ev.track_id).substring(0, 4);
      if (!visitorMap.has(vid)) {
        visitorMap.set(vid, {
          id: vid,
          firstSeen: new Date(ev.timestamp),
          lastSeen: new Date(ev.timestamp),
          zones: new Set(),
        });
      }
      const v = visitorMap.get(vid);
      if (new Date(ev.timestamp) < v.firstSeen) v.firstSeen = new Date(ev.timestamp);
      if (new Date(ev.timestamp) > v.lastSeen) v.lastSeen = new Date(ev.timestamp);
      if (ev.type === "zone") {
        v.zones.add(ev.subtitle);
      }
    }
  });

  const dynamicVisitors = Array.from(visitorMap.values()).map(v => ({
    id: v.id,
    time: v.firstSeen.toLocaleTimeString("en-US", { hour12: false }),
    zones: Math.max(1, v.zones.size),
    mins: Math.floor((v.lastSeen.getTime() - v.firstSeen.getTime()) / 60000)
  })).sort((a: any, b: any) => b.lastSeen.getTime() - a.lastSeen.getTime());

  const [filter, setFilter] = useState("All");
  const [isExporting, setIsExporting] = useState(false);

  const filters = [
    { label: "All", icon: Filter },
    { label: "Entries", icon: LogIn },
    { label: "Exits", icon: LogOut },
    { label: "Zone Visits", icon: MapPin },
    { label: "Checkout", icon: ShoppingBag },
    { label: "Transactions", icon: CreditCard },
    { label: "Queues", icon: Users },
  ];

  const handleExport = () => {
    setIsExporting(true);
    setTimeout(() => setIsExporting(false), 2000);
  };

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto pb-10">
      
      {/* Filter Bar */}
      <div className="bg-white border border-gray-200 rounded-xl px-4 py-3 shadow-sm flex items-center justify-between">
        <div className="flex items-center gap-3 overflow-x-auto no-scrollbar">
          <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">Filters:</span>
          
          {filters.map(({ label, icon: Icon }) => (
            <button 
              key={label}
              onClick={() => setFilter(label)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
                filter === label 
                  ? "bg-emerald-600 text-white font-bold shadow-sm" 
                  : "bg-white border border-gray-200 text-gray-600 font-semibold hover:bg-gray-50"
              }`}
            >
              <Icon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}

          <div className="h-6 w-px bg-gray-200 mx-1" />

          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-gray-700 text-xs font-bold hover:bg-gray-50">
            All Cameras <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button 
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-gray-600 text-xs font-semibold hover:bg-gray-50 transition-all"
          >
            {isExporting ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> : <Download className="w-3.5 h-3.5" />}
            {isExporting ? "Exported ✓" : "Export CSV"}
          </button>
          <button 
            onClick={() => setLiveEvents([])}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-50 text-rose-600 text-xs font-bold hover:bg-rose-100"
          >
            <Trash2 className="w-3.5 h-3.5" /> Clear
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column: Event Timeline */}
        <div className="lg:col-span-2 bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden flex flex-col h-[750px]">
          <div className="p-5 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-gray-900">Event Timeline</h2>
              <p className="text-[11px] text-gray-500 font-medium">
                {events.length} event{events.length !== 1 ? 's' : ''} · live feed
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-500 uppercase tracking-wider">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Live
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">
              {new Date().toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }).toUpperCase()} · LIVE
            </h3>
            
            <div className="space-y-1">
              {events.filter(e => filter === "All" || filter === e.title || (filter === "Entries" && e.type === "entry") || (filter === "Exits" && e.type === "exit") || (filter === "Zone Visits" && e.type === "zone") || (filter === "Queues" && e.type === "queue_update")).map(event => (
                <div key={event.id} className={`flex items-start gap-4 p-2 rounded-lg hover:bg-gray-50/80 transition-colors group ${event.bg || ''}`}>
                  <div className="text-[11px] text-gray-400 font-mono font-medium pt-1 w-16">
                    {event.time}
                  </div>
                  
                  <div className="pt-0.5 relative">
                    {getEventIcon(event.type)}
                    {/* Faint connecting line could go here if wanted */}
                  </div>

                  <div className="flex-1 pt-0.5">
                    <h4 className="text-sm font-bold text-gray-800">{event.title}</h4>
                    {event.subtitle && (
                      <p className="text-[11px] text-gray-500 mt-0.5">{event.subtitle}</p>
                    )}
                  </div>

                  <div className="pt-1">
                    {event.status === "pending" ? (
                      <span className="px-2 py-0.5 rounded-full border border-orange-200 text-orange-500 text-[9px] font-bold uppercase tracking-wider bg-orange-50">pending</span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full border border-emerald-200 text-emerald-500 text-[9px] font-bold uppercase tracking-wider bg-emerald-50">synced</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Customer Journey Intelligence */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 h-[750px] flex flex-col">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-gray-400" />
            <h2 className="text-sm font-bold text-gray-900">Customer Journey Intelligence</h2>
          </div>
          <p className="text-[11px] text-gray-500 mb-6">Click any visitor to filter the timeline by their journey.</p>
          
          <div className="space-y-3 flex-1 overflow-y-auto pr-1">
            {dynamicVisitors.length === 0 && (
              <div className="text-center text-gray-400 text-xs mt-10">No visitors tracked yet.</div>
            )}
            {dynamicVisitors.map(v => (
              <div key={v.id} className="border border-gray-200 rounded-xl p-4 hover:border-emerald-300 hover:shadow-md transition-all cursor-pointer bg-white">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-8 h-8 rounded-full bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 text-[10px] font-bold">
                    {v.id}
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-gray-900">Visitor #{v.id}</h4>
                    <p className="text-[10px] text-gray-500 font-medium">In store</p>
                  </div>
                </div>
                
                <div className="text-[11px] font-mono text-gray-600 mb-3">
                  {v.time} <span className="font-sans ml-1 text-gray-500">Entered</span>
                </div>
                
                <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden mb-2">
                  <div className="h-full bg-emerald-400 rounded-full w-[10%]" />
                </div>
                
                <div className="flex items-center justify-between text-[10px] text-gray-400 font-bold">
                  <span>{v.zones} zones</span>
                  <span>{v.mins}m in store</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
