import { useState, useEffect, useRef, useCallback } from "react";
import { API_BASE, Appointment, LogEntry, Stats, fetchStats } from "@/lib/api";

interface RealtimeState {
  appointments: Appointment[];
  logs: LogEntry[];
  stats: Stats | null;
  newIds: Set<number>;
  isConnected: boolean;
}

/**
 * Opens a Server-Sent Events connection to the FastAPI /api/events endpoint
 * and maintains live appointment + log state for the dashboard.
 *
 * Events:
 *   snapshot    → full initial payload (appointments + last 50 logs)
 *   appointment → single new row — prepended to list, highlighted 4 s
 *   log         → single new agent_logs entry — appended (capped at 200)
 *   ping        → ignored keepalive
 */
export function useRealtime(): RealtimeState {
  const [state, setState] = useState<RealtimeState>({
    appointments: [],
    logs: [],
    stats: null,
    newIds: new Set(),
    isConnected: false,
  });

  const refreshStats = useCallback(async () => {
    try {
      const s = await fetchStats();
      setState((prev) => ({ ...prev, stats: s }));
    } catch {
      // silently skip — dashboard will try again on next event
    }
  }, []);

  useEffect(() => {
    refreshStats();

    const es = new EventSource(`${API_BASE}/api/events`);

    es.onopen = () => setState((p) => ({ ...p, isConnected: true }));
    es.onerror = () => setState((p) => ({ ...p, isConnected: false }));

    es.addEventListener("snapshot", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      setState((prev) => ({
        ...prev,
        appointments: data.appointments ?? [],
        logs: data.logs ?? [],
        isConnected: true,
      }));
      refreshStats();
    });

    es.addEventListener("appointment", (e) => {
      const appt: Appointment = JSON.parse((e as MessageEvent).data);
      setState((prev) => {
        const ids = new Set(prev.newIds);
        ids.add(appt.id);
        return {
          ...prev,
          appointments: [appt, ...prev.appointments],
          newIds: ids,
        };
      });
      // Remove the green "new row" highlight after 4 s
      setTimeout(() => {
        setState((prev) => {
          const ids = new Set(prev.newIds);
          ids.delete(appt.id);
          return { ...prev, newIds: ids };
        });
      }, 4000);
      refreshStats();
    });

    es.addEventListener("log", (e) => {
      const entry: LogEntry = JSON.parse((e as MessageEvent).data);
      setState((prev) => ({
        ...prev,
        // Keep a rolling window of the last 200 log lines
        logs: [...prev.logs.slice(-199), entry],
      }));
    });

    return () => es.close();
  }, [refreshStats]);

  return state;
}
