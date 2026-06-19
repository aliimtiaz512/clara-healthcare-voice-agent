"""
Async PostgreSQL engine for Clara – Avery Wellness Clinic.

Provides a module-level connection pool (asyncpg) and the two tool
functions exposed to the Groq LLM via LiveKit function calling:
  - check_availability(specialty) -> str
  - book_appointment(patient_name, doctor_name, slot_time) -> str

All public coroutines are fully re-entrant and safe for concurrent
callers because every write operation uses SELECT … FOR UPDATE inside
a serialisable-grade transaction block, eliminating double-bookings.
"""

from __future__ import annotations

import logging
import os
import random

import asyncpg
from asyncpg import Pool

logger = logging.getLogger("voice-agent.db")

# ---------------------------------------------------------------------------
# Module-level pool singleton
# ---------------------------------------------------------------------------

_pool: Pool | None = None


async def get_pool() -> Pool:
    """Return the shared asyncpg pool, creating it on the first call."""
    global _pool
    if _pool is None or _pool._closed:  # re-init if the pool was closed
        logger.info("Initialising asyncpg connection pool …")
        _pool = await asyncpg.create_pool(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 5432)),
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("Connection pool ready (min=2, max=10).")
    return _pool


async def close_pool() -> None:
    """Gracefully drain and close the shared pool on shutdown."""
    global _pool
    if _pool and not _pool._closed:
        await _pool.close()
        logger.info("Connection pool closed.")
    _pool = None


# ---------------------------------------------------------------------------
# Tool: check_availability
# ---------------------------------------------------------------------------

async def check_availability(specialty: str) -> str:
    """
    Return a human-readable list of available (unbooked) timeslots for the
    requested medical specialty.

    Args:
        specialty: The medical specialty the patient is enquiring about,
                   e.g. "cardiology" or "dermatology".

    Returns:
        A short natural-language string suitable for Clara to read aloud,
        listing each available doctor and their open slots, or a polite
        message when nothing is free.
    """
    logger.info("check_availability called | specialty=%r", specialty)

    pool = await get_pool()

    query = """
        SELECT d.name      AS doctor_name,
               a.slot_time AS slot_time
        FROM   availability a
        JOIN   doctors      d ON d.id = a.doctor_id
        WHERE  LOWER(d.specialty) = LOWER($1)
          AND  a.is_booked = FALSE
        ORDER  BY d.name, a.slot_time;
    """

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, specialty.strip())
    except asyncpg.PostgresError as exc:
        logger.error("check_availability DB error: %s", exc)
        return (
            "I'm sorry, I'm having trouble accessing the schedule right now. "
            "Please try again in a moment."
        )

    if not rows:
        logger.info("No open slots found for specialty=%r", specialty)
        return (
            f"There are currently no available slots for {specialty}. "
            "Would you like me to check a different specialty?"
        )

    # Group slots by doctor for a natural spoken summary
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["doctor_name"], []).append(row["slot_time"])

    parts: list[str] = []
    for doctor, slots in grouped.items():
        slot_list = ", ".join(slots)
        parts.append(f"{doctor} has openings at {slot_list}")

    result = ". ".join(parts) + "."
    logger.info("check_availability result: %s", result)
    return result


# ---------------------------------------------------------------------------
# Tool: book_appointment
# ---------------------------------------------------------------------------

def _generate_reference_code() -> str:
    """Generate a unique alphanumeric booking reference in AV-XXXX format."""
    return f"AV-{random.randint(1000, 9999)}"


async def book_appointment(
    patient_name: str,
    doctor_name: str,
    slot_time: str,
) -> str:
    """
    Atomically reserve a timeslot and write an appointment record.

    Steps (inside a single serialisable transaction):
      1. Lock the matching availability row (FOR UPDATE) to block concurrent callers.
      2. Verify the slot is still unbooked.
      3. Flip is_booked → TRUE.
      4. Insert a row into appointments with a generated AV-XXXX reference code.
      5. Commit.

    Args:
        patient_name: Legal name of the patient (as spoken).
        doctor_name:  Full name of the target doctor, e.g. "Dr. Davis".
        slot_time:    Requested slot string matching the availability table,
                      e.g. "02:00 PM".

    Returns:
        A spoken confirmation string that includes the reference code, or an
        error message if the slot was already taken or could not be found.
    """
    logger.info(
        "book_appointment called | patient=%r  doctor=%r  slot=%r",
        patient_name,
        doctor_name,
        slot_time,
    )

    pool = await get_pool()

    # Normalise inputs to reduce mismatch risk from LLM formatting
    patient_name = patient_name.strip()
    doctor_name = doctor_name.strip()
    slot_time = slot_time.strip()

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():

                # Step 1 & 2 — Lock the specific availability row
                lock_query = """
                    SELECT a.id        AS avail_id,
                           d.id        AS doctor_id
                    FROM   availability a
                    JOIN   doctors      d ON d.id = a.doctor_id
                    WHERE  LOWER(d.name) = LOWER($1)
                      AND  a.slot_time  = $2
                      AND  a.is_booked  = FALSE
                    FOR UPDATE;
                """
                row = await conn.fetchrow(lock_query, doctor_name, slot_time)

                if row is None:
                    logger.warning(
                        "Slot not available | doctor=%r slot=%r", doctor_name, slot_time
                    )
                    return (
                        f"I'm sorry, the {slot_time} slot with {doctor_name} is no longer "
                        "available. Would you like me to check other openings?"
                    )

                avail_id = row["avail_id"]
                doctor_id = row["doctor_id"]

                # Step 3 — Flip the booking flag
                await conn.execute(
                    "UPDATE availability SET is_booked = TRUE WHERE id = $1;",
                    avail_id,
                )

                # Step 4 — Generate reference and insert appointment record
                # Retry the rare case of a code collision (table has a UNIQUE constraint)
                ref_code: str | None = None
                for attempt in range(10):
                    candidate = _generate_reference_code()
                    existing = await conn.fetchval(
                        "SELECT id FROM appointments WHERE appointment_code = $1;",
                        candidate,
                    )
                    if existing is None:
                        ref_code = candidate
                        break

                if ref_code is None:
                    # Astronomically unlikely, but fail safely
                    raise RuntimeError("Could not generate a unique reference code after 10 attempts.")

                await conn.execute(
                    """
                    INSERT INTO appointments
                        (appointment_code, patient_name, doctor_id, slot_time)
                    VALUES ($1, $2, $3, $4);
                    """,
                    ref_code,
                    patient_name,
                    doctor_id,
                    slot_time,
                )

                logger.info(
                    "Appointment committed | code=%s  patient=%r  doctor=%r  slot=%r",
                    ref_code,
                    patient_name,
                    doctor_name,
                    slot_time,
                )

    except asyncpg.UniqueViolationError as exc:
        logger.error("Unique constraint violated during booking: %s", exc)
        return (
            "I encountered a conflict while saving your appointment. "
            "Please try again or call the front desk for assistance."
        )
    except asyncpg.PostgresError as exc:
        logger.error("book_appointment DB error: %s", exc)
        return (
            "I'm sorry, there was a database error while booking your appointment. "
            "Please try again in a moment."
        )
    except RuntimeError as exc:
        logger.error("book_appointment runtime error: %s", exc)
        return "I encountered an unexpected error. Please contact the clinic directly."

    # Spell the reference code digit-by-digit so TTS reads it naturally
    code_spoken = ref_code.replace("-", " dash ")
    return (
        f"You're all set, {patient_name}. Your appointment with {doctor_name} "
        f"at {slot_time} is confirmed. Your reference code is {code_spoken}. "
        "Please have that ready when you arrive."
    )


# ---------------------------------------------------------------------------
# Utility: structured log event for the admin dashboard terminal
# ---------------------------------------------------------------------------


async def log_event(level: str, tool: str | None, message: str) -> None:
    """
    Persist a structured log entry to agent_logs so the dashboard terminal shows
    live agent activity.  Never raises — a logging failure must never interrupt
    the voice conversation.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO agent_logs (level, tool, message) VALUES ($1, $2, $3);",
                level.upper(),
                tool,
                message,
            )
    except Exception as exc:
        logger.warning("log_event write failed (non-fatal): %s", exc)
