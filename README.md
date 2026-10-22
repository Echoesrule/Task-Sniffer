# Task Sniffer

Kenya-first AI-powered job intelligence platform. Scrapes, normalizes, deduplicates, risk-scores, and matches jobs across multiple sources — with a Telegram bot for real-time alerts and a web dashboard for tracking.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy 2.0 (async) + SQLite/PostgreSQL |
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind CSS 4 |
| Bot | python-telegram-bot v22 (integrated into FastAPI) |
| Scraping | httpx + BeautifulSoup4 + lxml |
| Risk | Deterministic rule engine (35+ patterns) |
| Matching | 3-stage: keyword → fuzzy → structural |
| Charts | Recharts |
| Animations | Framer Motion |
| UI | Radix UI + Lucide icons |

## Quick Start

### Option 1: Local (SQLite)

```bash
git clone <repo>
cd work-hunter-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy env and add your Telegram token
cp .env.example .env

# Start API + Telegram bot
python run.py
```

API: http://localhost:8000
Docs: http://localhost:8000/docs

### Option 2: Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://localhost:3000

### Option 3: Docker (PostgreSQL + Redis)

```bash
cp .env.example .env
# For Docker Compose, set POSTGRES_PASSWORD, SECRET_KEY and ENCRYPTION_KEY, then set
# DATABASE_URL / DATABASE_URL_SYNC to PostgreSQL URLs using host `db`.
docker compose up -d
```

The Compose stack refuses to start without database credentials, a JWT signing
key and the CV encryption key. Generate `SECRET_KEY` with
`python -c 'import secrets; print(secrets.token_urlsafe(48))'`. Generate
`ENCRYPTION_KEY` with
`python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'`.
Keep both values in a deployment secret manager and retain the CV key backups
separately; losing the CV key makes encrypted documents unrecoverable.

New CV uploads are encrypted with AES-256-GCM before they are written to the
persistent `cv_data` volume. Before upgrading an installation with existing CVs,
provision `ENCRYPTION_KEY`, stop uploads, run
`python scripts/encrypt_legacy_cvs.py --dry-run`, review the count, then run
`python scripts/encrypt_legacy_cvs.py`. The script writes and verifies encrypted
replacements before updating candidate paths and retains the plaintext originals
under their old filenames. Verify authorized downloads and encrypted backups
before securely removing those plaintext originals. Back up both the database
and CV volume before conversion; rollback is restoring that paired snapshot so
the old database paths still point to their original plaintext files. Legacy
files are not served as plaintext by the new endpoint; they return HTTP 409
until migrated.

Match scores are stored per candidate in `candidate_job_scores`. Existing
`jobs.match_score` and `jobs.match_breakdown` columns remain for compatibility,
but historical values are not returned as personalized scores. Existing
candidate profiles can be backfilled one at a time with
`python scripts/score_jobs.py --candidate-id <candidate-id>`; use `--only-empty`
to preserve already calculated candidate/job rows. New profile saves rescore
that profile, and ingestion calculates independent scores for current profiles.
The local development configuration generates an ephemeral signing key when
`SECRET_KEY` is empty, so development tokens expire when the server restarts.
Docker Compose runs the Alembic revisions before starting the API. Local SQLite
startup retains the existing `create_all` plus additive migration behavior.

## Architecture

```text
work-hunter-bot/
├── backend/
│   ├── api/              FastAPI app, routes, schemas, deps
│   ├── models/           SQLAlchemy models (8 tables)
│   ├── scrapers/         5 job source adapters
│   ├── services/         Normalizer, deduplicator, scorer
│   ├── matching/         3-stage matching engine
│   ├── risk/             Scam/fraud detection engine
│   ├── telegram/         Bot + handlers + auto-alerts
│   ├── security/         JWT auth, bcrypt
│   ├── parsers/          CV and description parsing
│   ├── ai/               LLM integration (planned)
│   └── workers/          Celery background tasks
├── frontend/
│   └── src/
│       ├── app/          7 pages (Dashboard, Jobs, Detail, Applications, Analytics, CV, Settings)
│       ├── components/   Reusable UI (MatchScore, RiskBadge, StatCard, JobCard, Sidebar, Header)
│       ├── data/         Mock data for development
│       ├── services/     API service layer
│       ├── types/        TypeScript interfaces
│       └── lib/          Utilities
├── tests/unit/           29 tests
├── migrations/           Alembic
├── src/                  Legacy Telegram bot (deprecated)
├── run.py                Server entry point
└── docker-compose.yml
```

## Job Sources

| Source | Tier | Focus | Type |
|--------|------|-------|------|
| BrighterMonday | 1 | Kenya | Job board |
| MyJobsKenya | 1 | Kenya | Job board |
| Jobicy | 2 | Global | Remote API |
| Greenhouse | 2 | Global | ATS boards |
| Ashby | 2 | Global | ATS boards |

## Pipeline

```text
Scrapers → Normalizer → Deduplication → Risk Analysis → Matching → Store → API / Telegram Alerts
```

Each job goes through:
1. **Scrape** — fetch from source APIs/pages
2. **Normalize** — standardize fields, extract skills, parse salary
3. **Dedup** — fingerprint + similarity check (rapidfuzz)
4. **Risk** — 10 checks, 35+ patterns, scored 0-100
5. **Match** — 3-stage: keyword → fuzzy → structural (8 dimensions)
6. **Store** — SQLite/PostgreSQL with full audit trail
7. **Alert** — Telegram push to matching users (every 5 min)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/jobs` | List jobs with filters |
| GET | `/jobs/{id}` | Job detail + analysis |
| POST | `/jobs/search` | Search jobs |
| GET | `/candidate/profile` | Get candidate profile |
| POST | `/candidate/profile` | Create/update profile |
| POST | `/candidate/cv` | Upload CV |
| GET | `/applications` | List applications |
| POST | `/applications` | Create application |
| PATCH | `/applications/{id}` | Update status |
| GET | `/analytics/overview` | Dashboard stats |
| GET | `/analytics/match-distribution` | Score distribution |
| GET | `/analytics/top-sources` | Source performance |
| GET | `/analytics/risk-summary` | Risk breakdown |
| GET | `/analytics/activity` | Recent activity |

## Telegram Bot

The bot runs automatically with the API server. No separate process needed.

### Commands

| Command | Description |
|---------|-------------|
| `/start` | Register for job alerts |
| `/stop` | Unsubscribe |
| `/top` | View top 5 highest-match jobs |
| `/search <query>` | Search by title/company/skills |
| `/apply <job_id>` | Track an application |
| `/my_applications` | List your tracked apps |
| `/update_status <id> <status>` | Change app status |
| `/settings` | View preferences |
| `/set_keywords python,react` | Set match keywords |
| `/set_exclude intern,junior` | Set exclusions |
| `/set_salary 200000` | Set min salary (KES) |
| `/stats` | Job statistics |
| `/sources` | List active sources |

### Automated Alerts

The bot scans every 5 minutes for new jobs matching each user's preferences:
- Jobs scoring **≥60% match** with **<40% risk** are pushed automatically
- Filtered by user's keywords, exclusions, and salary threshold
- Requires the Telegram profile to be linked to a web candidate; ranking uses that candidate's scores
- No manual intervention needed — just `/start` and set your preferences

Each user/job alert has a durable delivery record, bounded retries and an
expiring send claim so concurrent workers do not normally send the same alert.
Delivery is at least once: if Telegram accepts a message but the process dies
before recording success, retrying the expired claim can still send a duplicate.
Ambiguous outcomes are delayed and logged; exactly-once delivery is not
available through Telegram's send operation and the local database alone.

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/dashboard` | Overview | Stat cards, top matches, activity feed |
| `/jobs` | Discovery | Search, filter, sort job listings |
| `/jobs/[id]` | Detail | Match breakdown, risk analysis, skills |
| `/applications` | Tracker | Kanban board with 6 status columns |
| `/analytics` | Analytics | Funnel, charts, source performance |
| `/cv` | CV Manager | Upload, download and delete encrypted CV files |
| `/settings` | Settings | Profile, hunter config, privacy |

## Configuration

All config via environment variables. See `.env.example`.

### Key Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./work_bot_hunter.db` | Database connection |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token from @BotFather |
| `SECRET_KEY` | `change-me` | JWT signing key |
| `SCRAPE_INTERVAL_MINUTES` | `60` | How often to scrape |
| `REQUEST_DELAY_SECONDS` | `2` | Delay between requests |
| `WEIGHT_SKILLS` | `0.30` | Skill match weight |
| `WEIGHT_EXPERIENCE` | `0.20` | Experience match weight |
| `RISK_BLOCK` | `70` | Risk score to block |
| `RISK_REVIEW` | `40` | Risk score to flag |

CV uploads are stored as files under `CV_STORAGE_PATH`. The application does
not encrypt those files itself; configure encrypted storage at the host or
volume layer if that is required by the deployment.

## Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration test (full pipeline)
python test_integration.py
```

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token to `.env` as `TELEGRAM_BOT_TOKEN`
3. Message your bot → `/start`
4. Set keywords: `/set_keywords python,django,react`
5. Jobs auto-delivered every 5 minutes

## Environment Variables

```bash
# Database (SQLite for local dev)
DATABASE_URL=sqlite+aiosqlite:///./work_bot_hunter.db

# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# Auth
SECRET_KEY=your-secret-key

# Scraping
SCRAPE_INTERVAL_MINUTES=60
REQUEST_DELAY_SECONDS=2
```

## License

Private — not for distribution.
