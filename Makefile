.PHONY: up up-d build clean down logs api-shell migrate test lint fe

up:
	docker compose up

up-d:
	docker compose up -d

build:
	docker compose build

clean:
	docker compose down -v --rmi local

down:
	docker compose down

logs:
	docker compose logs -f

api-shell:
	docker compose exec api bash

migrate:
	docker compose exec api alembic upgrade head

test:
	docker compose exec api pytest tests/ -v

lint:
	docker compose exec api ruff check .
	docker compose exec api ruff format --check .
	docker compose exec api mypy app/ tests/
	cd frontend && yarn lint
	cd frontend && yarn format:check

fe:
	cd frontend && yarn dev
