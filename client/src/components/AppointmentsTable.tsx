"use client";

import { CheckCircle } from "lucide-react";
import clsx from "clsx";
import type { Appointment } from "@/lib/api";

interface Props {
  appointments: Appointment[];
  newIds: Set<number>;
}

export function AppointmentsTable({ appointments, newIds }: Props) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden h-full">
      {/* Header */}
      <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Appointment Log
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {appointments.length} record{appointments.length !== 1 ? "s" : ""}
          </p>
        </div>
        {appointments.length > 0 && (
          <span className="text-xs text-emerald-600 font-medium bg-emerald-50 px-2 py-1 rounded-full">
            Live
          </span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/60">
              {["Code", "Patient", "Doctor", "Specialty", "Time", "Confirmed"].map(
                (col) => (
                  <th
                    key={col}
                    className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider"
                  >
                    {col}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {appointments.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-6 py-12 text-center text-sm text-slate-400"
                >
                  No appointments yet — Clara will populate this table in real
                  time as bookings are committed.
                </td>
              </tr>
            ) : (
              appointments.map((appt) => (
                <tr
                  key={appt.id}
                  className={clsx(
                    "transition-colors duration-500 hover:bg-slate-50",
                    newIds.has(appt.id)
                      ? "bg-emerald-50 animate-row-in"
                      : "bg-white"
                  )}
                >
                  {/* Reference code */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="font-mono text-xs font-semibold text-cyan-700 bg-cyan-50 px-2.5 py-1 rounded-md border border-cyan-100">
                      {appt.appointment_code}
                    </span>
                  </td>

                  {/* Patient */}
                  <td className="px-6 py-4 text-sm font-medium text-slate-900 whitespace-nowrap">
                    {appt.patient_name}
                  </td>

                  {/* Doctor */}
                  <td className="px-6 py-4 text-sm text-slate-700 whitespace-nowrap">
                    {appt.doctor_name}
                  </td>

                  {/* Specialty */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full capitalize">
                      {appt.specialty}
                    </span>
                  </td>

                  {/* Time */}
                  <td className="px-6 py-4 text-sm text-slate-700 whitespace-nowrap">
                    {appt.slot_time}
                  </td>

                  {/* Timestamp */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-1.5 text-emerald-600">
                      <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                      <span className="text-xs font-medium">
                        {new Date(appt.created_at).toLocaleTimeString("en-US", {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
