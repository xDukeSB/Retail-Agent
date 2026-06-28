"use client";

import { Camera, Zap, VideoOff, Activity, Heart, ArrowRight, Plus, X, RefreshCw, Wifi, WifiOff, AlertCircle, Settings } from "lucide-react";
import Link from "next/link";
import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

// ─── Types ──────────────────────────────────────────────────────────────────

interface CameraState {
  status: string;         // DB status: active | connecting | inactive | error
  pipeline_state?: string; // Real-time pipeline stage from CV worker
  details?: string;        // FPS, detection count, etc.
}

// ─── Helper: Map pipeline state → friendly UI label & colour ───────────────

function getPipelineDisplay(cameraState: CameraState) {
  const { status, pipeline_state, details } = cameraState;
  const stage = pipeline_state || "";

  if (status === "active" || stage === "INFERENCE RUNNING") {
    return {
      color: "emerald",
      dot: "bg-emerald-500",
      badge: "bg-emerald-50 border-emerald-200 text-emerald-700",
      label: "LIVE",
      detail: details || "INFERENCE RUNNING",
    };
  }
  if (status === "connecting" || ["CONNECTING", "AUTHENTICATING", "STREAM STARTING", "CONNECTED"].includes(stage)) {
    return {
      color: "amber",
      dot: "bg-amber-400 animate-pulse",
      badge: "bg-amber-50 border-amber-200 text-amber-700",
      label: "CONNECTING",
      detail: stage || "Initializing...",
    };
  }
  if (status === "error" || stage.includes("ERROR") || stage.includes("OFFLINE")) {
    return {
      color: "rose",
      dot: "bg-rose-500",
      badge: "bg-rose-50 border-rose-200 text-rose-700",
      label: "ERROR",
      detail: stage || "Signal lost",
    };
  }
  // inactive / unknown
  return {
    color: "gray",
    dot: "bg-gray-400",
    badge: "bg-gray-50 border-gray-200 text-gray-500",
    label: "OFFLINE",
    detail: "Not connected",
  };
}

// ─── KPI Card ────────────────────────────────────────────────────────────────

function KPICard({ title, value, icon: Icon, colorClass, textClass }: any) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 flex flex-col items-center justify-center shadow-sm">
      <div className={`mb-3 p-2 rounded-lg ${colorClass}`}>
        <Icon className={`w-5 h-5 ${textClass}`} />
      </div>
      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">{title}</p>
      <p className="text-3xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

function PipelineTag({ text, active }: { text: string; active?: boolean }) {
  return (
    <div className={`px-3 py-1.5 rounded text-xs font-bold ${active ? "bg-emerald-50 border border-emerald-200 text-emerald-600" : "bg-gray-50 border border-gray-200 text-gray-500"}`}>
      {text}
    </div>
  );
}

// ─── Camera Feed Card ────────────────────────────────────────────────────────

function CameraFeedCard({ camera, liveState, onToggleConnection, onDelete }: {
  camera: any;
  liveState: CameraState;
  onToggleConnection: (shouldDisable: boolean) => Promise<void>;
  onDelete: () => void;
}) {
  const [isWorking, setIsWorking] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgFailed, setImgFailed] = useState(false);
  const display = getPipelineDisplay(liveState);
  const isLive = liveState.status === "active";
  const isConnecting = liveState.status === "connecting";
  const isInactive = liveState.status === "inactive" || liveState.status === "error";

  // Reload the MJPEG image whenever status transitions to active
  useEffect(() => {
    if (isLive) {
      setImgFailed(false);
      if (imgRef.current) {
        // Add cache-busting timestamp to force browser to reload the MJPEG stream
        // We use streams instead of cameras to bypass JWT auth for the raw MJPEG img tag
        const base = `${api.base}/api/v1/streams/${camera.id}/video_feed`;
        imgRef.current.src = `${base}?t=${Date.now()}`;
      }
    }
  }, [isLive, camera.id]);

  const handleToggle = async () => {
    setIsWorking(true);
    try {
      await onToggleConnection(isLive || isConnecting);
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 flex flex-col shadow-sm h-full transition-all">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1 min-w-0">
          <h3 className="font-bold text-gray-900 text-sm flex items-center gap-2 truncate">
            <span className={`w-2 h-2 rounded-full shrink-0 ${display.dot}`} />
            {camera.name}
            <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${display.badge}`}>
              {display.label}
            </span>
          </h3>
          <p className="text-[11px] text-gray-400 font-mono mt-0.5 truncate">{camera.rtsp_url || camera.url}</p>
        </div>
        <div className="flex items-center gap-2 ml-3">
          <Link
            href={`/cameras/${camera.id}/zone`}
            className="p-1.5 rounded-md border border-blue-200 bg-blue-50 text-blue-600 hover:bg-blue-100 shadow-sm"
            title="Edit Zones & Lines"
          >
            <Settings className="w-3.5 h-3.5" />
          </Link>
          <button
            onClick={handleToggle}
            disabled={isWorking}
            className="px-3 py-1.5 rounded-md border border-gray-200 text-xs font-bold text-gray-700 hover:bg-gray-50 shadow-sm disabled:opacity-50 flex items-center gap-1.5 min-w-[100px]"
          >
            {isWorking ? (
              <><RefreshCw className="w-3 h-3 animate-spin" />Working...</>
            ) : isInactive ? (
              <><Wifi className="w-3 h-3" />Connect</>
            ) : (
              <><WifiOff className="w-3 h-3" />Disconnect</>
            )}
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded-md border border-rose-200 bg-rose-50 text-rose-600 hover:bg-rose-100 shadow-sm"
            title="Delete camera"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Video Viewport */}
      <div className={`relative w-full aspect-[16/9] rounded-xl overflow-hidden border mb-4 ${isLive ? "bg-black border-emerald-200" : "bg-[#06060c] border-gray-800"}`}>
        {/* Grid overlay */}
        {!isLive && (
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:20px_20px]" />
        )}

        {/* LIVE badge */}
        <div className="absolute top-2 left-2 z-10 flex gap-1">
          <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase ${isLive ? "bg-rose-500 text-white" : "bg-gray-800 text-gray-500"}`}>
            REC
          </span>
          {isLive && (
            <span className="px-1.5 py-0.5 rounded bg-black/40 backdrop-blur-sm text-white text-[8px] font-bold uppercase">
              LIVE
            </span>
          )}
        </div>

        {/* Pipeline stage badge */}
        {(isLive || isConnecting) && liveState.details && (
          <div className="absolute top-2 right-2 z-10">
            <span className="px-2 py-0.5 rounded bg-black/50 backdrop-blur-sm text-white text-[8px] font-mono">
              {liveState.details}
            </span>
          </div>
        )}

        {/* MJPEG Stream */}
        {isLive && !imgFailed && (
          <img
            ref={imgRef}
            src={`${api.base}/api/v1/streams/${camera.id}/video_feed`}
            alt={`Live feed: ${camera.name}`}
            className="w-full h-full object-cover"
            onError={() => setImgFailed(true)}
          />
        )}

        {/* Connecting State */}
        {isConnecting && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
            <RefreshCw className="w-7 h-7 text-amber-400 animate-spin" />
            <span className="text-[10px] font-bold text-amber-400 tracking-widest uppercase">
              {liveState.pipeline_state || "CONNECTING..."}
            </span>
            {liveState.details && (
              <span className="text-[9px] text-amber-300/60 font-mono">{liveState.details}</span>
            )}
          </div>
        )}

        {/* Signal Lost / Inactive */}
        {isInactive && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
            <VideoOff className="w-7 h-7 text-gray-600" />
            <span className="text-[10px] font-bold text-gray-500 tracking-widest uppercase">SIGNAL LOST</span>
            {liveState.pipeline_state && (
              <span className="text-[9px] text-gray-600 font-mono px-2 text-center">{liveState.pipeline_state}</span>
            )}
          </div>
        )}

        {/* MJPEG fallback */}
        {isLive && imgFailed && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
            <AlertCircle className="w-7 h-7 text-amber-400" />
            <span className="text-[10px] font-bold text-amber-400 tracking-widest uppercase">STREAM BUFFERING</span>
            <button
              onClick={() => setImgFailed(false)}
              className="text-[9px] text-gray-400 underline"
            >
              retry
            </button>
          </div>
        )}
      </div>

      {/* Pipeline State Row */}
      <div className="flex items-center gap-2 mb-3 px-1">
        <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">Pipeline:</span>
        <span className={`text-[9px] font-bold font-mono ${
          isLive ? "text-emerald-600" : isConnecting ? "text-amber-600" : "text-gray-500"
        }`}>
          {liveState.pipeline_state || (isLive ? "INFERENCE RUNNING" : "IDLE")}
        </span>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-gray-50 rounded-lg py-2 border border-gray-100">
          <p className="text-[10px] font-bold text-gray-400 uppercase">Status</p>
          <p className={`text-xs font-bold mt-0.5 ${
            isLive ? "text-emerald-600" : isConnecting ? "text-amber-500" : "text-rose-500"
          }`}>
            {liveState.status?.toUpperCase() || "—"}
          </p>
        </div>
        <div className="bg-gray-50 rounded-lg py-2 border border-gray-100">
          <p className="text-[10px] font-bold text-gray-400 uppercase">DB State</p>
          <p className="text-xs font-bold text-gray-900 mt-0.5">{camera.status}</p>
        </div>
        <div className="bg-gray-50 rounded-lg py-2 border border-gray-100">
          <p className="text-[10px] font-bold text-gray-400 uppercase">WS Sync</p>
          <p className={`text-xs font-bold mt-0.5 ${liveState.pipeline_state ? "text-emerald-600" : "text-gray-400"}`}>
            {liveState.pipeline_state ? "LIVE" : "—"}
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function CamerasPage() {
  const queryClient = useQueryClient();
  const [showAddCamera, setShowAddCamera] = useState(false);
  const [newCamera, setNewCamera] = useState({ name: "", url: "" });

  // Live state per camera_id, driven by WebSocket events
  const [liveStates, setLiveStates] = useState<Record<string, CameraState>>({});

  // WebSocket connection for real-time camera state
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${api.base.replace(/^http/, "ws")}/ws/live`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);

        if (msg.type === "camera_status_update") {
          const { camera_id, status, pipeline_state, details } = msg;
          setLiveStates((prev) => ({
            ...prev,
            [camera_id]: { status, pipeline_state, details },
          }));
          // Invalidate cameras query so DB status also refreshes
          queryClient.invalidateQueries({ queryKey: ["cameras"] });
        }

        if (msg.type === "live_detections") {
          // Could update detection count display here in future
        }
      } catch {
        /* ignore parse errors */
      }
    };

    ws.onopen = () => {
      console.log("[RetailAI] WebSocket connected");
    };

    ws.onclose = () => {
      console.log("[RetailAI] WebSocket closed — reconnecting in 3s");
      reconnectTimer.current = setTimeout(connectWS, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [queryClient]);

  useEffect(() => {
    connectWS();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connectWS]);

  // Fetch cameras from REST API
  const { data: camerasData, isLoading } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.getCameras(),
    refetchInterval: 15000, // Poll every 15s as fallback
  });

  const cameras = camerasData?.cameras || [];
  const summary = camerasData?.summary || { total: 0, active: 0, degraded: 0, error: 0 };

  // Populate initial liveStates from DB on first load
  useEffect(() => {
    if (!cameras.length) return;
    setLiveStates((prev) => {
      const next = { ...prev };
      for (const cam of cameras) {
        if (!next[cam.id]) {
          next[cam.id] = { status: cam.status };
        }
      }
      return next;
    });
  }, [cameras.length]);

  const createCamera = useMutation({
    mutationFn: api.createCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setShowAddCamera(false);
      setNewCamera({ name: "", url: "" });
    },
    onError: (error: any) => {
      alert(`Failed to connect camera: ${error.message}. Is the backend running?`);
    }
  });

  const deleteCamera = useMutation({
    mutationFn: (id: string) => api.deleteCamera(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });

  const toggleCamera = async (camera: any, shouldDisable: boolean) => {
    if (shouldDisable) {
      await api.disableCamera(camera.id);
    } else {
      await api.enableCamera(camera.id);
    }
    queryClient.invalidateQueries({ queryKey: ["cameras"] });
  };

  const handleAddCamera = () => {
    if (!newCamera.name || !newCamera.url) return;
    createCamera.mutate({ name: newCamera.name, rtsp_url: newCamera.url, is_enabled: true });
  };

  // Count cameras by live WebSocket state for KPI cards
  const liveActive = cameras.filter((c: any) => liveStates[c.id]?.status === "active").length;
  const liveConnecting = cameras.filter((c: any) => liveStates[c.id]?.status === "connecting").length;
  const liveError = cameras.filter((c: any) => {
    const s = liveStates[c.id]?.status;
    return s === "error" || s === "inactive";
  }).length;

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10">

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <KPICard title="ONLINE" value={liveActive} icon={Camera} colorClass="bg-emerald-50" textClass="text-emerald-500" />
        <KPICard title="CONNECTING" value={liveConnecting} icon={RefreshCw} colorClass="bg-amber-50" textClass="text-amber-500" />
        <KPICard title="OFFLINE" value={liveError} icon={VideoOff} colorClass="bg-rose-50" textClass="text-rose-500" />
        <KPICard title="AVG FPS" value={summary.active ? "~30" : "--"} icon={Activity} colorClass="bg-blue-50" textClass="text-blue-500" />
        <KPICard title="WS STATUS" value={wsRef.current?.readyState === WebSocket.OPEN ? "LIVE" : "..."} icon={Zap} colorClass="bg-purple-50" textClass="text-purple-500" />
      </div>

      {/* Pipeline Diagram */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 flex items-center shadow-sm overflow-x-auto">
        <span className="text-[11px] font-bold text-gray-800 mr-4 uppercase tracking-wider shrink-0">CV Pipeline:</span>
        <div className="flex items-center gap-2 flex-nowrap min-w-max">
          {["RTSP Camera", "MediaMTX", "CaptureWorker", "frame_queue (JPEG)", "InferenceWorker", "YOLOv8n + ByteTrack", "event_queue", "EventEngine", "SQLite + WebSocket", "Dashboard"].map((stage, i, arr) => (
            <div key={stage} className="flex items-center gap-2">
              <PipelineTag text={stage} active={stage === "Dashboard"} />
              {i < arr.length - 1 && <ArrowRight className="w-3 h-3 text-gray-300" />}
            </div>
          ))}
        </div>
      </div>

      {/* Camera Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {isLoading ? (
          <div className="col-span-3 text-center py-10 text-gray-500">Loading cameras...</div>
        ) : cameras.map((c: any) => (
          <CameraFeedCard
            key={c.id}
            camera={c}
            liveState={liveStates[c.id] || { status: c.status }}
            onToggleConnection={(shouldDisable) => toggleCamera(c, shouldDisable)}
            onDelete={() => deleteCamera.mutate(c.id)}
          />
        ))}

        {/* Add Camera Card */}
        <div
          onClick={() => setShowAddCamera(true)}
          className="bg-white border-2 border-dashed border-gray-200 rounded-xl p-5 flex flex-col items-center justify-center text-center shadow-sm min-h-[340px] cursor-pointer hover:border-emerald-400 hover:bg-emerald-50/40 transition-colors"
        >
          <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3 text-gray-400">
            <Plus className="w-5 h-5" />
          </div>
          <h3 className="font-medium text-gray-700 text-sm mb-1">Add RTSP Camera</h3>
          <p className="text-[11px] text-gray-500 max-w-[180px]">Connect IP camera, NVR, or DVR via RTSP URL</p>
        </div>
      </div>

      {/* Footer */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm text-[11px] text-gray-500 space-y-1">
        <p><span className="font-bold text-gray-800">Pipeline:</span> RTSP → MediaMTX → CaptureWorker (JPEG encode) → frame_queue → InferenceWorker (YOLO + ByteTrack) → annotated_queue + event_queue → EventEngine → SQLite + WebSocket → Dashboard</p>
        <p><span className="font-bold text-gray-800">Privacy:</span> No facial recognition. No biometric data. All tracking is anonymous (Visitor #ID).</p>
      </div>

      <div className="flex flex-col md:flex-row items-center justify-between px-2 pt-1 text-[10px] font-medium text-gray-400">
        <p><span className="font-bold text-gray-800">RetailAI Agent</span> v1.0.0 · Local-First Retail Intelligence</p>
        <p><span className="text-emerald-500 font-bold">●</span> YOLOv8n + ByteTrack · SQLite · localhost:3000</p>
      </div>

      {/* Add Camera Modal */}
      {showAddCamera && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50">
              <h3 className="text-sm font-bold text-gray-900">Add RTSP Camera</h3>
              <button onClick={() => setShowAddCamera(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Camera Name</label>
                <input
                  type="text"
                  value={newCamera.name}
                  onChange={(e) => setNewCamera({ ...newCamera, name: e.target.value })}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                  placeholder="e.g. Store Entrance"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">RTSP Stream URL</label>
                <input
                  type="text"
                  value={newCamera.url}
                  onChange={(e) => setNewCamera({ ...newCamera, url: e.target.value })}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                  placeholder="rtsp://127.0.0.1:8554/store"
                />
              </div>
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-[11px] text-blue-700">
                <span className="font-bold">Tip:</span> The camera will auto-connect and start YOLO inference immediately after adding. Watch the status badge update in real-time via WebSocket.
              </div>
            </div>
            <div className="p-4 border-t border-gray-100 flex justify-end gap-3 bg-gray-50">
              <button onClick={() => setShowAddCamera(false)} className="px-4 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
              <button
                onClick={handleAddCamera}
                disabled={createCamera.isPending || !newCamera.name || !newCamera.url}
                className="px-4 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg shadow-sm hover:bg-emerald-700 disabled:opacity-50 transition-colors"
              >
                {createCamera.isPending ? "Connecting..." : "Connect Camera"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
