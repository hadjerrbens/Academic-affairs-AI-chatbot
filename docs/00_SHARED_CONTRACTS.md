# MVP — Shared Contracts (everyone reads this first)

Rules that make five separate slices fit together. If a member doc disagrees with this file, **this file wins**.

**Core rule:** code decides facts (dates, GPA, eligibility, conflicts, fees). The model only explains them and cites sources.

## 1. The 10 features, their labels and their tools (14 tools total)

| Label (`feature_area`) | Owner | Tool | Login? |
|---|---|---|---|
| `course_registration` | M1 | `check_registration_eligibility(course_code, section_code?)` | yes |
| `calendar_conflicts` | M1 | `detect_schedule_conflicts()` | yes |
| `degree_requirements` | M2 | `get_major_requirements(program_code)` | no |
| `degree_requirements` | M2 | `audit_degree_progress()` | yes |
| `academic_standing` | M2 | `get_academic_standing()` | yes |
| `academic_calendar` | M3 | `get_academic_calendar(term?, event_type?)` | no |
| `exam_schedules` | M3 | `get_my_exam_schedule()` | yes |
| `exam_schedules` | M3 | `get_exam_rules_summary()` | no |
| `grading` | M4 | `explain_grading_system(grade?)` | no |
| `transcripts` | M4 | `check_transcript_eligibility()` | yes |
| `transcripts` | M4 | `propose_transcript_request(kind, delivery)` | yes (confirm-gated) |
| `course_substitution` | M5 | `explain_waiver_process()` | no |
| `course_substitution` | M5 | `check_waiver_eligibility(target_course, substitute_course)` | yes |
| `proctoring` | M5 | `get_proctoring_info(exam_type?, course_code?)` | no |

Router-only labels: `smalltalk`, `out_of_scope`.

## 2. Tool rules (every tool, no exceptions)

- Signature: `async def tool(ctx: ToolContext, args: ArgsModel) -> dict`, registered with `@register_tool(feature_area="...", requires_auth=True/False)`.
- **No tool takes `student_id` or `user_id`.** The logged-in user is `ctx.user`. A test scans every tool schema for these names.
- Returns JSON-serialisable data **plus a `"summary"` string** that already contains every number and date the answer needs. The model must not compute anything.
- Never raises: on failure return `{"error": "<CODE>", "message": "<one human sentence>"}`.
- No tool calls the LLM, the internet, or **writes to the database**. The only write path is `propose_transcript_request` → confirm button.
- Max 2 tools per feature area in the MVP.

## 3. Shared models (`domain/shared_models.py`, M1 writes it by Tue 27 Oct)

`MeetingSlot(day, start, end, room)` · `Course(code, title, credits, level, prereqs, terms_offered)` · `Section(code, course_code, term, instructor, schedule, capacity, enrolled_count, status)` · `CompletedCourse(student_id, course_code, credits, grade, grade_points, term, status, is_repeat)` · `StudentRecord(student_id, program_code, year, completed, current_section_codes)`.

Formats: `course_code` = `CS101` · `section_code` = `CS101-A` · `term` = `"Fall 2026"` / `"Spring 2027"`. Helpers (`parse_course_code`, `slots_overlap`, `time_to_minutes`) live in this file too.

## 4. The clock

`core/config.py` has `get_today()`: returns `settings.today_override` if set, else today's date. It is the **only** place that reads the clock. Domain functions never call it; services call it and pass `today` in. Seed the demo so that with the override set, `current_term` = Fall 2026 and `registration_term` = Spring 2027.

## 5. One fact, one owner

| Fact | Single source |
|---|---|
| GPA calculation and repeat-course rule (`BEST` attempt) | M2 `calculate_gpa` |
| Grade bands and points (`grading_scale.csv`) + `get_grade_points_map()` | M4 |
| Is registration open? | M3 `is_registration_open` / `TermInfo` |
| What may I bring to an exam? | M3 `ExamRules` |
| ID requirements at the exam | M5 `proctoring_policies` |
| Which standings block registration / transcripts | M2 `standing_policies.csv` fields `blocks_registration`, `blocks_transcripts` |
| Transcript fees and delivery times | M4 code table (docs say "the tool shows the fee") |
| Dates | CSV files only. **Policy docs never contain a literal date or fee.** |

## 6. Hand-offs (who needs what from whom)

| Needed by | From | What | By |
|---|---|---|---|
| everyone | M1 | `config.py` (incl. `get_today`), `shared_models.py` | Tue 27 Oct |
| everyone | M3 | `db.py`, `main.py`, chat route skeleton | Wed 28 Oct |
| everyone | M4 | `llm.py`, `tools.py` registry, agent loop v0 | Wed 28 / Fri 30 Oct |
| M4 | M5 | `retrieve_with_context(query, feature_area)` (a stub is fine) | Tue 27 Oct |
| M2 | M4 | `get_grade_points_map() -> dict[str,float]` and `passing_points` | Fri 6 Nov |
| M1 | M3 | `is_registration_open(term, today)`, `registration_term(today)` | Fri 6 Nov |
| M1, M4 | M2 | `get_student_record(student_id)`, `get_standing_status(student_id)` | Fri 6 Nov |
| M3 | M1 | `get_student_sections(student_id, term)` | Fri 6 Nov |
| M2 | M4 | the SSE event spec for `POST /chat/stream` (`meta`, `delta`, `tool`, `citations`, `confirm`, `done`, `error`) | Fri 30 Oct |
| M2, M5 | M1 | `useRealtime()` hook + the `/ws` seats contract | Fri 6 Nov |
| M4 | M3 | `PendingActionStore.propose(user, kind, payload, summary)` | Fri 6 Nov |
| M2 | M5 | `CitationChips`, `CitationDrawer`, `ToolCard`, `ConfirmCard` components | Fri 13 Nov |
| M5 | M1 | `sections.csv` (for `enrollments.csv`) | Fri 30 Oct |
| M5 | M2 | `students.csv` (for `enrollments.csv`) | Mon 2 Nov |

## 7. Seed data (each owner writes their CSVs; sizes are small on purpose)

| Collection | Size | Owner |
|---|---|---|
| `courses`, `sections` | ~30, ~45 | M1 |
| `enrollments` | consistent with `students` and `sections` | M5 (uses M1's sections and M2's students) |
| `students` (with transcripts), `users`, `programs`, `requirement_groups`, `standing_policies` | 10, 10, 3, ~12, 1 | M2 |
| `calendar_events`, `exam_schedules`, `exam_rules` | ~20, ~45, 1 | M3 |
| `grading_scale` (11 bands) | 11 | M4 |
| `substitution_rules`, `proctoring_policies` | ~8, 3 | M5 |

Quick check script (M3, W4): 40 lines. Fails CI if a `section_code` in `exam_schedules` or `enrollments` is missing from `sections`, or a course code in prereqs / requirement groups / substitution rules is missing from `courses`.

## 8. Golden set (30 questions, 3 per feature)

One JSON line each: `{"id","question","feature_area","needs_login","expected_facts":["..."],"must_cite":true|false}`. `expected_facts` are strings that must appear in the answer (a number, a date, a status). Each member writes 6 (their 2 features × 3). M3's `run_eval.py` runs them in W4.

## 9. Definition of done for any member

- [ ] Every tool in your slice answers its 3 golden questions in the browser
- [ ] Pure-function tests pass (listed in your member file)
- [ ] No hard-coded number/date/fee that also lives in a CSV
- [ ] You can explain your slice in under 2 minutes

## 10. Who owns what

The split of work, the day estimates behind it and the rules for rotating chores are in `01_FAIR_DIVISION.md`. Member files follow it.
