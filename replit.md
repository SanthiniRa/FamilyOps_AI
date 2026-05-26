# FamilyOps AI

An AI-powered Household Operations Platform — a production-grade full-stack application for managing family life with intelligent agents.

## Architecture

- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn-style Radix UI components — runs on port 5000
- **Backend**: FastAPI (Python 3.11), SQLAlchemy async, SQLite (dev) / PostgreSQL + pgvector (prod) — runs on port 8000
- **AI Engine**: LangGraph multi-agent orchestration, LangChain, OpenAI GPT-4o
- **Event System**: Async event bus for decoupled service communication
- **RAG**: pgvector-powered household memory with semantic search

## Features

- **Dashboard** — Real-time overview of all household operations
- **Tasks** — Create, assign, and track household tasks with priority management
- **Calendar** — Family event scheduling with visual monthly view
- **Grocery** — Smart shopping lists with AI-powered item suggestions
- **Meal Plans** — AI-generated weekly meal planning with nutritional summaries
- **Reminders** — Scheduled family alerts with recurrence support
- **Memory** — Semantic household knowledge base with RAG search
- **Family** — Member profiles with dietary restrictions and roles
- **AI Agent** — LangGraph orchestrated chat interface with agent run history
- **Settings** — Integration configuration (Supabase, OpenAI, Google Calendar, Email)

## Project Structure

```
/
├── src/                    # Next.js App Router source
│   ├── app/                # Pages (dashboard, tasks, calendar, etc.)
│   ├── components/         # Reusable UI components
│   └── lib/                # API client, utilities
├── backend/
│   ├── main.py             # FastAPI application entry point
│   ├── app/
│   │   ├── agents/         # LangGraph multi-agent orchestrator
│   │   ├── api/routes/     # REST API route handlers
│   │   ├── core/           # Config, logging
│   │   ├── db/             # SQLAlchemy models & database setup
│   │   ├── events/         # Async event bus
│   │   ├── memory/         # RAG / pgvector integration
│   │   ├── evals/          # Evaluation pipeline hooks
│   │   └── observability/  # OpenTelemetry & Prometheus hooks
│   └── requirements.txt
├── next.config.js          # Next.js config (API proxy to backend)
├── tailwind.config.ts
└── tsconfig.json
```

## Running Locally

The app uses two workflows:
- **Start application** — `npm run dev` (port 5000, Next.js frontend)
- **Backend API** — `cd backend && python -m uvicorn main:app --host localhost --port 8000 --reload`

Frontend proxies `/api/v1/*` requests to the backend via `next.config.js`.

## Configuration

Copy `backend/.env.example` to `backend/.env` and populate:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | GPT-4o + embeddings for all agents |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | Supabase service role key for server-side ops |
| `DATABASE_URL` | PostgreSQL connection string (falls back to SQLite in dev) |
| `GOOGLE_CLIENT_ID/SECRET` | Google Calendar OAuth |
| `EMAIL_ADDRESS/PASSWORD` | Gmail IMAP for email ingestion |

## Multi-Agent Architecture

The LangGraph orchestrator routes natural-language requests to specialist agents:
- **Email Agent** — Ingests and summarizes emails
- **Calendar Agent** — Schedules events and syncs with Google Calendar
- **Grocery Agent** — Manages shopping lists with AI suggestions
- **Meal Agent** — Generates weekly meal plans with dietary awareness
- **Reminder Agent** — Creates and dispatches family alerts
- **Memory Agent** — Stores/retrieves household knowledge via semantic search
- **Task Agent** — Creates and orchestrates household tasks

## User Preferences

- Prefer production-grade patterns (async SQLAlchemy, structured logging, event-driven architecture)
- SQLite for local development, PostgreSQL + pgvector for production
- All agent context preserved in SQLite `agent_runs` table
