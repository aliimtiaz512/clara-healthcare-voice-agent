"use client";

import { CalendarCheck, Calendar, Users, TrendingUp } from "lucide-react";
import type { Stats } from "@/lib/api";

interface StatCardProps {
  label: string;
  value: string | number;
  sublabel: string;
  icon: React.ReactNode;
  iconColor: string;
}

function StatCard({ label, value, sublabel, icon, iconColor }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          {label}
        </span>
        <span className={iconColor}>{icon}</span>
      </div>
      <div className="text-3xl font-bold tracking-tight text-slate-900">
        {value}
      </div>
      <div className="text-xs text-slate-400 mt-1">{sublabel}</div>
    </div>
  );
}

export function StatsBar({ stats }: { stats: Stats | null }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <StatCard
        label="Appointments Booked"
        value={stats?.total_appointments ?? "—"}
        sublabel="All time"
        icon={<CalendarCheck className="w-5 h-5" />}
        iconColor="text-emerald-600"
      />
      <StatCard
        label="Available Slots"
        value={stats?.available_slots ?? "—"}
        sublabel="Across all doctors"
        icon={<Calendar className="w-5 h-5" />}
        iconColor="text-cyan-600"
      />
      <StatCard
        label="Active Doctors"
        value={stats?.total_doctors ?? "—"}
        sublabel="On roster"
        icon={<Users className="w-5 h-5" />}
        iconColor="text-slate-600"
      />
      <StatCard
        label="Occupancy"
        value={stats ? `${stats.occupancy_pct}%` : "—"}
        sublabel="Slots filled"
        icon={<TrendingUp className="w-5 h-5" />}
        iconColor="text-cyan-600"
      />
    </div>
  );
}
