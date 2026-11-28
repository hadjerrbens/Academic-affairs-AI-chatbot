# M5 — Substitutions, Proctoring, Search & Chat Components (MVP)

**Features:** F9 Course substitution / waiver process · F10 Proctoring info
**Why together:** both are policy-heavy — rules in prose plus a small amount of structured data.
**Read first:** `00_SHARED_CONTRACTS.md`. **You also own the search layer (RAG), the system prompt, and the chat components (citations, cards, confirm card).**

## Foundation you own (W1)
- `core/retrieval.py` — split policy docs into chunks, embed (Voyage multilingual), store in Mongo, hybrid search (vector + keyword), return `retrieve_with_context(query, feature_area) -> (context_text, citations)`. **A stub with the final signature by Tue 27 Oct**, real by Fri 30 Oct.
- *(The chat screen is now M2's. You supply the components it imports.)*

## Your 5 files

| # | File | What it holds |
|---|---|---|
| 1 | `core/retrieval.py` | see above. Tag every chunk with `feature_area`. Ingest **all** teammates' docs (`course_registration.md`, `degree_requirements.md`, `academic_standing.md`, `academic_calendar.md`, `exam_rules.md`, `grading_system.md`, `transcript_requests.md`, `course_substitution.md`, `proctoring.md`). |
| 2 | `core/prompts.py` + `domain/intent_router.py` | system prompt, refusal templates, keyword fallback router. |
| 3 | `data/policy_repo.py` + `domain/policy_rules.py` | substitution rules and proctoring policies; pure `evaluate_substitution`. |
| 4 | `services/policy_service.py` | the 3 tools below. |
| 5 | `frontend/features/chat/components/` | `CitationChips`, `CitationDrawer`, `ToolCard` (result cards), `ConfirmCard` — imported by M2's `ChatShell`. |

## System prompt (file 2) — the grounding contract
- State only facts that appear in a tool result or in the `<context>` block. **Never compute** a GPA, date, fee or conflict.
- Cite with `[source N]` only when the fact came from `<context>`.
- If the facts aren't there: say so and point to the registrar. Don't guess.
- Never reveal another student's data. The bot **proposes** actions, it never performs them.
- Ask at most one clarifying question.
- Out-of-scope (admissions, fees, housing, library): refuse politely and list the 10 things the bot can do.
- Keyword fallback `keyword_route(text) -> label` is used when the LLM router fails or the budget is gone.

## Substitution and proctoring (files 3–4)

**`evaluate_substitution(target, substitute, rules, student_courses: list[CompletedCourse])`** — fixed order: (1) no rule for the target → `NEEDS_ADVISOR_REVIEW`; (2) substitute not in the accepted list → `LIKELY_INELIGIBLE`; (3) student hasn't taken the substitute → `INSUFFICIENT_INFORMATION`; (4) grade below the rule's minimum → `LIKELY_INELIGIBLE`; (5) credits below the rule's minimum → `LIKELY_INELIGIBLE`; else `LIKELY_ELIGIBLE`. `target == substitute` is a validation error, not a verdict. The verdict is always "likely" — an advisor decides.

**Waiver (exemption) vs substitution:** in the MVP the bot **explains** the waiver process (from `course_substitution.md`) and checks substitution eligibility. It does **not** submit anything.

**Proctoring:** policies are keyed by **mode** (in-person, online, proctoring centre). "How is **my** CS101 final proctored?" → read the exam's `proctoring_type` from M3's schedule → return the policy for that mode. **ID requirements live here.** "What can I bring?" is **M3's** exam rules — the proctoring answer links there instead of repeating it.

## Your 3 tools

| Tool | Returns |
|---|---|
| `explain_waiver_process()` (public) | the process steps from the doc + which office/advisor: `{steps, summary, citations}` |
| `check_waiver_eligibility(target_course, substitute_course)` | `{verdict, reasons, required_documents, summary}` |
| `get_proctoring_info(exam_type?, course_code?)` (public) | `{mode, provider?, location, id_requirements, technical_requirements, reschedule_policy, summary}` |

## The chat components (file 5)
M2 builds the screen; you build the parts that show your work:
- **`CitationChips`** — `[source N]` markers rendered as clickable chips.
- **`CitationDrawer`** — opens the source chunk (title, section heading, text) when a chip is clicked.
- **`ToolCard`** — renders a `card` event; reuses M1's `RegistrationCard` for registration answers and a plain table for the rest.
- **`ConfirmCard`** — summary, fee, Confirm / Cancel; calls `POST /actions/{id}/confirm` once, then disables itself and shows the result.
Hand these to M2 by **Fri 13 Nov** (a version with fake data is fine by Fri 6 Nov).

## Seed data and docs (W1)
`substitution_rules.csv` (~8: target, accepted substitutes, min grade, min credits, advisor note), `proctoring_policies.csv` (3 modes), `course_substitution.md`, `proctoring.md` — process prose, **no literal dates or fees**.

**Also yours (moved from M1):** `enrollments.csv` — current-term and next-term enrollments for the 10 students, consistent with M1's `sections.csv` and M2's `students.csv`. Include one student with a deliberate class clash and one section that's full, so the demo has interesting cases. You need sections from M1 (Fri 30 Oct) and students from M2 (Mon 2 Nov); deliver by **Wed 4 Nov**.

## Tests (must pass)
- retrieval: 10 hand-written questions each return the right chunk in the top 3 (**do this in W1, before building on it**)
- chunker keeps headings and doesn't split mid-sentence
- each substitution verdict in order; `target == substitute` → validation error
- proctoring: mode comes from the exam's `proctoring_type`, not the exam type
- router: all 30 golden questions routed correctly ≥ 70% by keywords alone
- UI (Vitest): a citation chip opens the right chunk; the Confirm card calls the endpoint once and disables itself

## Week by week

| Week | Deliverable | Gate |
|---|---|---|
| W1 (26 Oct) | `retrieval.py` (stub Tue, real Fri), ingest 2 docs, 10-question retrieval test, 2 docs + CSVs | **B+ question shows a source chip (Sun 1 Nov)** |
| W2 | `prompts.py`, router fallback, File 3 + tests, all other docs ingested, `enrollments.csv` (Wed 4 Nov) | Public questions answered with citations |
| W3 | File 4 (tools), components for M2 (fake data Fri 6 Nov, real Fri 13 Nov) | Both features answer 3 golden questions each |
| W4 | Review the 30 golden questions with M3, fix retrieval misses, polish the drawer | 30 golden questions run; no answer cites the wrong source |
| W5 | Demo script and rehearsal | Frozen Sat 28 Nov |

## Cut order if behind
Result cards → the Confirm card (transcript flow becomes text). **Never cut:** citations, the grounding contract, the refusal for out-of-scope questions.

## Risk to watch
Retrieval always looks easy and then gets fiddly. If your 10-question test is below 8/10 by Wed 28 Oct, fall back to keyword-only search plus a hand-written `feature_area` filter and keep moving.
