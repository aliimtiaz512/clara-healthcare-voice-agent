# **Claude Project Context & Engineering Rules (claude.md)**

## **1\. Project Specification (One-Liner)**

Clara is a real-time, low-latency Voice AI scheduling assistant for a healthcare clinic, built using LiveKit Agents, Deepgram STT, and Groq (LLaMA-3-70b), which dynamically commits atomic appointment rows to a local PostgreSQL cluster.

## **2\. Codebase Rules for Building**

### **A. Architectural & Execution Rules**

* **Strict Async Paradigm:** All database queries, transactions, and pool allocations must be handled using asynchronous design bindings (asyncpg). Never use synchronous execution blocks or blocking handlers (time.sleep) inside voice thread contexts.  
* **Concurrency Protection:** When modifying or reserving availability windows, enforce row-level locking via explicit FOR UPDATE clauses to prevent race conditions or double-booking from simultaneous calling tracks.  
* **Isolate Logic:** Keep the backend data engine isolated (server/db.py) from the LiveKit orchestration network (server/agent.py).

### **B. LLM Behavior & Pacing Constraints**

* **Verbal Conciseness:** The agent must communicate using short, conversational fragments (1–2 sentences max). Never generate long sentences, paragraphs, or bullet points.  
* **Strict Medical Guardrail:** The agent is an administrative scheduler, NOT a clinical advisor. If a caller mentions diagnostic queries or an active emergency, intercept the flow instantly with the exact phrase: *"I cannot provide medical advice. If you are experiencing a life-threatening emergency, please hang up and call 911 immediately."*  
* **Structured Tool Calls:** The agent must gracefully utilize standard tool definitions (check\_availability and book\_appointment) based on clear caller indicators. Do not assume user confirmation without triggering the write tool.

### **C. Technical Dependencies Stack**

* **Language/Platform:** Python 3.10+ (using asyncio)  
* **Media Stream Layer:** LiveKit Agents SDK & WebRTC Core Engine  
* **Cognitive APIs:** Deepgram (STT plugin) and Groq (OpenAI-compatible client framework targeting llama3-70b-8192)  
* **Relational Layer:** PostgreSQL (via asyncpg connection pools)

## **3\. Core System References**

Refer to these specialized specification documents located in the repository root for detailed system constraints:

1. **Product Requirements (prd.md):** Explains target user roles, business logic constraints, and table field boundaries.  
2. **System Architecture (arch.md):** Visualizes the full-duplex WebRTC streaming loops, data flows, and concurrency pipeline.  
3. **UI/UX Styling System (style.md):** Details the frontend design rules, color palettes (Nordic Cyan/Slate), and real-time streaming dashboards.