# University Chatbot (MVP)

An AI chatbot for students, built with an LLM (Groq) and RAG (retrieval over policy docs).
**Core rule:** code decides the facts (dates, GPA, eligibility, fees). The model only explains them and cites sources.

## Team

| Member | Slice | Branch prefix |
|---|---|---|
| M1 | Registration, schedule conflicts, real-time seats | `m1/` |
| M2 | Degree progress, standing, login, chat screen | `m2/` |
| M3 | Calendar, exams, server, confirm flow | `m3/` |
| M4 | Grading, transcripts, agent loop | `m4/` |
| M5 | Substitutions, proctoring, RAG search, chat components | `m5/` |

## Repo layout

```
backend/
  app/
    core/        config, db, llm, tools registry, security, retrieval, events
    domain/      pure logic (no I/O, no clock): rules and engines
    data/        database queries (repos)
    services/    tools + agent loop + action store
    api/         main.py, ws.py, routes/
  scripts/       run_eval.py, check_seed.py
  tests/
frontend/
  src/core/      useRealtime.ts
  src/features/  chat/ (screen + components/), registration/
data/
  seed/          CSV seed files (each owner adds their own)
  policy_docs/   .md docs ingested by RAG (no literal dates or fees!)
  golden/        30 golden questions (JSON lines)
docs/            the plan: contracts, member files, fair division
```

Read `docs/00_SHARED_CONTRACTS.md` first, then your own member file in `docs/`.

## Quick start

```bash
git clone <repo-url>
cd uni-chatbot
cp .env.example .env        # then fill in your own keys (never commit .env)

# backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# frontend (in another terminal)
cd frontend
npm install
npm run dev
```

## Rules

1. Never push straight to `main`. Work on your branch, open a Pull Request.
2. One branch per person per week: `m1/w1`, `m1/w2`, ...
3. Keep PRs small, and get at least one review before merging.
4. Edit files you own. If you need a change in someone else's file, ask them or open a small PR and tag them.
5. Never commit `.env`, API keys or passwords.
6. Policy docs never contain literal dates or fees (they live in CSVs / code).

See `GIT_GUIDE.md` for the step-by-step Git workflow and the demo script.
