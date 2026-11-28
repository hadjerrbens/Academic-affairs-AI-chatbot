# University Academic Affairs Chatbot (merged)

FastAPI + MongoDB + Groq + React/TypeScript. No Prolog: standing, degree audit, substitutions and proctoring are plain Python.

## Run
```bash
cp .env.example .env            # set MONGODB_URI, JWT_SECRET (long random), GROQ_API_KEY, optional VOYAGE_API_KEY
cd backend && pip install -r requirements.txt
python scripts/seed_db.py       # CSVs -> MongoDB (checks manifest.json counts)
python scripts/ingest_policy.py # policy docs -> policy_chunks (embeddings if VOYAGE_API_KEY)
uvicorn app.api.main:create_app --factory --reload      # http://localhost:8000/health
cd ../frontend && npm install && npm run dev            # http://localhost:5173
```
Tests: `cd backend && pytest` (150, fake MongoDB, no network) and `cd frontend && npm test`.

## Known gaps
- M1 is not in the zips: no registration-eligibility / schedule-conflict tools and no live seat updates.
- Transcript delivery names differ: code uses pickup/post/email, `transcript_fees.csv` uses electronic/paper.
- Daily token budget and rate limiter are in memory (reset on restart).
