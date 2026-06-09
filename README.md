# FamilyOps AI

AI-powered home assistant for:
- Email → Calendar automation
- Meal planning from kitchen images
- Smart grocery & reminders

## Tech Stack
- Next.js
- Supabase (DB + Auth + Storage)
- OpenAI / LLM
- pgvector

## Features
1. Email → Event extraction
2. Image → Ingredients → Meal Plan
3. AI Chat Assistant

## Architecture
Frontend → API → AI → Supabase → Integrations

## Production folder structure
- `/src/` — active Next.js frontend application source
- `/backend/` — FastAPI backend and AI service code
- `frontend/` — stale duplicate frontend copy, not used in production
- `main.py` — obsolete root script, kept only if needed for local experiments
- `pyproject.toml` — obsolete Python packaging file; backend uses `/backend/requirements.txt`
- celery -A app.core.celery_app.celery worker --loglevel=info (run in seperate terminal)
- celery -A app.core.celery_app.celery beat --loglevel=info
- export REDIS_URL=redis://localhost:6379/0
- docker start a6f6689cee29 turn on the redis and then celery()
##for evals
- python -m evaluation.pipeline \
  --dataset evaluation/dataset/evaluation_dataset.json \
  --results evaluation/results.json \
  --threshold 0.80 \
  --mode baseline
- python -m evaluation.pipeline \
  --dataset evaluation/dataset/evaluation_dataset.json \
  --results evaluation/results.json \
  --threshold 0.80 \
  --mode live
-mode live
- `make eval` - run the baseline evaluation from the terminal
- `make eval-live` - run the live evaluation from the terminal
- RAG eval coverage includes context precision, context recall, faithfulness, and answer relevancy
