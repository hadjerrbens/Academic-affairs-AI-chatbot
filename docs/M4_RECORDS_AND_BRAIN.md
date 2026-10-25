# M4 — Grading, Transcripts & the Chatbot Brain (MVP)

**Features:** F5 Grading system explanation · F6 Transcript requests
**Why together:** both are about the student's grade record. F5 explains the scale; F6 issues an official copy of the result.
**Read first:** `00_SHARED_CONTRACTS.md`. **You also build the agent loop** — the part that turns a question into an answer.

## Foundation you own (W1–W2)
- `core/llm.py` — Groq client: `complete`, `complete_json` (router, no tools), `stream`. Fast model for routing, bigger model for answers. Retry on 429 with backoff, a daily token budget tracker. **By Wed 28 Oct.**
- `core/tools.py` — `ToolContext(user, today, registration_term, current_term)`, `@register_tool`, `ToolRegistry.specs_for(areas, authenticated)` (**max 6 tools per request**), `execute(name, args, ctx)` (validates args, never raises, truncates huge results).
- `services/chat_service.py` — the agent loop (below). **v0 with the grading tool by Fri 30 Oct.**
- *(The confirm-before-write store is now M3's `services/action_service.py`. You call its `propose(...)` from `propose_transcript_request`.)*

## Your feature slice (3 files)

| # | File | What it holds |
|---|---|---|
| 1 | `data/records_repo.py` | `get_grade_scale()`, `get_grade_points_map() -> dict[str,float]` + `passing_points` (**M2 needs this by Fri 6 Nov**), `create_transcript_request`, `list_transcript_requests`. |
| 2 | `domain/records_engine.py` | pure: `band_for_percentage`, `explain_band`, `normalise_letter`, `check_transcript_eligibility`, `transcript_fee`. |
| 3 | `services/records_service.py` | the 3 tools below. |

**Grading scale (`grading_scale.csv`, 11 bands):** A 93–100 (4.0), A- 90–92.9 (3.7), B+ 87–89.9 (3.3), B 83–86.9 (3.0), B- 80–82.9 (2.7), C+ 77–79.9 (2.3), C 73–76.9 (2.0), C- 70–72.9 (1.7), D+ 67–69.9 (1.3), D 60–66.9 (1.0), F 0–59.9 (0.0). Pass at 1.0. **A boundary value belongs to the higher band** (exactly 90.0 → A-). `explain_band` for A- must say 90.0–92.9, matching the table.

**GPA:** do **not** write one. M2's `calculate_gpa` is the only GPA function; if you need a GPA, call it.

**Transcript eligibility** (pure): checks that the student's standing is not in `blocks_transcripts` (from M2's policy — don't hard-code probation), no unpaid hold flag, and that a request isn't a duplicate within the same day. Fees and delivery times are a small table **in code** — one source; the doc never quotes a fee.

## Your 3 tools

| Tool | Returns |
|---|---|
| `explain_grading_system(grade?)` (public) | the scale, or one band explained: `{bands: [...], summary}` |
| `check_transcript_eligibility()` | `{eligible, blocking_reasons, options: [{kind, delivery, fee, estimated_days}], summary}` |
| `propose_transcript_request(kind, delivery)` | **never writes.** Validates, checks eligibility, returns `{requires_confirmation: true, action_id, summary, fee, estimated_days}`. |

## The agent loop (`chat_service.py`)

1. **Clean the input** (strip control characters, cap length, flag obvious injection phrases).
2. **Rate limit and token-budget check.** Over budget → step 9.
3. **Route** with `complete_json` (no tools): `{primary: label, secondary: label|null}` from the 10 labels + `smalltalk` + `out_of_scope`. If it fails, use M5's keyword router.
4. `out_of_scope` → polite refusal that lists what the bot can do. `smalltalk` → short reply, no tools.
5. **Pick tools** for `primary` + `secondary` only (≤ 6). Sending all 14 every time would burn the token budget.
6. **Retrieve policy text** from M5's `retrieve_with_context(query, feature_area)` for areas that have a doc.
7. **Tool loop** — call the model with tools; run requested tools; feed results back; repeat up to 4 times.
8. **Answer** (temperature 0.1) only from tool results and context, with `[source N]` markers; drop any marker with no matching source.
9. **Degraded mode** (budget gone, LLM down): run the routed tool directly and return its `summary` string with a note "AI explanation temporarily unavailable". The numbers still work.
10. Save the turn; record token use.

Events streamed to the browser: `meta`, `delta`, `tool` (name + ok only), `citations`, `confirm`, `done`, `error`.

## Confirm-before-write
The store (`PendingActionStore`) and the `/actions/{id}/confirm|cancel` endpoints belong to **M3**. Your part: `propose_transcript_request` validates the input, runs eligibility, and calls `propose(...)`; the real `request_transcript` is a *service* method only, called by M3's confirm endpoint, and it **re-runs eligibility** before writing. Agree the `propose` signature with M3 by Fri 6 Nov.

## Seed data and docs (W1)
`grading_scale.csv`, `grading_system.md`, `transcript_requests.md` (process prose, **no fees or dates**).

## Tests (must pass)
- `band_for_percentage` at every boundary (89.9, 90.0, 92.9, 93.0, 59.9, 60.0, 100)
- `explain_band("A-")` matches the table
- letter normalisation: `a-`, `A -`, `A-` → same key
- eligibility blocks a standing listed in `blocks_transcripts`
- `propose_transcript_request` creates **nothing** in `transcript_requests` (it only calls M3's `propose`); `request_transcript` re-checks eligibility
- registry: unknown tool → error dict; bad args → error dict; no tool schema has `student_id`; `specs_for` never returns more than 6
- agent loop: an out-of-scope question makes **zero** tool calls; LLM 429 → degraded answer with the real numbers; unauthenticated "what's my GPA" → login prompt, no tool call

## Week by week

| Week | Deliverable | Gate |
|---|---|---|
| W1 (26 Oct) | `llm.py` (Wed), `tools.py` registry, agent loop v0 with `explain_grading_system`, `grading_scale.csv` | **B+ question works end to end (Sun 1 Nov)** |
| W2 | Router + tool selection, File 1 + 2 with tests; `get_grade_points_map` to M2 by Fri 6 Nov | Public questions answer without login |
| W3 | All 14 tools wired, degraded mode, `propose_transcript_request` (using M3's store) | Every feature answers one real question |
| W4 | Tune routing and prompts on the golden set | Routing ≥ 90%; average tokens per turn ≤ 3 500 |
| W5 | Kill-Groq drill, bug fixes | Frozen Sat 28 Nov |

## Cut order if behind
`secondary` route (single area only) → Confirm flow (transcript becomes "here's how to request it") → tool-result cards. **Never cut:** grounding, citations, degraded mode, no-write-from-LLM.

## Workload note
Your agent loop is the project's single point of failure. Build the thin slice first, keep it small, and let others plug tools into it. You no longer own the confirm store or the WebSocket, so the loop is your focus. M3 reviews it in W3.
