# Work-Bot Hunter — Kenya-First Job Intelligence Platform

## Quick Start

### Using Docker (recommended)

```bash
cp .env.example .env
# Edit .env with your values

docker compose up -d
```

API available at http://localhost:8000
API docs at http://localhost:8000/docs

### Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL and Redis (or use Docker)
docker compose up -d db redis

# Run migrations
alembic upgrade head

# Start the API
uvicorn backend.api.app:app --reload

# Start worker
celery -A backend.workers.celery_app worker -l info

# Start scheduler
celery -A backend.workers.celery_app beat -l info
```

## Architecture

```text
work-bot-hunter/
├── backend/
│   ├── api/           FastAPI routes + schemas
│   ├── models/        SQLAlchemy database models
│   ├── services/      Normalizer, dedup, scoring
│   ├── scrapers/      Job source adapters
│   ├── parsers/       CV and description parsing
│   ├── ai/            LLM integration (Phase 4)
│   ├── matching/      Multi-stage matching engine
│   ├── risk/          Scam/fraud detection
│   ├── applications/  Application tracking
│   ├── security/      Auth, encryption
│   └── workers/       Celery background tasks
├── frontend/          React dashboard (Phase 2)
├── tests/
├── migrations/        Alembic migrations
└── docker-compose.yml
```

## Job Sources (Kenya-First)

| Source | Tier | Country | Type |
|--------|------|---------|------|
| BrighterMonday | 1 | KE | Job board |
| MyJobsKenya | 1 | KE | Job board |
| Jobicy | 2 | Global | Remote API |
| Greenhouse | 2 | Global | ATS boards |
| Ashby | 2 | Global | ATS boards |

## Pipeline

```text
Scrapers → Normalizer → Deduplication → Risk Analysis → Matching → Store → API
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /jobs | List jobs with filters |
| GET | /jobs/{id} | Job details + analysis |
| POST | /jobs/search | Search jobs |
| POST | /candidate/profile | Create/update profile |
| POST | /candidate/cv | Upload CV |
| GET | /applications | List applications |
| POST | /applications | Create application |
| PATCH | /applications/{id} | Update status |
| GET | /analytics/overview | Dashboard stats |

## Configuration

All configuration via environment variables. See `.env.example`.

Matching weights, risk thresholds, and classification scores are configurable.
# Task-Sniffer
