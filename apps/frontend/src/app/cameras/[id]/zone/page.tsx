"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, Badge } from "@/components/ui/index";
import { Trash2, Plus, Save, ArrowLeft, MousePointer, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";

interface Point { x: number; y: number; }
interface Zone {
  name: string;
  type: "polygon" | "line";
  zone_type: "entry" | "exit" | "checkout" | "queue" | "general";
  color: string;
  points: Point[];
}
interface EventLine {
  id?: string;
  name: string;
  line_type: "entry" | "exit" | "both";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  flip_direction: boolean;
}

const ZONE_COLORS: Record<string, string> = {
  entry:    "#10b981",
  exit:     "#f43f5e",
  checkout: "#3b82f6",
  queue:    "#f59e0b",
  general:  "#8b5cf6",
};

const LINE_COLORS: Record<string, string> = {
  entry: "#10b981",
  exit: "#f43f5e",
  both: "#f59e0b",
};

const ZONE_TYPE_OPTIONS = [
  { value: "entry",    label: "Entry" },
  { value: "exit",     label: "Exit" },
  { value: "checkout", label: "Checkout" },
  { value: "queue",    label: "Queue" },
  { value: "general",  label: "General" },
];

export default function ZoneEditorPage() {
  const params = useParams<{ id: string }>();
  const cameraId = params?.id as string;
  
  const qc = useQueryClient();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  // Cache-busting timestamp that doesn't change on re-render
  const timestampRef = useRef(Date.now());
  
  const [mode, setMode] = useState<"zone" | "line">("line");
  const [zones, setZones]       = useState<Zone[]>([]);
  const [eventLines, setEventLines] = useState<EventLine[]>([]);
  
  const [drawing, setDrawing]   = useState(false);
  const [currentPoints, setCurrentPoints] = useState<Point[]>([]);
  const [activeZoneType, setActiveZoneType] = useState<Zone["zone_type"]>("general");
  const [activeShape, setActiveShape] = useState<"polygon" | "line">("polygon");
  const [activeLineType, setActiveLineType] = useState<EventLine["line_type"]>("both");
  const [elementName, setElementName] = useState("");
  const [saved, setSaved]       = useState(false);

  const { data: camera } = useQuery({
    queryKey: ["camera", cameraId],
    queryFn:  () => api.getCamera(cameraId),
    enabled: !!cameraId,
  });

  const { data: linesData } = useQuery({
    queryKey: ["camera_lines", cameraId],
    queryFn: () => api.getLines(cameraId),
    enabled: !!cameraId,
  });

  // Load existing zones & lines
  useEffect(() => {
    if (camera?.zone_config?.zones) {
      setZones(camera.zone_config.zones);
    }
  }, [camera]);

  useEffect(() => {
    if (linesData?.lines) {
      setEventLines(linesData.lines);
    }
  }, [linesData]);

  const saveMut = useMutation({
    mutationFn: () => api.updateZones(cameraId, { zones }),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ["camera", cameraId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const createLineMut = useMutation({
    mutationFn: (line: EventLine) => api.createLine({ ...line, camera_id: cameraId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["camera_lines", cameraId] });
    }
  });

  const deleteLineMut = useMutation({
    mutationFn: (lineId: string) => api.deleteLine(cameraId, lineId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["camera_lines", cameraId] });
    }
  });

  // Draw canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw grid
    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.lineWidth = 0.5;
    for (let x = 0; x < canvas.width; x += 40) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    for (let y = 0; y < canvas.height; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }

    // Draw saved zones
    zones.forEach(zone => {
      if (zone.points.length < 2) return;
      const pts = zone.points.map(p => ({
        x: p.x * canvas.width,
        y: p.y * canvas.height,
      }));

      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
      if (zone.type === "polygon") ctx.closePath();

      ctx.fillStyle   = zone.color + "33";
      ctx.strokeStyle = zone.color;
      ctx.lineWidth   = 2;
      if (zone.type === "polygon") ctx.fill();
      ctx.stroke();

      // Label
      const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length;
      const cy = pts.reduce((a, p) => a + p.y, 0) / pts.length;
      ctx.fillStyle = zone.color;
      ctx.font      = "bold 12px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(zone.name, cx, cy + 4);
    });

    // Draw saved Event Lines
    eventLines.forEach(line => {
      const color = LINE_COLORS[line.line_type] || "#fff";
      const x1 = line.x1 * canvas.width;
      const y1 = line.y1 * canvas.height;
      const x2 = line.x2 * canvas.width;
      const y2 = line.y2 * canvas.height;

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.stroke();

      // Label
      const cx = (x1 + x2) / 2;
      const cy = (y1 + y2) / 2;
      ctx.fillStyle = color;
      ctx.font = "bold 12px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`${line.name} (${line.line_type})`, cx, cy - 8);
    });

    // Draw current shape being drawn
    if (currentPoints.length > 0) {
      const pts = currentPoints.map(p => ({
        x: p.x * canvas.width,
        y: p.y * canvas.height,
      }));
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
      
      const drawColor = mode === "zone" ? ZONE_COLORS[activeZoneType] : LINE_COLORS[activeLineType];
      
      ctx.strokeStyle = drawColor;
      ctx.lineWidth   = 2;
      ctx.setLineDash([6, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      pts.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = drawColor;
        ctx.fill();
      });
    }
  }, [zones, eventLines, currentPoints, activeZoneType, activeLineType, mode]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawing) return;
    const canvas = canvasRef.current!;
    const rect   = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top)  / rect.height));
    
    if (mode === "line" && currentPoints.length === 1) {
      // Complete the line
      const newPoints = [...currentPoints, { x, y }];
      setCurrentPoints(newPoints);
      
      const name = elementName || `${activeLineType} Line ${eventLines.length + 1}`;
      const newLine = {
        name,
        line_type: activeLineType,
        x1: newPoints[0].x,
        y1: newPoints[0].y,
        x2: newPoints[1].x,
        y2: newPoints[1].y,
        flip_direction: false,
      };
      
      createLineMut.mutate(newLine as any);
      setCurrentPoints([]);
      setElementName("");
      setDrawing(false);
    } else {
      setCurrentPoints(prev => [...prev, { x, y }]);
    }
  };

  const handleCanvasDblClick = () => {
    if (!drawing || mode !== "zone" || currentPoints.length < 2) return;
    const name = elementName || `${activeZoneType}-${zones.length + 1}`;
    setZones(prev => [
      ...prev,
      {
        name,
        type:      activeShape,
        zone_type: activeZoneType,
        color:     ZONE_COLORS[activeZoneType],
        points:    currentPoints,
      },
    ]);
    setCurrentPoints([]);
    setElementName("");
    setDrawing(false);
  };

  const inputCls =
    "w-full px-3 py-2 rounded-lg border border-gray-200 bg-white text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-blue-500 transition-all";

  return (
    <div className="space-y-4 animate-slide-up">
      <div className="flex items-center gap-3">
        <Link href="/cameras" className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" /> Cameras
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-xs text-gray-500">{camera?.name ?? "Loading…"}</span>
        <span className="text-gray-300">/</span>
        <span className="text-xs font-bold text-gray-900">Editor</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Canvas */}
        <div className="xl:col-span-2">
          <Card
            title="Drawing Canvas"
            description={drawing ? (mode === "line" ? "Click to add start and end points" : "Click to add points · Double-click to finish zone") : "Select a type and click 'Start Drawing'"}
            action={
              <Badge variant={drawing ? "warning" : "default"}>
                {drawing ? `${currentPoints.length} points` : "Idle"}
              </Badge>
            }
          >
            <div className="relative w-full aspect-video rounded-lg overflow-hidden border border-gray-200 bg-black shadow-inner">
              {/* Background Live MJPEG Feed */}
              {cameraId && (
                <img
                  src={`${api.base}/api/v1/streams/${cameraId}/video_feed?t=${timestampRef.current}`}
                  alt="Live feed"
                  className="absolute inset-0 w-full h-full object-cover pointer-events-none opacity-80"
                />
              )}
              <canvas
                ref={canvasRef}
                width={1280}
                height={720}
                onClick={handleCanvasClick}
                onDoubleClick={handleCanvasDblClick}
                className={cn(
                  "absolute inset-0 w-full h-full",
                  drawing ? "cursor-crosshair" : "cursor-default"
                )}
              />
            </div>
            <p className="text-xs text-gray-500 mt-3 text-center">
              Draw analytics lines or zones directly over the live camera feed.
            </p>
          </Card>
        </div>

        {/* Controls */}
        <div className="space-y-4">
          
          <Card title="New Element">
            <div className="flex gap-2 mb-4">
               <button
                  onClick={() => { setMode("line"); setDrawing(false); setCurrentPoints([]); }}
                  className={cn(
                    "flex-1 py-1.5 rounded-lg text-xs font-bold border transition-all",
                    mode === "line"
                      ? "bg-blue-50 text-blue-600 border-blue-200"
                      : "text-gray-500 border-gray-200 hover:text-gray-900 bg-white"
                  )}
                >
                  Analytics Line
                </button>
               <button
                  onClick={() => { setMode("zone"); setDrawing(false); setCurrentPoints([]); }}
                  className={cn(
                    "flex-1 py-1.5 rounded-lg text-xs font-bold border transition-all",
                    mode === "zone"
                      ? "bg-blue-50 text-blue-600 border-blue-200"
                      : "text-gray-500 border-gray-200 hover:text-gray-900 bg-white"
                  )}
                >
                  Zone
                </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Name</label>
                <input
                  className={inputCls}
                  placeholder={mode === "line" ? "e.g. Main Entrance" : "e.g. Checkout Area"}
                  value={elementName}
                  onChange={e => setElementName(e.target.value)}
                />
              </div>

              {mode === "zone" ? (
                <>
                  <div>
                    <label className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Zone Type</label>
                    <div className="grid grid-cols-2 gap-1.5">
                      {ZONE_TYPE_OPTIONS.map(opt => (
                        <button
                          key={opt.value}
                          onClick={() => setActiveZoneType(opt.value as Zone["zone_type"])}
                          className={cn(
                            "py-1.5 rounded-lg text-xs font-bold border transition-all",
                            activeZoneType === opt.value
                              ? "text-white border-transparent shadow-sm"
                              : "text-gray-500 border-gray-200 hover:text-gray-900 bg-white"
                          )}
                          style={activeZoneType === opt.value
                            ? { background: ZONE_COLORS[opt.value], borderColor: ZONE_COLORS[opt.value] }
                            : {}}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Shape</label>
                    <div className="flex gap-2">
                      {(["polygon", "line"] as const).map(s => (
                        <button
                          key={s}
                          onClick={() => setActiveShape(s)}
                          className={cn(
                            "flex-1 py-1.5 rounded-lg text-xs font-bold border transition-all capitalize",
                            activeShape === s
                              ? "bg-blue-50 text-blue-600 border-blue-200"
                              : "text-gray-500 border-gray-200 hover:text-gray-900 bg-white"
                          )}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div>
                  <label className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Line Type</label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {["entry", "exit", "both"].map(type => (
                      <button
                        key={type}
                        onClick={() => setActiveLineType(type as EventLine["line_type"])}
                        className={cn(
                          "py-1.5 rounded-lg text-xs font-bold border transition-all capitalize",
                          activeLineType === type
                            ? "text-white border-transparent shadow-sm"
                            : "text-gray-500 border-gray-200 hover:text-gray-900 bg-white"
                        )}
                        style={activeLineType === type
                          ? { background: LINE_COLORS[type], borderColor: LINE_COLORS[type] }
                          : {}}
                      >
                        {type}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {!drawing ? (
                <button
                  onClick={() => { setDrawing(true); setCurrentPoints([]); }}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold shadow-sm transition-colors mt-2"
                >
                  <Plus className="w-4 h-4" /> Start Drawing
                </button>
              ) : (
                <div className="flex gap-2 mt-2">
                  {mode === "zone" && (
                    <button
                      onClick={handleCanvasDblClick}
                      disabled={currentPoints.length < 2}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 disabled:opacity-40 text-white text-sm font-bold shadow-sm transition-colors"
                    >
                      <MousePointer className="w-3.5 h-3.5" /> Finish
                    </button>
                  )}
                  <button
                    onClick={() => { setDrawing(false); setCurrentPoints([]); }}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-gray-200 bg-white text-gray-600 text-sm hover:bg-gray-50 font-bold transition-colors shadow-sm"
                  >
                    <Minus className="w-3.5 h-3.5" /> Cancel
                  </button>
                </div>
              )}
            </div>
          </Card>

          {/* Lines list */}
          <Card title={`Analytics Lines (${eventLines.length})`}>
            {eventLines.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-4">No lines yet</p>
            ) : (
              <div className="space-y-2">
                {eventLines.map((line) => (
                  <div key={line.id} className="flex items-center justify-between py-1.5 border-b border-gray-100 last:border-0">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded shadow-sm" style={{ background: LINE_COLORS[line.line_type] || "#ccc" }} />
                      <div>
                        <p className="text-xs font-bold text-gray-900">{line.name}</p>
                        <p className="text-[10px] text-gray-500 font-medium uppercase">{line.line_type}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => deleteLineMut.mutate(line.id!)}
                      className="p-1 rounded text-gray-400 hover:text-rose-500 hover:bg-rose-50 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Zone list */}
          <Card title={`Zones (${zones.length})`}>
            {zones.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-4">No zones yet</p>
            ) : (
              <div className="space-y-2">
                {zones.map((zone, i) => (
                  <div key={i} className="flex items-center justify-between py-1.5 border-b border-gray-100 last:border-0">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded shadow-sm" style={{ background: zone.color }} />
                      <div>
                        <p className="text-xs font-bold text-gray-900">{zone.name}</p>
                        <p className="text-[10px] text-gray-500 font-medium uppercase">{zone.zone_type} · {zone.type} · {zone.points.length}pts</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setZones(prev => prev.filter((_, idx) => idx !== i))}
                      className="p-1 rounded text-gray-400 hover:text-rose-500 hover:bg-rose-50 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending || zones.length === 0}
              className={cn(
                "w-full mt-3 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-bold shadow-sm transition-all",
                saved
                  ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                  : "bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-40"
              )}
            >
              <Save className="w-4 h-4" />
              {saved ? "Saved!" : "Save Zones"}
            </button>
          </Card>
        </div>
      </div>
    </div>
  );
}
