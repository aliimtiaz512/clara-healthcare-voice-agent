# Product Requirement Document (PRD)
## Project Name: Clara - Healthcare Voice AI Scheduling Agent
**Target Release Date:** June 20, 2026  
**Status:** Ready for Implementation

## 1. Purpose
### What the app does:
Clara is a locally deployed, real-time Voice AI agent built utilizing the LiveKit Agents SDK. It processes speech-to-text (STT) via Deepgram, runs orchestration and conversational loops through Groq (using LLaMA-3-70b), and provides human-like speech feedback using standard text-to-speech (TTS) engines. Clara allows patients to check real-time doctor availability and book healthcare appointments completely via natural voice interactions.

### Why it is built (Business Problem & Value):
Medical clinics lose up to 30% of booking opportunities during peak operating hours due to phone congestion, busy staff, and the absence of an automated after-hours response framework. This results in high patient frustration, dropped calls, and elevated no-show rates. Clara automates repetitive Level-1 scheduling inquiries, instantly responding to incoming patient calls, logging appointments to local PostgreSQL databases, and ensuring that human front-desk staff can focus on critical in-clinic operations.

## 2. Users and Roles
Since this is a locally deployed enterprise application with a real-time terminal sandbox/web view, users and roles are split into three interaction spheres:

| Role | Description | Access Permissions |
| :--- | :--- | :--- |
| **Patient (Caller)** | The external user calling into the system via voice. | **Voice Only:** Can speak to Clara, check doctor availability by specialty, provide booking details, and receive confirmation numbers. Has no access to the underlying files or interface. |
| **Clinic Administrator** | The internal user managing the appointment desk. | **Read-Only Data Access:** Can open and view the local database tables or the admin panel to track scheduled patient entries. |
| **AI Developer** | The engineer deploying and testing the architecture locally. | **Full Super-Admin Control:** Access to execute LiveKit local server routines, manage `.env` provider credentials, tweak system prompts, and modify custom Python backend tools. |

## 3. Data Model
The application leverages a robust, asynchronous PostgreSQL relational database layer (`clara_clinic`) to handle high-concurrency state modifications during call sessions.

### A. Doctors Table (`doctors`)
Tracks active medical providers and their specialties.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | SERIAL | PRIMARY KEY | Unique auto-incrementing ID |
| `name` | VARCHAR(100) | NOT NULL, UNIQUE | Full name of the doctor (e.g., "Dr. Davis") |
| `specialty` | VARCHAR(100) | NOT NULL | Focus area (e.g., "dermatology") |

### B. Availability Table (`availability`)
Holds specific scheduled timeslots for each physician.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | SERIAL | PRIMARY KEY | Unique auto-incrementing ID |
| `doctor_id` | INT | REFERENCES doctors(id) | Linked doctor |
| `slot_time` | VARCHAR(50) | NOT NULL | Alphanumeric slot time (e.g., "02:00 PM") |
| `is_booked` | BOOLEAN | DEFAULT FALSE | Status of reservation |

### C. Appointments Table (`appointments`)
Logs finalized customer bookings with distinct tracking tokens.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | SERIAL | PRIMARY KEY | Unique auto-incrementing ID |
| `appointment_code` | VARCHAR(20) | UNIQUE, NOT NULL | Alphanumeric tracking ID (e.g., "AV-9421") |
| `patient_name` | VARCHAR(150) | NOT NULL | Legal name of patient |
| `doctor_id` | INT | REFERENCES doctors(id) | Associated doctor |
| `slot_time` | VARCHAR(50) | NOT NULL | Reserved timeslot |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Record generation timestamp |

## 4. Business Rules
To protect patient safety and ensure strict business alignment, the Voice Agent enforces the following technical guardrails via system prompts and functional conditions:

1. **Medical Advice Prohibition (Critical Guardrail):** The AI agent is strictly a scheduling entity. If a user asks for diagnostic advice, symptom identification, or mentions an emergency (e.g., "My chest hurts"), the agent must immediately intercept the request with a mandatory warning: *"I cannot provide medical advice. If you are experiencing a life-threatening emergency, please hang up and call 911 immediately."*
2. **Concise Turn-Taking:** To optimize voice pacing and prevent overlapping audio, Clara must never output markdown bullet points, long lists, or blocks of text. All verbal responses must be restricted to 1–2 brief, human-sounding sentences.
3. **Out-of-Scope Redirection:** If the caller attempts to discuss non-clinic related topics, the agent must politely pivot back to the scheduling flow (e.g., *"I can help you with scheduling or availability, but I'm unable to discuss that. What kind of appointment are you looking to book today?"*).
4. **Slot Commit Locking:** A slot cannot be confirmed unless both a valid patient name and an available time slot matching an active specialist are supplied to the tool function.

## 5. Integrations
The local architecture connects seamlessly through standard Python-wrapped functional layers and external API pipelines:

### A. Core Communication Stack (External Pipelines)
* **LiveKit Agents SDK:** Manages the active real-time WebRTC media connection, room state orchestration, and user track monitoring.
* **Deepgram STT Plugin:** Live streaming speech-to-text integration converting caller voice frequencies into clean text strings.
* **Groq API Connection:** Processes user text inputs against the custom system prompt using high-throughput open-source LLM engines (LLaMA-3-70b).
* **LiveKit Native TTS Plugin:** Transforms the LLM's raw text response back into real-time voice streaming playback for the user.

### B. Internal Application Database APIs
These functions are declared locally in your Python script using `@agents.llm.ai_callable` descriptors, allowing the Groq LLM engine to execute automated tooling dynamically:
* `check_availability(specialty: str) -> str`: Reads the available slot list from PostgreSQL based on the patient's requested medical category.
* `book_appointment(patient_name: str, doctor_name: str, slot_time: str) -> str`: Atomically updates availability and inserts new tracking records.
