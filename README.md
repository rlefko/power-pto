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

**Prerequisites:** Docker, Docker Compose, Make

```bash
# Build and start all services (db, api, frontend)
make up

# In another terminal, run database migrations (required on first start)
make migrate
```

Once running:

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

## Make Commands

| Command | Description |
|---------|-------------|
| `make up` | Start all services in foreground |
| `make up-d` | Start all services detached |
| `make down` | Stop all services |
| `make build` | Build Docker images |
| `make clean` | Stop services, remove volumes and local images |
| `make migrate` | Run Alembic database migrations |
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
