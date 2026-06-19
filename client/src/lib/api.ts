export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Appointment {
  id: number;
  appointment_code: string;
  patient_name: string;
  doctor_name: string;
  specialty: string;
  slot_time: string;
  created_at: string;
}

export interface LogEntry {
  id: number;
  level: string;
  tool: string | null;
  message: string;
  created_at: string;
}

export interface Stats {
  total_appointments: number;
  total_slots: number;
  booked_slots: number;
  available_slots: number;
  total_doctors: number;
  occupancy_pct: number;
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/api/stats`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function fetchToken(
  identity: string,
  room = "clara-clinic-room"
): Promise<{ token: string; url: string; room: string }> {
  const res = await fetch(`${API_BASE}/api/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identity, room }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? "Failed to get LiveKit token");
  }
  return res.json();
}
