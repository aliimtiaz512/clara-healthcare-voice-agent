#!/usr/bin/env bash
# Clara – start all services on Linux/macOS.
# Run from the repo root:  ./start.sh
#
# Starts (in the background): LiveKit dev server, FastAPI admin API, Next.js
# dashboard. The voice agent is started in the foreground so you can watch its
# logs; Ctrl+C stops everything.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LK="$ROOT/livekit-server/livekit-server"
SRV="$ROOT/server"
CLI="$ROOT/client"

# Pick the Python interpreter from whichever venv exists.
if   [ -x "$ROOT/.venv/bin/python" ];      then PY="$ROOT/.venv/bin/python"
elif [ -x "$SRV/.venv/bin/python" ];       then PY="$SRV/.venv/bin/python"
else PY="python3"; fi

echo "=================================================="
echo "  Clara – Avery Wellness Clinic Voice Agent"
echo "=================================================="

if [ ! -x "$LK" ]; then
  echo "LiveKit server binary not found. Fetching it ..."
  "$ROOT/scripts/get-livekit.sh"
fi

pids=()
cleanup() { echo; echo "Stopping services ..."; kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "[1/4] LiveKit server on :7880 ..."
"$LK" --dev --bind 0.0.0.0 > /tmp/clara-livekit.log 2>&1 & pids+=($!)
sleep 2

echo "[2/4] FastAPI admin API on :8000 ..."
( cd "$SRV" && "$PY" -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload > /tmp/clara-api.log 2>&1 ) & pids+=($!)
sleep 2

echo "[3/4] Next.js dashboard on :3000 ..."
( cd "$CLI" && npm run dev > /tmp/clara-client.log 2>&1 ) & pids+=($!)
sleep 2

echo "[4/4] Clara voice agent (foreground — Ctrl+C to stop all) ..."
echo "--------------------------------------------------"
echo "  Dashboard  →  http://localhost:3000"
echo "  Admin API  →  http://localhost:8000/docs"
echo "  Logs       →  /tmp/clara-*.log"
echo "--------------------------------------------------"
cd "$SRV" && exec "$PY" agent.py dev
