UV ?= uv
DOCKER_COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help install run run-prod worker beat lint format typecheck test coverage seed stress \
	migrate-upgrade migrate-revision docker-up-prod-monitoring docker-down mutation-test

help:
	@echo "Available targets:"
	@echo "  install                  Install/update dependencies (all groups)"
	@echo "  run                      Start Flask development server"
	@echo "  run-prod                 Start Gunicorn production server"
	@echo "  worker                   Start Celery worker"
	@echo "  beat                     Start Celery beat scheduler"
	@echo "  lint                     Run Ruff lint checks"
	@echo "  format                   Run Ruff formatter"
	@echo "  typecheck                Run ty type checks"
	@echo "  test                     Run pytest suite"
	@echo "  coverage                 Run pytest with coverage report"
	@echo "  seed                     Seed baseline database data"
	@echo "  stress                   Run stress/load test script"
	@echo "  migrate-upgrade          Apply Alembic migrations"
	@echo "  migrate-revision         Create Alembic migration (set MSG='message')"
	@echo "  docker-up-prod-monitoring  Start prod + monitoring compose profiles"
	@echo "  docker-down              Stop prod + monitoring compose profiles"
	@echo "  mutation-test            Run mutmut mutation testing"

install:
	$(UV) sync --all-groups

run:
	$(UV) run python app.py

run-prod:
	$(UV) run gunicorn --config gunicorn.conf.py app:app

worker:
	$(UV) run celery -A backend.celery_config worker --loglevel=info

beat:
	$(UV) run celery -A backend.celery_config beat --loglevel=info

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

typecheck:
	$(UV) run ty check app.py backend models tests migrations --respect-ignore-files --exclude frontend/static/vendor --exclude .venv --exclude blood-bank-ms --ignore unresolved-import --ignore unsupported-base --ignore not-iterable --ignore unresolved-attribute

test:
	$(UV) run pytest tests -q

coverage:
	$(UV) run pytest tests --cov=backend --cov=models --cov-report=term-missing

seed:
	$(UV) run python scripts/seed_db.py

stress:
	$(UV) run python scripts/stress_test.py

migrate-upgrade:
	$(UV) run alembic upgrade head

migrate-revision:
	$(UV) run alembic revision --autogenerate -m "$(or $(MSG),describe_change)"

docker-up-prod-monitoring:
	$(DOCKER_COMPOSE) --profile prod --profile monitoring up --build -d

docker-down:
	$(DOCKER_COMPOSE) --profile prod --profile monitoring down

mutation-test:
	$(UV) run mutmut run --paths-to-mutate backend/,models/ --runner "pytest tests/test_auth.py tests/test_validation.py"
	$(UV) run mutmut results
