# Power PTO

Employee time-off tracking system built for the Warp product take-home assessment. Supports flexible policies (unlimited and accrual-based), ledger-first balance tracking, approval workflows, and full audit trails.

## Tech Stack

**Backend:** Python 3.13+, FastAPI, PostgreSQL, SQLModel, Alembic

**Frontend:** TypeScript, React, Vite, shadcn/ui (Radix + Tailwind), TanStack Query

**Infra:** Docker, Docker Compose, Make, GitHub Actions CI

## Project Structure

```
backend/    — FastAPI application, migrations, and tests
frontend/   — React/Vite application
docs/       — Product requirements and technical design
```

## How to Run Locally

**Prerequisites:** Docker, Docker Compose, Make

```bash
# Start all services (db, api, worker, frontend)
make dev

# Stop all services
make down

# Tail logs
make logs

# Run backend tests
make test

# Run linter
make lint
```

> Docker and Make setup is coming in a subsequent PR.

## Documentation

- [Product Requirements](docs/prd.md)
- [Technical Design](docs/tdd.md)
