# Power PTO

[![CI](https://github.com/rlefko/power-pto/actions/workflows/ci.yml/badge.svg)](https://github.com/rlefko/power-pto/actions/workflows/ci.yml)
[![CodeQL](https://github.com/rlefko/power-pto/actions/workflows/codeql.yml/badge.svg)](https://github.com/rlefko/power-pto/actions/workflows/codeql.yml)

Employee time-off tracking system built for the Warp product take-home assessment. Supports flexible policies (unlimited and accrual-based), ledger-first balance tracking, approval workflows, and full audit trails.

## Tech Stack

**Backend:** Python 3.13+, FastAPI, PostgreSQL 17, SQLModel, Alembic, Pydantic

**Frontend:** TypeScript, React 19, Vite, shadcn/ui (Radix + Tailwind), TanStack Query

**Infra:** Docker, Docker Compose, Make, GitHub Actions CI, pre-commit hooks

**Code Quality:** ruff, ty, ESLint, Prettier

## Project Structure

```
backend/     — FastAPI application, Alembic migrations, and tests
frontend/    — React/Vite single-page application
docs/        — Product requirements, technical design, and architecture
```

## Getting Started

### One-Command Setup

The setup script installs all prerequisites (Docker, Node.js, yarn, GitHub CLI, pre-commit), builds the Docker images, runs migrations, and seeds demo data:

```bash
make setup
```

Once complete, the app is running at the URLs below. No other steps needed.

### Manual Setup

If you already have Docker, Docker Compose, Make, and Node.js/yarn installed:

```bash
# Clone and enter the repo
git clone https://github.com/rlefko/power-pto.git
cd power-pto

# Install pre-commit hooks
pre-commit install

# Install frontend dependencies (needed for linting)
cd frontend && yarn install && cd ..

# Build and start all services (db, api, frontend)
make up

# In another terminal, run migrations and seed demo data
make migrate
make seed
```

### Service URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |

To also start the background accrual worker:

```bash
docker compose --profile worker up
```

## Seed Data

`make seed` populates the database with demo data for development:

- **4 employees:** Alice Johnson, Bob Smith, Carol Williams, Dave Brown
- **4 policies:** standard-pto (accrual), unlimited-vacation, sick-leave (accrual), hourly-pto (hours-worked)
- **6 holidays** for 2026
- **Policy assignments** linking employees to policies
- **Balance adjustments** (10-day accrual grants)
- **A pending time-off request** from Bob Smith (2 days of standard PTO)

The seed script is idempotent and can be re-run after `make clean` to reset data.

## Make Commands

| Command | Description |
|---------|-------------|
| `make setup` | One-command dev environment setup (installs prerequisites, builds, migrates, seeds) |
| `make up` | Start all services in foreground |
| `make up-d` | Start all services detached |
| `make down` | Stop all services |
| `make build` | Build Docker images |
| `make clean` | Stop services, remove volumes and local images |
| `make migrate` | Run Alembic database migrations |
| `make seed` | Seed the database with demo data |
| `make test` | Run backend tests |
| `make test-cov` | Run backend tests with coverage report |
| `make lint` | Run all linters (ruff, ty, ESLint, Prettier) |
| `make logs` | Tail service logs |
| `make api-shell` | Open a shell in the API container |
| `make fe` | Run frontend dev server standalone (outside Docker) |

### Running a Single Test

```bash
docker compose exec api uv run pytest tests/path/to/test_file.py::test_function_name -v
```

## Documentation

- [Product Requirements](docs/prd.md)
- [Technical Design](docs/tdd.md)
- [Architecture](docs/architecture.md)
- [API Reference](docs/api.md)
- [Data Model](docs/data-model.md)
- [Deployment Plan](docs/deployment.md)
