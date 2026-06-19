"""
Clara Admin API – FastAPI server.

Endpoints:
  GET  /api/health          → service liveness probe
  GET  /api/stats           → aggregate counts for the dashboard header cards
  GET  /api/appointments    → full appointment list, newest first
  GET  /api/doctors         → doctor roster
  GET  /api/availability    → slot grid (optional ?specialty= filter)
  GET  /api/events          → SSE stream — appointment + agent log events
  POST /api/token           → issue a short-lived LiveKit JWT for the browser client

Run with:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import db
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voice-agent.api")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API server starting — warming database pool …")
    await db.get_pool()
    yield
    logger.info("API server shutting down — draining database pool …")
    await db.close_pool()


app = FastAPI(
    title="Clara Admin API",
    description="Real-time admin API for the Avery Wellness Clinic voice scheduling agent.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TokenRequest(BaseModel):
    identity: str
    room: str = "clara-clinic-room"


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _fmt_appointment(r) -> dict:
    return {
        "id": r["id"],
        "appointment_code": r["appointment_code"],
        "patient_name": r["patient_name"],
        "doctor_name": r["doctor_name"],
        "specialty": r["specialty"],
        "slot_time": r["slot_time"],
        "created_at": r["created_at"].isoformat(),
    }


def _fmt_log(r) -> dict:
    return {
        "id": r["id"],
        "level": r["level"],
        "tool": r["tool"],
        "message": r["message"],
        "created_at": r["created_at"].isoformat(),
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "clara-admin-api"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/api/stats", tags=["data"])
async def get_stats():
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        total_appointments = await conn.fetchval("SELECT COUNT(*) FROM appointments;")
        total_slots = await conn.fetchval("SELECT COUNT(*) FROM availability;")
        booked_slots = await conn.fetchval(
            "SELECT COUNT(*) FROM availability WHERE is_booked = TRUE;"
        )
        total_doctors = await conn.fetchval("SELECT COUNT(*) FROM doctors;")

    available = total_slots - booked_slots
    return {
        "total_appointments": total_appointments,
        "total_slots": total_slots,
        "booked_slots": booked_slots,
        "available_slots": available,
        "total_doctors": total_doctors,
        "occupancy_pct": round(
            (booked_slots / total_slots * 100) if total_slots else 0.0, 1
        ),
    }


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------


@app.get("/api/appointments", tags=["data"])
async def get_appointments():
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id, a.appointment_code, a.patient_name,
                   d.name AS doctor_name, d.specialty, a.slot_time, a.created_at
            FROM   appointments a
            JOIN   doctors      d ON d.id = a.doctor_id
            ORDER  BY a.created_at DESC;
            """
        )
    return [_fmt_appointment(r) for r in rows]


# ---------------------------------------------------------------------------
# Doctors
# ---------------------------------------------------------------------------


@app.get("/api/doctors", tags=["data"])
async def get_doctors():
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, specialty FROM doctors ORDER BY name;"
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


@app.get("/api/availability", tags=["data"])
async def get_availability(specialty: str | None = Query(default=None)):
    pool = await db.get_pool()
    if specialty:
        sql = """
            SELECT d.name AS doctor_name, d.specialty, a.slot_time, a.is_booked
            FROM   availability a
            JOIN   doctors      d ON d.id = a.doctor_id
            WHERE  LOWER(d.specialty) = LOWER($1)
            ORDER  BY d.name, a.slot_time;
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, specialty)
    else:
        sql = """
            SELECT d.name AS doctor_name, d.specialty, a.slot_time, a.is_booked
            FROM   availability a
            JOIN   doctors      d ON d.id = a.doctor_id
            ORDER  BY d.specialty, d.name, a.slot_time;
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Server-Sent Events — combined appointment + agent log stream
# ---------------------------------------------------------------------------


@app.get("/api/events", tags=["realtime"])
async def sse_events():
    """
    Long-lived SSE stream consumed by the Next.js dashboard.

    Event types:
      snapshot    — on connect: full appointment list + last 50 log lines
      appointment — a single newly committed appointment row
      log         — a single new agent_logs entry
      ping        — keepalive every ~15 s to prevent proxy timeouts
    """

    async def generate():
        pool = await db.get_pool()

        # ── Initial snapshot ──────────────────────────────────────────────
        async with pool.acquire() as conn:
            appt_rows = await conn.fetch(
                """
                SELECT a.id, a.appointment_code, a.patient_name,
                       d.name AS doctor_name, d.specialty, a.slot_time, a.created_at
                FROM   appointments a
                JOIN   doctors      d ON d.id = a.doctor_id
                ORDER  BY a.created_at DESC;
                """
            )
            log_rows = await conn.fetch(
                """
                SELECT id, level, tool, message, created_at
                FROM   agent_logs
                ORDER  BY created_at DESC
                LIMIT  50;
                """
            )

        last_appt_id: int = appt_rows[0]["id"] if appt_rows else 0
        last_log_id: int = log_rows[0]["id"] if log_rows else 0

        snapshot = {
            "appointments": [_fmt_appointment(r) for r in appt_rows],
            "logs": [_fmt_log(r) for r in reversed(log_rows)],
        }
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

        # ── Polling loop ──────────────────────────────────────────────────
        tick = 0
        while True:
            await asyncio.sleep(2)
            tick += 1

            try:
                pool = await db.get_pool()
                async with pool.acquire() as conn:
                    new_appts = await conn.fetch(
                        """
                        SELECT a.id, a.appointment_code, a.patient_name,
                               d.name AS doctor_name, d.specialty, a.slot_time, a.created_at
                        FROM   appointments a
                        JOIN   doctors      d ON d.id = a.doctor_id
                        WHERE  a.id > $1
                        ORDER  BY a.created_at ASC;
                        """,
                        last_appt_id,
                    )
                    new_logs = await conn.fetch(
                        """
                        SELECT id, level, tool, message, created_at
                        FROM   agent_logs
                        WHERE  id > $1
                        ORDER  BY created_at ASC;
                        """,
                        last_log_id,
                    )

                for row in new_appts:
                    last_appt_id = row["id"]
                    yield f"event: appointment\ndata: {json.dumps(_fmt_appointment(row))}\n\n"

                for row in new_logs:
                    last_log_id = row["id"]
                    yield f"event: log\ndata: {json.dumps(_fmt_log(row))}\n\n"

                if tick % 8 == 0:
                    yield "event: ping\ndata: {}\n\n"

            except Exception as exc:
                logger.error("SSE generation error: %s", exc)
                yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
                await asyncio.sleep(5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# LiveKit token generation
# ---------------------------------------------------------------------------


@app.post("/api/token", tags=["livekit"])
async def generate_token(body: TokenRequest):
    """
    Issue a short-lived LiveKit JWT so a browser client can join the clinic room.
    Used by the Next.js dashboard's test-call feature.
    """
    try:
        from livekit.api import AccessToken, VideoGrants

        token = (
            AccessToken(
                api_key=os.environ["LIVEKIT_API_KEY"],
                api_secret=os.environ["LIVEKIT_API_SECRET"],
            )
            .with_identity(body.identity)
            .with_name(body.identity)
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=body.room,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
            .to_jwt()
        )
        return {"token": token, "url": os.environ["LIVEKIT_URL"], "room": body.room}

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="livekit-api is not installed. Run: pip install livekit-api",
        )
    except Exception as exc:
        logger.error("Token generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
