.PHONY: dev down logs api-shell migrate test lint fe

dev:
	docker compose up --build -d

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

fe:
	cd frontend && yarn dev
