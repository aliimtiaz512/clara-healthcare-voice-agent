"use client";

import { Activity } from "lucide-react";
import { StatsBar } from "@/components/StatsBar";
import { LiveVoiceMonitor } from "@/components/LiveVoiceMonitor";
import { TerminalLog } from "@/components/TerminalLog";
import { AppointmentsTable } from "@/components/AppointmentsTable";
import { useRealtime } from "@/hooks/useRealtime";

export default function Dashboard() {
  const { appointments, logs, stats, newIds, isConnected } = useRealtime();

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ── Top navigation bar ─────────────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-cyan-600 rounded-lg flex items-center justify-center shrink-0">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <div className="leading-tight">
              <p className="text-base font-bold tracking-tight text-slate-900">
                Avery Wellness Clinic
              </p>
              <p className="text-xs text-slate-400">
                Clara Voice Agent — Admin Dashboard
              </p>
            </div>
          </div>

          {/* SSE connection status chip */}
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${
                isConnected
                  ? "bg-emerald-500 animate-pulse"
                  : "bg-red-400"
              }`}
            />
            <span className="text-xs text-slate-500 font-medium">
              {isConnected ? "Live" : "Reconnecting …"}
            </span>
          </div>
        </div>
      </header>

      {/* ── Main content ───────────────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Row 1 — stat cards */}
        <StatsBar stats={stats} />

        {/* Row 2 — dual-column grid matching style.md spec:
              col-1  : voice monitor + terminal log
              col-2/3: appointment table                        */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left panel */}
          <div className="lg:col-span-1 flex flex-col gap-6">
            <LiveVoiceMonitor />
            <TerminalLog logs={logs} />
          </div>

          {/* Right panel */}
          <div className="lg:col-span-2">
            <AppointmentsTable appointments={appointments} newIds={newIds} />
          </div>
        </div>
      </main>
    </div>
  );
}
