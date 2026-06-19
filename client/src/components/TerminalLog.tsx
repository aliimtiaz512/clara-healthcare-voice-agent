"use client";

import { useEffect, useRef } from "react";
import type { LogEntry } from "@/lib/api";

// Colour mapping matches the style.md terminal typography spec
const LEVEL_STYLES: Record<string, string> = {
  INFO: "text-cyan-400",
  SUCCESS: "text-emerald-400",
  WARNING: "text-amber-400",
  ERROR: "text-red-400",
  DEBUG: "text-slate-500",
};

export function TerminalLog({ logs }: { logs: LogEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the newest entry whenever the log grows
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Panel header */}
      <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
        <span className="flex gap-1">
          <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
        </span>
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider ml-1">
          Agent Activity Log
        </span>
      </div>

      {/* Terminal body — matches style.md typography spec exactly */}
      <div className="font-mono text-sm bg-slate-950 text-cyan-400 p-4 h-60 overflow-y-auto scrollbar-terminal">
        {logs.length === 0 ? (
          <span className="text-slate-600 text-xs">
            Waiting for agent activity …
          </span>
        ) : (
          logs.map((entry) => {
            const time = new Date(entry.created_at).toLocaleTimeString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              hour12: false,
            });
            const levelStyle = LEVEL_STYLES[entry.level] ?? "text-cyan-400";
            return (
              <div key={entry.id} className="mb-1 leading-relaxed break-words">
                <span className="text-slate-600 select-none">{time} </span>
                <span className={`${levelStyle} font-medium`}>
                  {entry.level}{" "}
                </span>
                {entry.tool && (
                  <span className="text-slate-400">[{entry.tool}] </span>
                )}
                <span className="text-slate-300">{entry.message}</span>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
