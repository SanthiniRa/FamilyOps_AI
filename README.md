# FamilyOps AI

FamilyOps AI is an autonomous household operations platform for email-to-calendar automation, meal planning, grocery support, reminders, memory search, and live family utilities.

## What It Does

- Routes household requests through specialist agents
- Turns emails into tasks and calendar actions
- Supports meal planning, recipes, groceries, and reminders
- Stores family knowledge with retrieval-augmented search
- Pulls in live web, weather, event, and recipe information
- Exposes a FastAPI backend, a Next.js frontend, and evaluation workflows

## Key Features

| Capability | Description |
| --- | --- |
| Multi-agent routing | LangGraph-style orchestration for household workflows |
| Dashboard | Overview of tasks, calendar, groceries, reminders, memory, and activity |
| Email workflows | Ingests household email and turns it into actionable work |
| Meal planning | Creates meal plans and recipe suggestions from available context |
| Grocery support | Manages lists and shopping-oriented workflows |
| Family reminders | Creates and tracks reminders for members of the household |
| Household memory | Stores and retrieves family knowledge with RAG-backed search |
| Live utilities | Web search, weather, event, and recipe lookup |
| Document ingestion | Upload and index documents into the knowledge hub |
| Observability | Logging, metrics, tracing, and optional Langfuse support |

## Tech Stack Architecture

FamilyOps AI is built as a modular monolith: the frontend handles the user experience, the backend owns orchestration and business rules, and shared data/services sit underneath both. That keeps the stack simple to run locally while still giving us clear boundaries for agents, retrieval, and integrations.

```text
User
  |
  v
Next.js 14 + React 18 + TypeScript
  |
  v
FastAPI API + SQLAlchemy + Pydantic
  |
  v
Orchestrator / Specialist Agents
  |-- Tasks
  |-- Calendar
  |-- Grocery
  |-- Meals
  |-- Reminders
  |-- Memory / RAG
  |-- Family
  |-- Email processing
  |-- Live search utilities
  |
  v
Data + Infra
  |-- PostgreSQL / Supabase
  |-- Qdrant vector search
  |-- Redis + Celery background jobs
  |-- Logging, metrics, tracing, Langfuse
```

### Layer Breakdown

| Layer | Stack | Responsibility |
| --- | --- | --- |
| Presentation | Next.js 14, React 18, TypeScript | Dashboard, workflow UIs, navigation, and client-side data fetching |
| UI system | Tailwind CSS, Radix UI, Framer Motion, Recharts | Component primitives, styling, motion, and charts |
| API layer | FastAPI, Pydantic, SQLAlchemy | HTTP routes, request validation, persistence, and response shaping |
| Orchestration | LangGraph-style agent routing | Routes work to task, calendar, grocery, meal, memory, email, and utility flows |
| AI layer | OpenAI primary, Google Gemini fallback | Intent handling, extraction, summarization, and planning |
| Retrieval | BM25 + dense search + reranking + Qdrant | Household memory and document search |
| Background jobs | Redis, Celery | Email ingest, processing, and longer-running work |
| Integrations | Email, weather, events, recipes, web search | External information and household automation inputs |
| Observability | Logging, metrics, tracing, Langfuse | Debugging, dashboards, evaluation, and runtime visibility |

## System Design

The backend keeps orchestration, retrieval, and integrations in one codebase so the system stays easier to build, test, and evolve, while still allowing each workflow to be reasoned about separately.

### Design Choices

| Area | Choice | Trade-off |
| --- | --- | --- |
| Backend shape | Single FastAPI backend with agent and service layers | Simpler to ship and operate, but less isolated than separate microservices |
| Retrieval | Hybrid RAG with BM25, dense search, RRF, and reranking | Better relevance, but more tuning and slightly more latency |
| Vector store | Qdrant for memory retrieval | Fast local-friendly retrieval, but adds an extra dependency |
| Storage | PostgreSQL-compatible storage via Supabase | Good developer experience and managed reliability, but couples the app to one primary data layer |
| General web search | DuckDuckGo HTML search plus page fetching | Lightweight and provider-flexible, but less structured than a paid search API |
| Evaluations | Deterministic synthetic evals with live mode | Stable CI signal, but not a full substitute for production telemetry |
| Frontend | Next.js UI plus backend APIs | Fast to iterate and easy to deploy, but the app is less split than a pure API-first architecture |

### Why This Architecture

- It keeps the product fast to iterate on while the workflow surface area is still growing.
- It supports household workflows that need orchestration, retrieval, and integrations without forcing a microservice split too early.
- It allows the evaluation pipeline to exercise the same routing and retrieval ideas the product uses.
- It leaves room to split out services later if traffic, team size, or reliability needs increase.

### Data Flow

1. The user submits a request through the Next.js frontend or the API.
2. The orchestrator classifies the intent and routes the request to the right workflow.
3. The workflow may call memory retrieval, web search, weather, event, or recipe services.
4. Retrieved context is filtered, ranked, and assembled into a response prompt.
5. The model generates the final answer, and the backend returns it to the UI.
6. Observability hooks capture logs, metrics, traces, and eval results for later review.

### Failure Modes

| Failure mode | Handling strategy |
| --- | --- |
| Missing external API key | Return a clear validation error and keep the rest of the app usable |
| Retrieval returns weak context | Fall back to a broader search path or a safer answer template |
| LLM call fails | Use a graceful error response and record the failure for eval/debugging |
| Web search is unavailable | Continue without live web evidence and surface a partial result |
| Background jobs lag | Keep the synchronous API path functional and let jobs catch up later |
| Vector store unavailable | Fall back to database-backed memory search where possible |

### Scalability Notes

- The modular service layout makes it easy to split retrieval, search, or agent workflows later.
- Qdrant can stay local during development and move to an external service in production.
- Celery keeps longer-running tasks off the request path, which helps the UI stay responsive.
- The main scaling pressure points are retrieval latency, web fetch latency, and LLM response time.
- If usage grows, the first likely split is background jobs or retrieval services, not the full frontend/backend stack.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 14, React 18, TypeScript |
| UI | Tailwind CSS, Radix UI, Framer Motion, Recharts |
| Backend | FastAPI, SQLAlchemy, Pydantic settings |
| Resilience | Retries, caching, and rate limiting for live external utilities |
| Orchestration | LangGraph-style multi-agent backend |
| AI | OpenAI primary, Google Gemini fallback |
| Storage | Supabase / PostgreSQL-compatible database, pgvector-oriented RAG workflows |
| Web search | DuckDuckGo HTML search with page fetching and orchestration support |
| Weather | Open-Meteo weather lookups with UK-friendly defaults |
| Events | Ticketmaster-powered local and family-friendly event search |
| Recipes | TheMealDB recipe search and inspiration lookup |
| Background jobs | Redis, Celery |
| Observability | Metrics, tracing, logging, optional Langfuse |

## Getting Started

### Install dependencies

```sh
npm install
```

```sh
cd backend
pip install -r requirements.txt
```

### Configure environment variables

```sh
cp backend/.env.example backend/.env
```

Then fill in the values you need in `backend/.env`.

### Run locally

Frontend:

```sh
npm run dev
```

Backend:

```sh
npm run backend
```

### Run with Docker

```sh
cp backend/.env.example backend/.env
docker compose up --build
```

The Compose stack brings up the frontend, backend, PostgreSQL, Redis, and Qdrant together. See [DEPLOYMENT.md](/workspaces/FamilyOps_AI/DEPLOYMENT.md) for production notes.
The Docker stack enables shared resilience Redis in the backend container so retries, caching, and rate limits are coordinated across services.

Optional background jobs:

```sh
docker compose up -d redis
export REDIS_URL=redis://localhost:6379/0
celery -A app.core.celery_app.celery worker --loglevel=info
celery -A app.core.celery_app.celery beat --loglevel=info
```

## Branch Protection

If you want GitHub to block merges until the project is healthy, require these checks on the default branch:

- `Backend tests`
- `Frontend build`
- `Docker validation`
- `Evaluation pipeline`

If you add an approval rule for your own workflow, I’d also keep `Require branches to be up to date` enabled so the checks always run against the latest base branch.

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Service info |
| GET | `/health` | Health check |
| GET | `/api/docs` | Swagger UI |
| GET | `/api/redoc` | ReDoc |
| POST | `/api/v1/auth/register` | Register a user |
| POST | `/api/v1/auth/login` | Get a JWT access token |
| GET | `/api/v1/auth/me` | Current user profile |
| GET | `/api/v1/dashboard/summary` | Dashboard summary |
| GET/POST | `/api/v1/tasks` | Task workflows |
| GET/POST | `/api/v1/calendar/events` | Calendar workflows |
| GET/POST | `/api/v1/grocery` | Grocery workflows |
| GET/POST | `/api/v1/meals` | Meal planning workflows |
| GET/POST | `/api/v1/reminders` | Reminder workflows |
| GET/POST | `/api/v1/memory` | Household memory workflows |
| GET/POST | `/api/v1/family` | Family member and preference workflows |
| POST | `/api/v1/uploads/document` | Upload a document for ingestion |
| POST | `/api/v1/uploads/{doc_id}/ingest` | Manually trigger document ingestion |
| POST | `/api/v1/web/search` | Search the web for current external information |
| POST | `/api/v1/weather/search` | Search live weather by location |
| POST | `/api/v1/events/search` | Search local family-friendly events |
| POST | `/api/v1/recipes/search` | Search external recipe ideas |
| GET | `/api/v1/briefing/daily` | Daily family briefing |

## Prompt Types

Use prompts like these to trigger the right capability:

| Prompt type | Example prompt | Routed to |
| --- | --- | --- |
| Task | `Create a task for me to book the dentist` | Task agent |
| Calendar | `Add a school meeting to my calendar tomorrow at 3pm` | Calendar agent |
| Grocery | `Make a grocery list for this week` | Grocery agent |
| Meal | `Plan dinners for next week using what we already have` | Meal agent |
| Recipe | `Find me a quick chicken pasta recipe` | Recipe agent |
| Weather | `What's the weather in London this weekend?` | Weather agent |
| Events | `Find family-friendly events near Manchester` | Event agent |
| Web search | `Look up the latest advice on UK school holiday activities` | Web search agent |
| Reminder | `Remind me to pack the kids' bags on Friday evening` | Reminder agent |
| Memory | `What did we save about the holiday travel plans?` | Memory agent |
| Email | `Summarize my latest inbox and turn action items into tasks` | Email agent |
| General | `Give me a quick household overview` | General agent |

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in the values you need.

### Core

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

DATABASE_URL=
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_SERVICE_KEY=

REDIS_URL=redis://localhost:6379
ENABLE_SHARED_RESILIENCE_REDIS=false
API_BEARER_TOKEN=
SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=10080
```

### Retrieval and fallback

```env
GOOGLE_API_KEY=
GOOGLE_MODEL=gemini-2.5-flash
GOOGLE_EMBEDDING_MODEL=models/embedding-001

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=familyops_memory
```

### Email, calendar, search, and tracing

```env
EMAIL_IMAP_HOST=
EMAIL_IMAP_PORT=993
EMAIL_ADDRESS=
EMAIL_PASSWORD=

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/calendar/oauth/callback

LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# Web search supports duckduckgo, tavily, or auto.
WEB_SEARCH_PROVIDER=duckduckgo
WEB_SEARCH_TAVILY_API_KEY=
WEB_SEARCH_TAVILY_SEARCH_DEPTH=basic
WEB_SEARCH_MAX_RESULTS=5
WEB_SEARCH_FETCH_LIMIT=3
WEB_SEARCH_TIMEOUT_SECONDS=12

# Weather search uses Open-Meteo, with a UK default country code.
WEATHER_DEFAULT_COUNTRY_CODE=GB
WEATHER_FORECAST_DAYS=5
WEATHER_TIMEOUT_SECONDS=12

# Event search uses Ticketmaster.
EVENT_SEARCH_PROVIDER=ticketmaster
EVENT_SEARCH_COUNTRY_CODE=GB
EVENT_SEARCH_TIMEOUT_SECONDS=12
TICKETMASTER_API_KEY=

# Recipe search uses TheMealDB.
RECIPE_SEARCH_PROVIDER=themealdb
RECIPE_SEARCH_TIMEOUT_SECONDS=12
```

## Evaluation

The evaluation pipeline covers:

- task-specific success for each workflow category
- error handling behavior when a case fails
- cost efficiency via estimated token and cost units
- latency tracking for retrieval, generation, and end-to-end response time
- RAG quality signals such as context precision, context recall, faithfulness, and answer relevancy
- version metadata for the eval dataset and the prompt snapshot used in a run
- a published `version-manifest.json` alongside the eval results for CI traceability

The backend also exposes `GET /api/v1/dashboard/version` so the UI can show the active backend version and prompt registry snapshot.

Run it with:

```sh
make eval
```

```sh
make eval-live
```

Or directly:

```sh
python -m evaluation.pipeline \
  --dataset evaluation/dataset/evaluation_dataset.json \
  --results evaluation/results.json \
  --threshold 0.80 \
  --mode baseline
```

```sh
python -m evaluation.pipeline \
  --dataset evaluation/dataset/evaluation_dataset.json \
  --results evaluation/results.json \
  --threshold 0.80 \
  --mode live
```

## Project Structure

```text
src/                 Next.js frontend source
backend/             FastAPI backend, agents, services, workers, docs
evaluation/          Baseline and live evaluation pipelines
frontend/            Legacy frontend copy, not used in production
README.md            Production project readme
```

## Tests

```sh
cd backend
pytest -q
```

```sh
pytest backend/tests -q
```

The backend test suite includes email graph, ingestion, memory, privacy, weather, event, recipe, and RAG retrieval coverage.

## Documentation

- `backend/IMPLEMENTATION_SUMMARY.md` - implementation overview
- `backend/INGESTION.md` - document ingestion flow
- `backend/LANGGRAPH_ARCHITECTURE_REPORT.md` - orchestration architecture notes
- `backend/MIGRATION_AND_TESTING_GUIDE.md` - migration and testing guide
- `evaluation/pipeline.py` - evaluation runner

## Roadmap

| Phase | Status | Scope |
| --- | --- | --- |
| Core household platform | Complete | Frontend, backend, and dashboard workflows |
| Multi-agent orchestration | Complete | Specialist agents and routing |
| Live utilities | Complete | Web search, weather, event, and recipe lookups |
| Email and ingestion pipelines | Complete | Email ingestion, document ingestion, and memory capture |
| Observability and background jobs | Complete | Logging, metrics, tracing, and Celery workflows |
| Future enhancements | Planned | Expanded integrations, UX polish, and production hardening |
