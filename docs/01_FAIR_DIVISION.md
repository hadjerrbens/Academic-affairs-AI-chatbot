# Fair Division of Work (MVP)

**How this was done:** every work package got a rough effort estimate in **days for one student** (code + tests + seed data). The packages were then moved until each person has about the same total **and** exactly one "hard" item. These are estimates, not measurements — treat ±1 day as noise.

## 1. Effort per person (days)

| Work package | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|
| Foundation: config + shared models | 2 | | | | |
| Foundation: security + login routes | | 3 | | | |
| Foundation: db + `main.py` + chat route (SSE) | | | 3 | | |
| Foundation: Groq client | | | | 2 | |
| Foundation: tool registry | | | | 2 | |
| **Agent loop** (routing, tool loop, degraded mode) | | | | **7** | |
| **Search layer (RAG)** + retrieval test | | | | | **6** |
| Prompts + keyword router | | | | | 2 |
| **Real-time path** (EventBus, WebSocket, watcher, `useRealtime`) | **4** | | | | |
| Chat screen (shell, streaming, login form, chips) | | 6 | | | |
| Chat components (citations, cards, confirm card) | | | | | 2 |
| Confirm-before-write store + endpoints | | | 2 | | |
| Eval runner + seed check | | | 3 | | |
| Feature slice (rules + tools + routes) | 9 | 7 | 6 | 5 | 4 |
| Seed CSVs + policy docs | 2 | 4 | 3 | 1 | 3 |
| Golden questions (6 each) | 1 | 1 | 1 | 1 | 1 |
| **Total** | **18** | **21** | **18** | **18** | **18** |

M2 reads slightly high because the chat screen includes the login form and the 10 transcripts for the seed data are fiddly. If M2 is behind at the W2 gate, move the starter chips and the degraded banner to M5.

## 2. Each person's single hard item

| Member | Hard item | Why it's hard | Fallback if it slips |
|---|---|---|---|
| M1 | Seat transaction + real-time path | Race conditions, async fan-out | Static seat count, polling every 30 s |
| M2 | Standing / GPA engine **and** a streaming UI | Many edge cases; SSE parsing | Plain (non-streamed) answers |
| M3 | Calendar phases + confirm flow | Exact boundary dates, single-use actions | Transcript becomes "how to request it" text |
| M4 | The agent loop | Everyone depends on it | Keyword router + one tool per question |
| M5 | RAG search | Embeddings and chunking get fiddly | Keyword-only search with a `feature_area` filter |

## 3. What changed from the first split (and why)

| Moved | From → To | Reason |
|---|---|---|
| Real-time (EventBus, WebSocket, watcher) | M3 → M1 | M1 already owns the seat data and the counter, so one person owns the path from database to screen. M1 is lighter after W2. |
| Chat screen | M5 → M2 | M2 already builds the login gate. M5 keeps the parts that show its own work (citations, cards). |
| Confirm-before-write store | M4 → M3 | Lets M4 focus on the agent loop. M3 already owns the chat route. |
| Eval runner + seed check | M2 → M3 | M3's workload dropped after the real-time move. |
| `enrollments.csv` | M1 → M5 | Cross-cutting data that needs M1's sections and M2's students. A neutral owner avoids waiting on either. |

## 4. Fair-play rules

- **Rotating chores (weekly):** the Friday full-chat check and the bug-triage list rotate in order M1 → M2 → M3 → M4 → M5.
- **Demo:** each person presents their own slice for about 2 minutes. M2 opens (the screen), M4 shows the agent flow, M1 closes (the live seats).
- **Credit:** one repo, one branch per person per week. Contribution is judged on files each person owns, so commit under your own name and keep PRs small.
- **Swap rule:** if you're behind at a gate and tell the team **that day**, the team moves one package to the person with the most slack. Nobody is blamed for an estimate that was wrong.
- **No heroics:** if someone finishes early, they review a teammate's PR before starting anything new.

## 5. Critical path by week (who waits on whom)

| Week | Blocking item | Owner | Waiting |
|---|---|---|---|
| W1 | `shared_models`, `config` (Tue) | M1 | everyone |
| W1 | `db.py`, `main.py` (Wed), `llm.py` (Wed) | M3, M4 | everyone |
| W2 | `get_grade_points_map` (Fri 6 Nov) | M4 | M2 |
| W2 | `registration_term`, `is_registration_open` (Fri 6 Nov) | M3 | M1 |
| W3 | chat components (Fri 13 Nov) | M5 | M2 |

Moving the real-time work to M1 does **not** add a new blocker: it lands in W3–W4, after M1's W1–W2 critical-path work is done.
