# Clara — Healthcare Voice AI Scheduling Agent

> A locally-deployed, real-time **LiveKit voice agent** for **Avery Wellness Clinic**.
> Patients call in and talk to **Clara**, who checks doctor availability, books and
> cancels appointments, and confirms insurance — entirely by voice.

Built for the *AI Systems & Voice Agents* capstone (Topic 06 — Healthcare Appointment Scheduling).

---

## The business problem

Medical clinics lose a large share of booking opportunities during peak hours: phones
ring busy, front-desk staff are overloaded, and there is no after-hours intake. The
result is dropped calls, frustrated patients, and elevated no-show rates.

**Clara** answers every call instantly — day or night — and handles routine Level-1
scheduling so human staff can focus on in-clinic care. She checks live availability,
commits real bookings to a database, confirms insurance, and cancels appointments,
all through a natural voice conversation. Every action is mirrored live on an admin
dashboard so the front desk can watch bookings land in real time.

---

## What's in the box

| Layer | Tech |
|-------|------|
| Transport | **LiveKit** WebRTC + built-in dev server |
| Agent runtime | **LiveKit Agents SDK 1.6** (`Agent` / `AgentSession`) |
| Speech-to-Text | **Deepgram** Nova-2 |
| LLM | **Groq** `llama-3.3-70b-versatile` (OpenAI-compatible) |
| Text-to-Speech | **Deepgram** Aura (`aura-asteria-en`) |
| Turn-taking | **Silero** VAD |
| Database | **PostgreSQL** via `asyncpg` (pooled, row-locked) |
| Admin API | **FastAPI** + Server-Sent Events |
| Dashboard | **Next.js 14** + Tailwind + LiveKit React components |

> The whole pipeline runs on two keys only — **Deepgram** (STT + TTS) and **Groq** (LLM).
> No OpenAI key is required.

---

## Clara's four tools

Clara invokes real function calls during the conversation (the brief requires ≥2):

1. **`check_availability(specialty)`** — reads open slots for a specialty from PostgreSQL.
2. **`book_appointment(patient_name, doctor_name, slot_time)`** — atomically reserves a
   slot inside a `SELECT … FOR UPDATE` transaction (no double-booking) and returns a
   unique `AV-XXXX` reference code.
3. **`lookup_insurance(provider)`** — checks whether the clinic is in-network with a
   given carrier (Aetna, Blue Cross, Cigna, UnitedHealthcare, Medicare, Humana …).
4. **`cancel_appointment(appointment_code)`** — cancels a booking by reference code and
   frees the slot back up.

The **system prompt** that defines Clara's identity, personality, voice style, and
guardrails lives at the top of [`server/agent.py`](server/agent.py) (`SYSTEM_PROMPT`),
with the engaging opening line in `GREETING`.

---

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **PostgreSQL 13+** running locally
- A **Deepgram** API key — <https://console.deepgram.com/>
- A **Groq** API key — <https://console.groq.com/keys>

---

## Setup

### 1. Clone & configure environment

```bash
# Server
cd server
cp .env.example .env        # then edit .env and add your DEEPGRAM_API_KEY + GROQ_API_KEY
                            # and your Postgres password

# Client
cd ../client
cp .env.example .env
```

### 2. Create the database

```bash
createdb clara_clinic                              # or: CREATE DATABASE clara_clinic;
psql -U postgres -d clara_clinic -f server/schema.sql
```

This creates the `doctors`, `availability`, `appointments`, and `agent_logs` tables
and seeds 5 doctors × 5 timeslots.

### 3. Install dependencies

```bash
# Python (from repo root, using a virtualenv)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r server/requirements.txt

# Node
cd client && npm install && cd ..
```

---

## Running

### Option A — one command (Linux/macOS)

```bash
./start.sh
```

This downloads the LiveKit binary if needed, then starts the LiveKit server, the
FastAPI API, the Next.js dashboard, and the Clara agent (in the foreground).
`Ctrl+C` stops everything.

### Option B — Windows

```powershell
powershell -File start.ps1      # starts LiveKit + API + dashboard
# then, in a new terminal:
cd server
..\.venv\Scripts\python.exe agent.py dev
```

### Option C — manual (4 terminals)

```bash
# 1. LiveKit dev server (built-in, no signup)
./livekit-server/livekit-server --dev --bind 0.0.0.0     # Windows: livekit-server.exe

# 2. Admin API
cd server && uvicorn api:app --reload --port 8000

# 3. Voice agent  (the LiveKit CLI entrypoint)
cd server && python agent.py dev

# 4. Dashboard
cd client && npm run dev
```

Open **http://localhost:3000**, click **Start Test Call**, allow your microphone, and
talk to Clara. Bookings and tool calls appear live in the dashboard.

---

## Try saying…

- *"What cardiology appointments do you have?"* → triggers `check_availability`
- *"Do you take Aetna?"* → triggers `lookup_insurance`
- *"Book me with Dr. Davis at 2:30, my name is John Carter."* → triggers `book_appointment`
- *"I need to cancel, my code is A-V-six-one-zero-eight."* → triggers `cancel_appointment`
- *"My chest hurts"* → fires the medical-advice guardrail (no diagnosis, points to 911)

---

## Project structure

```
clara-healthcare-voice-agent/
├── server/
│   ├── agent.py          # LiveKit agent: system prompt, greeting, 4 tools, pipeline
│   ├── db.py             # asyncpg pool + tool implementations (availability, booking…)
│   ├── api.py            # FastAPI admin API + SSE stream + LiveKit token endpoint
│   ├── schema.sql        # tables + seed data
│   ├── requirements.txt
│   └── .env.example
├── client/               # Next.js admin dashboard (live monitor, terminal, table)
├── livekit-server/       # LiveKit binaries (.exe committed; Linux fetched on demand)
├── scripts/get-livekit.sh
├── start.sh / start.ps1
├── prd.md · arch.md · style.md · claude.md   # design docs
└── README.md
```

---

## Safety & design notes

- **Medical guardrail (highest priority):** Clara is a *scheduler*, not a clinician.
  Any symptom/diagnosis/emergency triggers a fixed safety script pointing to 911.
- **No double-booking:** every booking takes a row-level `FOR UPDATE` lock before
  flipping `is_booked`, so concurrent callers can't grab the same slot.
- **Concise by design:** the prompt forces 1–2 spoken sentences, no markdown/lists —
  tuned for natural phone pacing.
- **No secrets in git:** real keys live in `.env` (git-ignored); `.env.example` ships
  with placeholders.
