# M3 — Academic Calendar, Exams, Server & Confirm Flow (MVP)

**Features:** F3 Academic calendar (semester dates, holidays) · F4 Exam schedules & exam rules
**Why together:** both are date-driven and both answer "what phase of the term are we in?".
**Read first:** `00_SHARED_CONTRACTS.md`. **You also run the server**, so you unblock everyone's browser testing.

## Foundation you own (W1)
- `core/db.py` — one Mongo client, connect/close, `ensure_indexes`.
- `api/main.py` — app startup (connect DB, build the LLM client, tool registry and retriever once, start M1's seat watcher once it exists), mounts all routers, CORS from settings, `GET /api/health`.
- `api/routes/chat.py` — `POST /chat/stream` (Server-Sent Events), `POST /actions/{id}/confirm|cancel`. **Skeleton by Wed 28 Oct**, wired to M4's agent loop by Fri 30 Oct.

## Your 5 files

| # | File | Layer | What it holds |
|---|---|---|---|
| 1 | `data/calendar_repo.py` | data | `list_events(term, types)`, `get_exam_schedule(student sections)`, `get_exam_rules(term)`. |
| 2 | `domain/calendar_engine.py` | domain, pure | `resolve_phase`, `current_term`, `registration_term`, `is_registration_open`, `detect_exam_conflicts`, `format_exam_rules`. |
| 3 | `services/calendar_service.py` | service | Calls the engine, exposes 3 tools, builds `TermInfo` for M1. |
| 4 | `services/action_service.py` | service | Confirm-before-write store (moved to you from M4). |
| 5 | `api/routes/chat.py` + `api/main.py` | API | See foundation above. |

## The rules (file 2)

- **Two kinds of "current term".** Today (Oct 2026) is inside Fall 2026, but registration is for Spring 2027. `current_term(today)` = the term whose semester window contains today. `registration_term(today)` = the term whose registration window is open, else the next upcoming one. Calendar questions default to `current_term`; registration questions (M1) use `registration_term`.
- **`is_registration_open(term, today)`** — exact boundaries, **no grace days**. The day after the close date is closed. M1 uses this and nothing else.
- **`detect_exam_conflicts`** — two exams on the same date with overlapping times → HARD; same student with 3+ exams in one day → SOFT warning.
- **Exam rules live here and only here:** allowed and forbidden items, calculator and open-book policy, late-arrival rule, scheduling limits. **ID requirements are not here** — they belong to M5's proctoring policy. If a student asks "what can I bring?", answer from `get_exam_rules_summary`.
- **`format_exam_rules`** returns one text block with every fact the bot may state.

## Your 3 tools (file 3)

| Tool | Returns |
|---|---|
| `get_academic_calendar(term?, event_type?)` (public) | events sorted by date, current phase, next deadline: `{term, phase, events: [...], summary}` |
| `get_my_exam_schedule()` | the student's exams with date, time, room and `proctoring_type`, plus conflicts: `{exams: [...], conflicts: [...], summary}` |
| `get_exam_rules_summary()` (public) | the exam-day rules from `exam_rules.csv` |

Each exam row carries `proctoring_type` — M5's `get_proctoring_info` joins on it.

## Confirm-before-write (file 4 — moved to you from M4)

The LLM must never perform a write. `services/action_service.py`:
- `PendingAction(action_id, user_id, kind, payload, summary, status, created_at, expires_at)`; `kind = TRANSCRIPT` in the MVP; expires after 120 s (`confirm_ttl_s`).
- `PendingActionStore`: `propose(user, kind, payload, summary)`; `confirm(user, action_id)` checks ownership, expiry and single use, then calls M4's `records_service.request_transcript`, which **re-runs eligibility before writing**; `cancel(...)`.
- Endpoints (in your chat route): `POST /actions/{id}/confirm`, `POST /actions/{id}/cancel`. Second confirm → 409; someone else's action → 404; expired → 410.
- M4's `propose_transcript_request` tool calls `propose`; the chat stream turns that into a `confirm` event; M5's `ConfirmCard` shows Confirm / Cancel.

## Eval runner and seed check (moved to you from M2)

- `scripts/run_eval.py` — runs the 30 golden questions through the real chat endpoint, checks that every `expected_facts` string appears and that `must_cite` questions carry a citation, prints pass/fail per feature. Runs in CI.
- `scripts/check_seed.py` — about 40 lines. Fails if a `section_code` in `exam_schedules` or `enrollments` is missing from `sections`, or a course code in prerequisites / requirement groups / substitution rules is missing from `courses`.

## Seed data and docs (W1)
`calendar_events.csv` (~20 events across Fall 2026 and Spring 2027: semester start/end, registration open/close, add-drop deadline, holidays, exam period), `exam_schedules.csv` (~45 — one per section, a couple deliberately clashing), `exam_rules.csv`, `academic_calendar.md` and `exam_rules.md` (process prose — **no literal dates**). With `today_override` set to the demo date, `current_term` must be Fall 2026 and `registration_term` Spring 2027.

## Tests (must pass)
- `registration_term` on three dates (before Spring registration opens, during, after it closes)
- `is_registration_open` on the open date, the close date and the day after
- `resolve_phase` for each boundary date
- exam conflict: same date overlapping → HARD; back-to-back → no conflict
- action store: propose writes nothing to `transcript_requests`; confirm creates exactly one; second confirm → 409; another user's action → 404; expired → 410
- `run_eval.py` fails (non-zero exit) when a golden question's expected fact is missing
- `/api/health` returns the documented shape

## Week by week

| Week | Deliverable | Gate |
|---|---|---|
| W1 (26 Oct) | `db.py`, `main.py`, chat route skeleton, CSVs, 2 docs | Server starts; B+ question reaches M4's agent loop by Sun 1 Nov |
| W2 | Files 1 + 2 with tests; `registration_term` + `is_registration_open` to M1 by Fri 6 Nov | Phase logic correct on all boundary dates |
| W3 | File 3 (tools), exam conflicts, action store + confirm/cancel endpoints | 3 tools answer 3 golden questions each; confirm flow works end to end |
| W4 | `run_eval.py` + `check_seed.py` | Eval and seed check run in CI |
| W5 | Bug fixes | Frozen Sat 28 Nov |

## Cut order if behind
`format_exam_rules` polish → SOFT 3-exams warning → `check_seed.py` extras. **Never cut:** boundary-exact dates, `registration_term`, server health.

## Workload note
This slice is lighter than in the first plan: M1 now owns the real-time path. If you finish early, review M4's agent loop in W3 and help wire tools. Don't start new features.
