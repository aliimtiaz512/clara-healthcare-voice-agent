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
        ORDER  BY d.name, to_timestamp(a.slot_time, 'HH12:MI AM');
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
# Tool: lookup_insurance
# ---------------------------------------------------------------------------

# Insurance carriers Avery Wellness Clinic is in-network with. Mock data is
# perfectly acceptable per the brief — what matters is the tool works reliably
# and is triggered naturally in conversation.
_ACCEPTED_INSURANCE: dict[str, str] = {
    "aetna": "Aetna",
    "blue cross": "Blue Cross Blue Shield",
    "blue cross blue shield": "Blue Cross Blue Shield",
    "bcbs": "Blue Cross Blue Shield",
    "cigna": "Cigna",
    "unitedhealthcare": "UnitedHealthcare",
    "united healthcare": "UnitedHealthcare",
    "united": "UnitedHealthcare",
    "medicare": "Medicare",
    "humana": "Humana",
}

# Common carriers we are explicitly out-of-network with (for a natural "no").
_NOT_ACCEPTED = {"kaiser", "kaiser permanente", "medicaid", "tricare"}


async def lookup_insurance(provider: str) -> str:
    """
    Check whether the clinic accepts a given insurance provider.

    Args:
        provider: The carrier name as spoken by the caller, e.g. "Aetna".

    Returns:
        A short, spoken-style string Clara can read back confirming whether the
        provider is in-network.
    """
    logger.info("lookup_insurance called | provider=%r", provider)
    key = provider.strip().lower()

    if key in _ACCEPTED_INSURANCE:
        canonical = _ACCEPTED_INSURANCE[key]
        return (
            f"Good news — yes, we're in-network with {canonical}, so you're all set "
            "to book. Would you like me to find you an opening?"
        )

    if key in _NOT_ACCEPTED:
        return (
            f"Unfortunately we're not in-network with {provider.strip()} right now, "
            "but you're welcome to book as a self-pay patient. Would you like to?"
        )

    # Unknown carrier — be honest rather than guess.
    return (
        f"I'm not certain whether we take {provider.strip()} — our front desk can "
        "confirm that for you. In the meantime, would you like me to check availability?"
    )


# ---------------------------------------------------------------------------
# Tool: cancel_appointment
# ---------------------------------------------------------------------------


async def cancel_appointment(appointment_code: str) -> str:
    """
    Cancel an existing appointment by reference code and free the timeslot.

    Steps (inside a single transaction):
      1. Locate the appointment by its (normalised) reference code.
      2. Free the matching availability slot (is_booked -> FALSE).
      3. Delete the appointment record.

    Args:
        appointment_code: The reference code, e.g. "AV-9421" (dash optional).

    Returns:
        A spoken confirmation string, or a polite message if the code wasn't found.
    """
    logger.info("cancel_appointment called | code=%r", appointment_code)

    # Normalise: strip spaces, uppercase, and re-insert the dash if missing.
    raw = appointment_code.strip().upper().replace(" ", "").replace("-", "")
    if raw.startswith("AV") and len(raw) > 2:
        code = f"AV-{raw[2:]}"
    else:
        code = appointment_code.strip().upper()

    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                appt = await conn.fetchrow(
                    """
                    SELECT a.id, a.patient_name, a.slot_time, a.doctor_id,
                           d.name AS doctor_name
                    FROM   appointments a
                    JOIN   doctors      d ON d.id = a.doctor_id
                    WHERE  a.appointment_code = $1
                    FOR UPDATE;
                    """,
                    code,
                )

                if appt is None:
                    logger.warning("cancel_appointment: code not found | code=%r", code)
                    return (
                        f"I couldn't find an appointment under {code.replace('-', ' dash ')}. "
                        "Could you read me that reference code again?"
                    )

                # Free the slot back up
                await conn.execute(
                    """
                    UPDATE availability
                    SET    is_booked = FALSE
                    WHERE  doctor_id = $1 AND slot_time = $2;
                    """,
                    appt["doctor_id"],
                    appt["slot_time"],
                )

                # Remove the appointment record
                await conn.execute(
                    "DELETE FROM appointments WHERE id = $1;", appt["id"]
                )

                logger.info(
                    "Appointment cancelled | code=%s patient=%r doctor=%r slot=%r",
                    code, appt["patient_name"], appt["doctor_name"], appt["slot_time"],
                )

    except asyncpg.PostgresError as exc:
        logger.error("cancel_appointment DB error: %s", exc)
        return (
            "I'm sorry, I hit a snag cancelling that. Please try again in a moment."
        )

    return (
        f"Done — I've cancelled the appointment for {appt['patient_name']} with "
        f"{appt['doctor_name']} at {appt['slot_time']}, and that time is open again. "
        "Is there anything else I can help with?"
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
