"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console but don't crash
    console.warn("Page error caught by boundary:", error.message);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] gap-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
        <AlertTriangle className="text-amber-400" size={28} />
      </div>
      <div>
        <h2 className="text-xl font-semibold text-white mb-2">Something went wrong</h2>
        <p className="text-white/40 text-sm max-w-sm">
          This page encountered an error loading data. The backend may still be starting up.
        </p>
      </div>
      <button
        onClick={reset}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500/30 text-blue-400 text-sm font-medium hover:bg-blue-500/30 transition-all"
      >
        <RefreshCw size={14} />
        Try Again
      </button>
    </div>
  );
}
