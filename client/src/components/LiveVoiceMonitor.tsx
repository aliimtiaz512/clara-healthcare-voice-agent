"use client";

import { useState, useCallback } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  BarVisualizer,
} from "@livekit/components-react";
import { Phone, PhoneOff } from "lucide-react";
import clsx from "clsx";
import { fetchToken } from "@/lib/api";

// ── Agent state badge config ─────────────────────────────────────────────────

type AgentState =
  | "disconnected"
  | "connecting"
  | "initializing"
  | "listening"
  | "thinking"
  | "speaking";

interface StateConfig {
  label: string;
  ringColor: string;
  dotColor: string;
  animate: string;
}

const STATE_CONFIG: Record<AgentState, StateConfig> = {
  disconnected: {
    label: "Idle",
    ringColor: "border-slate-200",
    dotColor: "bg-slate-300",
    animate: "",
  },
  connecting: {
    label: "Connecting …",
    ringColor: "border-amber-300",
    dotColor: "bg-amber-400",
    animate: "animate-pulse",
  },
  initializing: {
    label: "Initialising …",
    ringColor: "border-amber-300",
    dotColor: "bg-amber-400",
    animate: "animate-pulse",
  },
  listening: {
    // emerald pulsing ring — style.md "Listening State" spec
    label: "Listening",
    ringColor: "border-emerald-400",
    dotColor: "bg-emerald-500",
    animate: "animate-pulse-slow",
  },
  thinking: {
    // cyan spinning ring — style.md "Processing/Thinking State" spec
    label: "Processing",
    ringColor: "border-cyan-400",
    dotColor: "bg-cyan-500",
    animate: "animate-spin",
  },
  speaking: {
    label: "Speaking",
    ringColor: "border-cyan-500",
    dotColor: "bg-cyan-600",
    animate: "animate-pulse",
  },
};

// ── Inner component — must live inside <LiveKitRoom> to use hooks ─────────────

function AgentView({ onDisconnect }: { onDisconnect: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();
  const cfg = STATE_CONFIG[state as AgentState] ?? STATE_CONFIG.disconnected;

  return (
    <div className="flex flex-col items-center gap-4 py-4">
      {/* State indicator aura — style.md spec */}
      <div
        className={clsx(
          "relative w-24 h-24 rounded-full border-4 flex items-center justify-center",
          cfg.ringColor,
          cfg.animate === "animate-pulse-slow" && "animate-pulse-slow",
          cfg.animate === "animate-spin" && "animate-spin"
        )}
      >
        <div className={clsx("w-12 h-12 rounded-full", cfg.dotColor)} />
      </div>
      <span className="text-sm font-medium text-slate-600">{cfg.label}</span>

      {/* Waveform visualizer — style.md "audio track bar meter" spec */}
      <div className="w-full h-14 px-2">
        {audioTrack ? (
          <BarVisualizer
            trackRef={audioTrack}
            barCount={24}
            style={{ "--lk-fg": "#0891b2" } as React.CSSProperties}
            className="w-full h-full"
          />
        ) : (
          // Flat placeholder bars when no audio track is present
          <div className="flex items-end justify-center gap-0.5 h-full">
            {Array.from({ length: 24 }).map((_, i) => (
              <div
                key={i}
                className="flex-1 bg-slate-200 rounded-sm"
                style={{ height: "4px" }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Render the agent's audio into the page */}
      <RoomAudioRenderer />

      <button
        onClick={onDisconnect}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-50 hover:bg-red-100 active:bg-red-200 text-red-600 rounded-lg text-sm font-medium transition-colors"
      >
        <PhoneOff className="w-4 h-4" />
        End Call
      </button>
    </div>
  );
}

// ── Public component ─────────────────────────────────────────────────────────

export function LiveVoiceMonitor() {
  const [livekitToken, setLivekitToken] = useState<string>("");
  const [livekitUrl, setLivekitUrl] = useState<string>("");
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConnect = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { token, url } = await fetchToken(
        `admin-${Date.now()}`,
        "clara-clinic-room"
      );
      setLivekitToken(token);
      setLivekitUrl(url);
      setConnected(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleDisconnect = useCallback(() => {
    setConnected(false);
    setLivekitToken("");
    setLivekitUrl("");
  }, []);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
      {/* Card header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
          Live Voice Monitor
        </h2>
        <span
          className={clsx(
            "w-2 h-2 rounded-full",
            connected ? "bg-emerald-500 animate-pulse" : "bg-slate-300"
          )}
        />
      </div>

      {connected && livekitToken && livekitUrl ? (
        <LiveKitRoom
          serverUrl={livekitUrl}
          token={livekitToken}
          connect
          audio
          video={false}
          onDisconnected={handleDisconnect}
        >
          <AgentView onDisconnect={handleDisconnect} />
        </LiveKitRoom>
      ) : (
        <>
          {/* Idle state display */}
          <div className="flex flex-col items-center gap-4 py-6">
            <div className="w-24 h-24 rounded-full border-4 border-slate-200 flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-slate-200" />
            </div>
            <span className="text-sm text-slate-400 font-medium">
              Clara is idle
            </span>
            {/* Flat waveform placeholder */}
            <div className="w-full flex items-end justify-center gap-0.5 h-14 px-2">
              {Array.from({ length: 24 }).map((_, i) => (
                <div
                  key={i}
                  className="flex-1 bg-slate-100 rounded-sm"
                  style={{ height: "4px" }}
                />
              ))}
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-500 text-center mb-3 px-2">
              {error}
            </p>
          )}

          <button
            onClick={handleConnect}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-cyan-600 hover:bg-cyan-700 disabled:bg-cyan-300 active:bg-cyan-800 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <Phone className="w-4 h-4" />
            {loading ? "Connecting …" : "Start Test Call"}
          </button>
        </>
      )}
    </div>
  );
}
