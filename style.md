# Interface Styling & UI Design System

## 1. Visual Theme & Corporate Identity
To fit a premium medical environment, the interface utilizes a clean, minimal "Nordic Medical Clinic" layout. It focuses on accessible typography, high contrast ratios, and generous whitespace to create a professional feel.

### Color Palette (Tailwind CSS Variables)
* **Primary Cyan (Brand Core):** `bg-cyan-600` / `#0891b2` (Conveys trust, modern healthcare, and cleanliness).
* **Deep Navy (Text & Contrast Headers):** `text-slate-900` / `#0f172a` (Provides premium contrast and deep visual structure).
* **Muted Slate (Borders & Inactive Subtitles):** `border-slate-200` / `#e2e8f0`
* **Clean Emerald (Success Identifiers):** `text-emerald-600` / `#059669` (Indicates a successfully saved appointment).

## 2. Component Design Specifications
### A. Live Voice Stream Monitor Card
* **State Indicator Aura:** A centered circular badge representing Clara's current state.
  * *Listening State:* An emerald pulsing ring layout (`animate-pulse`).
  * *Processing/Thinking State:* A smooth rotating cyan spinner layout (`animate-spin`).
* **Waveform Visualizer:** Implement an active audio track bar meter built on the WebRTC stream to visually display inbound voice levels during testing.

### B. Real-Time Admin Dashboard Layout
* **Grid Split:** A dual-column responsive setup (`grid grid-cols-1 lg:grid-cols-3 gap-6`).
  * *Left Component (Col-1):* Live audio session controls, connectivity statuses, and real-time terminal tool logs.
  * *Right Component (Col-2/3):* A live table display of the database state. This displays incoming appointments records as soon as Clara triggers the transaction commit tool.

## 3. Typography Hierarchy
* **Primary System Interface Font:** Inter or standard sans-serif (`font-sans`).
* **Main Screen Header:** `text-3xl font-bold tracking-tight text-slate-900`
* **Table Column Metadata Labels:** `text-xs font-semibold text-slate-500 uppercase tracking-wider`
* **Real-time Log Typography:** `font-mono text-sm bg-slate-950 text-cyan-400 p-4 rounded-lg` (Ensures maximum code readability when demonstrating backend tool triggers).
