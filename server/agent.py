"""
Clara – Voice AI Scheduling Agent for Avery Wellness Clinic.
Targets livekit-agents 1.6.x (Agent / AgentSession API).

Pipeline:  Deepgram nova-2 STT  ──>  Groq LLaMA-3-70b (OpenAI-compat)  ──>  OpenAI TTS
Transport: LiveKit WebRTC with Silero VAD.

Run with:
    python agent.py start
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    RunContext,
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
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are Clara, a professional AI scheduling assistant for Avery Wellness Clinic.
Your only job is to help patients check doctor availability and book appointments by phone.

STRICT RULES — follow these without exception:

1. RESPONSE LENGTH: Every reply must be 1 to 2 short, conversational sentences.
   Never use bullet points, numbered lists, markdown, or long paragraphs.
   Read times and codes back naturally, exactly as a human receptionist would speak them.

2. MEDICAL EMERGENCY GUARDRAIL (highest priority rule):
   If the caller mentions any symptom, diagnosis, health condition, or emergency —
   immediately say exactly this, word for word, with no additions:
   "I cannot provide medical advice. If you are experiencing a life-threatening emergency,
   please hang up and call 911 immediately."
   Then gently redirect them back to scheduling after the warning.

3. OUT-OF-SCOPE REDIRECTION:
   If the caller raises any topic unrelated to scheduling or clinic availability, say:
   "I can help you with scheduling or availability, but I'm unable to discuss that.
   What kind of appointment are you looking to book today?"

4. TOOL DISCIPLINE:
   - Use check_availability when the caller asks which slots or doctors are free.
   - Use book_appointment ONLY after confirming ALL three from the caller:
     their full name, the exact doctor name, and the exact time slot.
   - Never invent or assume confirmation without explicit caller agreement.
   - Never confirm a booking before the tool returns a reference code.

5. NATURAL DATA READING:
   When reading back appointment codes (e.g., AV-9421), say "A V dash nine four two one".
   When reading times, say "two o'clock PM", not "14:00" in a robotic tone.
""".strip()

# ---------------------------------------------------------------------------
# Agent class with @function_tool decorated methods
# ---------------------------------------------------------------------------


class ClaraAgent(Agent):
    """
    Clara scheduling agent.

    Tools (check_availability, book_appointment) are auto-discovered by the
    livekit-agents framework via @function_tool and added to the LLM schema.
    """

    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

    @function_tool
    async def check_availability(
        self,
        specialty: Annotated[
            str,
            "The medical specialty to check, e.g. 'cardiology', 'dermatology', 'general practice'.",
        ],
        ctx: RunContext,
    ) -> str:
        """Check which appointment slots are currently available for a given medical specialty.

        Call this whenever the patient asks about availability, open times, or which doctors
        are free for a particular specialty.

        Args:
            specialty: The medical specialty the patient is asking about.
        """
        logger.info("[TOOL] check_availability → specialty=%r", specialty)
        await db.log_event(
            "INFO", "check_availability", f"Called → specialty={specialty!r}"
        )
        result = await db.check_availability(specialty)
        await db.log_event("INFO", "check_availability", f"Result: {result[:120]}")
        logger.info("[TOOL] check_availability ← %r", result)
        return result

    @function_tool
    async def book_appointment(
        self,
        patient_name: Annotated[
            str,
            "The patient's full legal name as spoken by the caller.",
        ],
        doctor_name: Annotated[
            str,
            "Full name of the doctor, e.g. 'Dr. Davis'. Must match a doctor returned by check_availability.",
        ],
        slot_time: Annotated[
            str,
            "Exact appointment time string matching the availability record, e.g. '02:00 PM'.",
        ],
        ctx: RunContext,
    ) -> str:
        """Book a confirmed appointment for a patient.

        Call this ONLY after explicitly obtaining and verbally confirming with the caller:
        their full name, the exact doctor name, and the exact time slot they want.
        This commits an atomic database transaction and returns a unique reference code.

        Args:
            patient_name: Full legal name of the patient.
            doctor_name: Full name of the doctor to book with.
            slot_time: The exact appointment time slot string.
        """
        logger.info(
            "[TOOL] book_appointment → patient=%r  doctor=%r  slot=%r",
            patient_name,
            doctor_name,
            slot_time,
        )
        await db.log_event(
            "INFO",
            "book_appointment",
            f"Called → patient={patient_name!r}  doctor={doctor_name!r}  slot={slot_time!r}",
        )
        result = await db.book_appointment(patient_name, doctor_name, slot_time)
        outcome_level = "SUCCESS" if result.startswith("You're all set") else "WARNING"
        await db.log_event(outcome_level, "book_appointment", result[:150])
        logger.info("[TOOL] book_appointment ← %r", result)
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

    # Connect to the LiveKit room — audio tracks only (no video for a phone agent)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Connected to LiveKit room.")

    # Build the Groq LLM via the OpenAI-compatibility shim
    groq_llm = openai.LLM(
        model="llama3-70b-8192",
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )

    # Assemble the voice pipeline session
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-2",
            language="en-US",
            punctuate=False,
            interim_results=True,
        ),
        llm=groq_llm,
        tts=openai.TTS(
            model="tts-1",
            voice="nova",      # Warm professional voice; swap to "alloy" if preferred
        ),
        vad=silero.VAD.load(),
    )

    # Start the agent — connects it to the room automatically
    await session.start(
        agent=ClaraAgent(),
        room=ctx.room,
    )

    logger.info("AgentSession started for room=%s", ctx.room.name)

    # Deliver the opening greeting immediately
    session.generate_reply(
        instructions=(
            "Greet the caller now with exactly this opening: "
            "'Thank you for calling Avery Wellness Clinic, this is Clara. "
            "How can I help you today?'"
        )
    )

    # Drain the DB pool when this room session ends
    ctx.add_shutdown_callback(db.close_pool)


# ---------------------------------------------------------------------------
# Worker entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="clara-scheduler",
        )
    )
