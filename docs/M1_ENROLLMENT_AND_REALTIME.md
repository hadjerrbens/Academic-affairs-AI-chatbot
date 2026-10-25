# M1 — Registration Help, Schedule Conflicts & Real-Time (MVP)

**Features:** F1 Course registration help · F8 Calendar conflicts
**Why together:** both ask "does this course fit into this student's term?" and use the same section/meeting-time data.
**Read first:** `00_SHARED_CONTRACTS.md`. **You are the critical path:** M2 and M3 read your data.

## Foundation you own (W1)
- `core/config.py` — settings from `.env` (fail fast if a required key is missing), plus `get_today()` with `today_override`.
- `domain/shared_models.py` — the shared models and helpers in contracts §3. **Due Tue 27 Oct.**
- **Real-time (moved to you from M3, so you own the whole path from database to screen; build it W3–W4):**
  - `core/events.py` — `EventBus`: in-process async fan-out, `publish(topic, event)`, `subscribe(topic)`. Each subscriber has a queue of 100; when full, **drop the oldest** so a slow browser never stalls the server. `SeatUpdate(section_code, seats_left, status)`.
  - Seat watcher — consumes your `watch_section_updates()` and publishes `SeatUpdate`, **at most one event per section per second**. M3's `main.py` starts it.
  - `api/ws.py` — `GET /ws`, public topic `seats` (no login). Client sends `{"type":"subscribe","topic":"seats","sections":["CS101-A"]}`; server pushes `{"type":"seat_update","section_code","seats_left","status"}`. Heartbeat ping/pong; origin must be in `cors_origins`; max 5 sockets per IP; max 50 sections per subscription.
  - `frontend/core/useRealtime.ts` — one shared WebSocket for the whole app: reconnect with backoff, 30 s polling fallback, exposes `connectionState`. M2's screen and your `RegistrationCard` both read from it.
  - Chat stays on HTTP streaming, not the WebSocket. The socket is for push updates only.

## Your 5 files

| # | File | Layer | What it holds |
|---|---|---|---|
| 1 | `data/enrollment_repo.py` | data | Mongo queries: `get_course`, `get_sections(course_code, term)`, `get_student_sections(student_id, term)`, `enroll(...)`, `drop(...)`. The seat count and the enrollment record change **in one transaction**. `watch_section_updates()` yields seat changes (5 s polling; Change Streams only if your Atlas tier supports them — check in W1). |
| 2 | `domain/registration_rules.py` | domain, pure | `check_prerequisites`, `detect_conflicts`, `evaluate_registration` (below). No I/O, no clock. |
| 3 | `services/enrollment_service.py` | service | Loads data, calls the rules, exposes the 2 tools. Gets `is_registration_open` from M3 and the standing from M2. |
| 4 | `api/routes/enrollment.py` | API | `GET /enrollment/sections?course=CS101`, `POST /enrollment/register`, `POST /enrollment/drop` (login required). The chatbot **never** registers; the button does. |
| 5 | `frontend/features/registration/RegistrationCard.tsx` | UI | Section list with a live seat counter, eligibility badge with the reason, Register / Drop buttons. |

## The rules (file 2)

`evaluate_registration` returns the **first** problem found, in this order:
`ALREADY_ENROLLED → REGISTRATION_CLOSED → SECTION_FULL → PREREQ_MISSING → CONFLICT → STANDING_BLOCKED`
Otherwise `ELIGIBLE`. Each result carries a `reason` sentence and the data behind it (full section: seats and waitlist; conflict: both courses and the overlapping time).

- **`check_prerequisites`:** a prerequisite is met only if it's in `completed` with a passing grade. Return the *missing* codes.
- **`detect_conflicts`:** two meeting slots overlap if they share a day and the time ranges intersect. **10:00–10:50 and 10:50–11:40 do not overlap.** A gap under 15 minutes is a SOFT conflict (tight), an overlap is HARD.
- **Registration open?** Not your function. Call M3's `is_registration_open`. **No grace days.**
- **Standing blocked?** The service asks M2's `get_standing_status` and checks it against `blocks_registration` in the standing policy. Don't hard-code "probation blocks".

## Your 2 tools (file 3)

| Tool | Returns |
|---|---|
| `check_registration_eligibility(course_code, section_code?)` | `{verdict, reason, sections: [{code, instructor, schedule, seats_left}], summary}`. `term` defaults to `registration_term`, **not** `current_term`. |
| `detect_schedule_conflicts()` | Class-vs-class conflicts **and** exam-vs-exam clashes for the student's registered term: `{conflicts: [{kind: CLASS_OVERLAP\|EXAM_CLASH, severity, course_a, course_b, detail}], summary}`. Exam clashes come from M3's `detect_exam_conflicts` (pure). |

## Seed data and docs (W1)
`courses.csv` (~30, prerequisites filled in), `sections.csv` (~45, some deliberately full or overlapping so the demo has interesting cases), `course_registration.md` (one page of *process* prose: how registration works, waitlists, what "prerequisite" means — **no dates**).

## Tests (must pass)
- prereq met / missing / failed (F doesn't count)
- overlap vs back-to-back (10:50 boundary) vs SOFT gap
- each verdict in the priority order, including "full **and** prereq missing → SECTION_FULL"
- register twice → one enrollment, error on second
- seat count never exceeds capacity when two registrations race (transaction)
- tool schema has no `student_id`
- EventBus: slow subscriber drops oldest and the publisher never blocks; 10 events in 1 s → 1 delivered
- WebSocket: wrong origin rejected; subscribe → update arrives; reconnect re-subscribes

## Week by week

| Week | Deliverable | Gate |
|---|---|---|
| W1 (26 Oct) | `config.py`, `shared_models.py` (by Tue), `courses.csv`, `sections.csv` (to M5 by Fri 30 Oct), `course_registration.md` | Seed loads; everyone imports your models |
| W2 | Files 1 + 2 with tests | `evaluate_registration` correct on 5 hand-checked cases |
| W3 | File 3 (both tools), File 4, `EventBus` + `/ws` skeleton | Both tools answer 3 golden questions each; ws ping/pong works |
| W4 | File 5, seat watcher, `useRealtime`, live seat counter | Two browsers: register in one, other updates in ~2 s |
| W5 | Bug fixes | Frozen Sat 28 Nov |

## Cut order if behind
SOFT conflicts → seat-counter polish → live counter (keep static count). **Never cut:** the priority order and the transaction.

## You owe the team
By Fri 30 Oct: `sections.csv` to M5 (for `enrollments.csv`). By Fri 6 Nov: `get_student_sections(student_id, term)` for M3, and the `useRealtime` hook with the seats contract for M2 and M5. You need from others: `is_registration_open`/`registration_term` (M3) and `get_student_record`/`get_standing_status` (M2).
