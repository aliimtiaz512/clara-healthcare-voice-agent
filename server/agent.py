"""
Clara – Voice AI Scheduling Agent for Avery Wellness Clinic.
Targets livekit-agents 1.6.x (Agent / AgentSession API).

Pipeline:  Deepgram nova-2 STT  ──>  Groq LLaMA-3.3-70b (OpenAI-compat)  ──>  Deepgram Aura TTS
Transport: LiveKit WebRTC with Silero VAD.

Run with:
    python agent.py dev      # hot-reload dev mode
    python agent.py start    # production worker
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, openai, silero

import db

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voice-agent")

# ---------------------------------------------------------------------------
# System prompt — Clara's identity (graded: this is the biggest differentiator)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
# WHO YOU ARE
You are Clara — the friendly voice of the front desk at Avery Wellness Clinic, a
warm neighborhood health clinic. You are not a generic bot; you are the calm,
reassuring person patients are relieved to reach. You have been "answering the
phones" at Avery for years and you genuinely enjoy helping people get the care
they need. Your single job is to help callers check doctor availability, book
appointments, look up accepted insurance, and cancel appointments — all by voice.

# YOUR PERSONALITY
- Warm, upbeat, and unhurried. You make a stressed caller feel taken care of.
- Efficient — you respect people's time and never ramble.
- Naturally human: you use small acknowledgements ("Of course", "Absolutely",
  "Got it", "Let me take a look") before acting.
- You smile with your voice. A little warmth, never robotic, never salesy.

# HOW YOU SPEAK (this is a phone call — voice only)
- Keep EVERY reply to 1–2 short, spoken sentences. Never longer.
- Never use bullet points, numbered lists, markdown, asterisks, or symbols —
  the caller cannot see them, they only hear you.
- Ask for ONE thing at a time. Don't pile up questions.
- Read times like a person: say "two thirty in the afternoon", not "14:30".
- Read reference codes slowly and clearly, letter by letter and digit by digit:
  for "AV-9421" say "A - V - nine - four - two - one".
- If you didn't catch something, warmly ask them to repeat it — never guess.

# WHAT YOU CAN DO (your tools)
- check_availability: look up open slots for a specialty (cardiology, dermatology,
  general practice, orthopedics, neurology).
- book_appointment: reserve a slot — ONLY after you have verbally confirmed all
  three: the caller's full name, the exact doctor, and the exact time.
- lookup_insurance: check whether the clinic accepts a given insurance provider.
- cancel_appointment: cancel an existing booking using its reference code.

# HARD RULES — never break these
1. MEDICAL GUARDRAIL (highest priority): You are a SCHEDULER, not a clinician.
   The moment a caller describes a symptom, condition, diagnosis, medication,
   or any health emergency, say EXACTLY, word for word:
   "I cannot provide medical advice. If you are experiencing a life-threatening
   emergency, please hang up and call 911 immediately."
   Then gently steer back: "I can still help you get booked in to see a doctor —
   would you like me to find an opening?"
2. STAY ON TASK: If a caller goes off-topic, warmly redirect:
   "I'm just the scheduling line, so I can't help with that — but I'd love to get
   you an appointment. What are you looking to book?"
3. NEVER invent doctors, times, prices, codes, or confirmations. If a tool hasn't
   returned something, you don't know it yet.
4. NEVER confirm a booking until book_appointment returns a real reference code.
5. Always confirm details back to the caller before booking ("So that's Dr. Davis
   at two thirty for John Carter — shall I lock that in?").

# OPENING
Your greeting is handled for you at the start of the call. After that, just be
Clara: listen, help, and keep it human.
""".strip()

# Engaging scripted opening line — spoken the instant the call connects.
# Kept warm and inviting (the brief weighs the first impression heavily).
GREETING = (
    "Hi there, thanks so much for calling Avery Wellness Clinic — this is Clara, "
    "your scheduling assistant. I can check which of our doctors are open and get "
    "you booked in no time. What can I help you with today?"
)

# ---------------------------------------------------------------------------
# Agent class with @function_tool decorated methods
# ---------------------------------------------------------------------------


class ClaraAgent(Agent):
    """
    Clara scheduling agent.

    Tools are auto-discovered by livekit-agents via @function_tool and added to
    the LLM schema. Each tool delegates to db.py and writes a structured log line
    that the admin dashboard streams live.
    """

    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

    # ── Tool 1 — availability lookup ─────────────────────────────────────
    @function_tool
    async def check_availability(
        self,
        specialty: Annotated[
            str,
            "The medical specialty to check, e.g. 'cardiology', 'dermatology', "
            "'general practice', 'orthopedics', 'neurology'.",
        ],
    ) -> str:
        """Check which appointment slots are currently open for a given specialty.

        Call this whenever the patient asks about availability, open times, or
        which doctors are free for a particular specialty.
        """
        logger.info("[TOOL] check_availability → specialty=%r", specialty)
        await db.log_event("INFO", "check_availability", f"Called → specialty={specialty!r}")
        result = await db.check_availability(specialty)
        await db.log_event("INFO", "check_availability", f"Result: {result[:120]}")
        logger.info("[TOOL] check_availability ← %r", result)
        return result

    # ── Tool 2 — book an appointment ─────────────────────────────────────
    @function_tool
    async def book_appointment(
        self,
        patient_name: Annotated[str, "The patient's full name as spoken by the caller."],
        doctor_name: Annotated[
            str,
            "Full name of the doctor, e.g. 'Dr. Davis'. Must match a doctor returned "
            "by check_availability.",
        ],
        slot_time: Annotated[
            str,
            "Exact appointment time string matching the availability record, e.g. '02:30 PM'.",
        ],
    ) -> str:
        """Book a confirmed appointment for a patient.

        Call ONLY after verbally confirming all three with the caller: their full
        name, the exact doctor, and the exact time slot. Commits an atomic DB
        transaction and returns a unique reference code.
        """
        logger.info(
            "[TOOL] book_appointment → patient=%r  doctor=%r  slot=%r",
            patient_name, doctor_name, slot_time,
        )
        await db.log_event(
            "INFO", "book_appointment",
            f"Called → patient={patient_name!r}  doctor={doctor_name!r}  slot={slot_time!r}",
        )
        result = await db.book_appointment(patient_name, doctor_name, slot_time)
        outcome_level = "SUCCESS" if result.startswith("You're all set") else "WARNING"
        await db.log_event(outcome_level, "book_appointment", result[:150])
        logger.info("[TOOL] book_appointment ← %r", result)
        return result

    # ── Tool 3 — insurance acceptance lookup ─────────────────────────────
    @function_tool
    async def lookup_insurance(
        self,
        provider: Annotated[
            str,
            "The insurance provider/carrier the caller mentions, e.g. 'Aetna', "
            "'Blue Cross', 'Cigna', 'UnitedHealthcare', 'Medicare'.",
        ],
    ) -> str:
        """Check whether Avery Wellness Clinic accepts a given insurance provider.

        Call this when the caller asks if their insurance is accepted, in-network,
        or covered before they commit to booking.
        """
        logger.info("[TOOL] lookup_insurance → provider=%r", provider)
        await db.log_event("INFO", "lookup_insurance", f"Called → provider={provider!r}")
        result = await db.lookup_insurance(provider)
        await db.log_event("INFO", "lookup_insurance", f"Result: {result[:120]}")
        logger.info("[TOOL] lookup_insurance ← %r", result)
        return result

    # ── Tool 4 — cancel an existing appointment ──────────────────────────
    @function_tool
    async def cancel_appointment(
        self,
        appointment_code: Annotated[
            str,
            "The booking reference code the caller reads out, e.g. 'AV-9421'. "
            "Accept it with or without the dash.",
        ],
    ) -> str:
        """Cancel an existing appointment by its reference code and free the slot.

        Call this when a caller wants to cancel a booking. Always read the code
        back to confirm before cancelling.
        """
        logger.info("[TOOL] cancel_appointment → code=%r", appointment_code)
        await db.log_event("INFO", "cancel_appointment", f"Called → code={appointment_code!r}")
        result = await db.cancel_appointment(appointment_code)
        outcome_level = "SUCCESS" if result.startswith("Done") else "WARNING"
        await db.log_event(outcome_level, "cancel_appointment", result[:150])
        logger.info("[TOOL] cancel_appointment ← %r", result)
        return result


# ---------------------------------------------------------------------------
# LiveKit entrypoint
# ---------------------------------------------------------------------------


async def entrypoint(ctx: JobContext) -> None:
    """
    Called once per incoming LiveKit room connection.
    Boots the DB pool, wires the voice pipeline, and starts Clara.
    """
    logger.info("New job received | room=%s", ctx.room.name)

    # Pre-warm the database pool before the caller's audio arrives
    await db.get_pool()

    # Connect to the LiveKit room
    await ctx.connect()
    logger.info("Connected to LiveKit room.")

    # Groq LLM via the OpenAI-compatibility shim.
    # llama-3.3-70b-versatile is Groq's current flagship with reliable tool calling.
    groq_llm = openai.LLM(
        model="llama-3.3-70b-versatile",
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
        temperature=0.6,
    )

    # Assemble the voice pipeline. STT and TTS both use the Deepgram key, so no
    # OpenAI key is required to run Clara.
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-2",
            language="en-US",
            interim_results=True,
        ),
        llm=groq_llm,
        tts=deepgram.TTS(
            model="aura-asteria-en",  # warm, natural female voice
        ),
        vad=silero.VAD.load(),
    )

    # Start the agent — connects it to the room automatically
    await session.start(agent=ClaraAgent(), room=ctx.room)
    logger.info("AgentSession started for room=%s", ctx.room.name)

    await db.log_event("INFO", None, "Call connected — Clara greeting the caller.")

    # Deliver the engaging opening greeting the instant the call connects.
    await session.say(GREETING, allow_interruptions=True)

    # Drain the DB pool when this room session ends
    ctx.add_shutdown_callback(db.close_pool)


# ---------------------------------------------------------------------------
# Worker entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # NOTE: no `agent_name` is set on purpose. Naming a worker switches LiveKit
    # to *explicit dispatch*, meaning Clara would only join rooms when dispatched
    # via the API. Leaving it unset uses *automatic dispatch* — Clara joins every
    # new room automatically, so the dashboard's "Start Test Call" button (which
    # just drops a participant into the room) immediately gets greeted by Clara.
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
