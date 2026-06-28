"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { WS_LIVE_URL } from "@/lib/api";

export type LiveEvent = {
  type: string;
  camera_id?: string;
  track_id?: string;
  zone_name?: string;
  event_type?: string;
  queue_depth?: number;
  dwell_seconds?: number;
  timestamp?: string;
  x?: number;
  y?: number;
  [key: string]: unknown;
};

export function useLiveFeed(onEvent?: (event: LiveEvent) => void) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    try {
      const ws = new WebSocket(WS_LIVE_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        }, 25_000);
      };

      ws.onmessage = (e) => {
        try {
          const data: LiveEvent = JSON.parse(e.data);
          setLastEvent(data);
          onEvent?.(data);
        } catch {}
      };

      ws.onclose = () => {
        setConnected(false);
        clearInterval(pingRef.current!);
        setTimeout(connect, 3000); // reconnect
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      setTimeout(connect, 5000);
    }
  }, [onEvent]);

  useEffect(() => {
    connect();
    return () => {
      clearInterval(pingRef.current!);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, lastEvent };
}

export function useLiveCounts() {
  const [counts, setCounts] = useState({
    currentInStore: 0,
    todayEntries: 0,
    todayExits: 0,
    activeQueues: {} as Record<string, number>,
  });

  useLiveFeed(
    useCallback((event: LiveEvent) => {
      if (event.type === "track_start") {
        setCounts((prev) => ({
          ...prev,
          currentInStore: prev.currentInStore + 1,
          todayEntries: prev.todayEntries + 1,
        }));
      } else if (event.type === "track_end") {
        setCounts((prev) => ({
          ...prev,
          currentInStore: Math.max(0, prev.currentInStore - 1),
          todayExits: prev.todayExits + 1,
        }));
      } else if (event.type === "queue_update" && event.zone_name) {
        setCounts((prev) => ({
          ...prev,
          activeQueues: {
            ...prev.activeQueues,
            [event.zone_name!]: event.queue_depth ?? 0,
          },
        }));
      }
    }, [])
  );

  return counts;
}
