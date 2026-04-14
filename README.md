# Hospital Operations System

Hospital Operations System is a full-stack, role-based web application for managing hospital operations with integrated Blood Bank Operations capabilities.

The platform includes two tightly integrated modules in one runtime:

- Hospital Operations module (appointments, doctor/patient/admin workflows, reports, exports, payments).
- Blood Bank Operations module (inventory, donor workflows, smart allocation, shortage alerts, audit trail).

Both modules share the same authentication core (session + JWT support) and are deployed together in one Docker stack.

## Table of Contents

- [Project Highlights](#project-highlights)
- [Architecture Overview](#architecture-overview)
- [RBAC and Access Control](#rbac-and-access-control)
- [Security Hardening and API Standards](#security-hardening-and-api-standards)
- [Observability and Request Tracing](#observability-and-request-tracing)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Environment Configuration](#environment-configuration)
- [Database Migrations (Alembic)](#database-migrations-alembic)
- [SMTP Setup (Required for Real Emails)](#smtp-setup-required-for-real-emails)
- [Run with Docker Compose (Recommended)](#run-with-docker-compose-recommended)
- [Monitoring Profile (Prometheus and Grafana)](#monitoring-profile-prometheus-and-grafana)
- [Manual Run (Equivalent to 4 Terminals)](#manual-run-equivalent-to-4-terminals)
- [Developer Commands (Makefile + uv)](#developer-commands-makefile--uv)
- [Usage Notes](#usage-notes)
- [API Documentation and Auth Endpoints](#api-documentation-and-auth-endpoints)
- [Blood Bank Module Details](#blood-bank-module-details)
- [Testing Both Modules](#testing-both-modules)
- [Verification and Health Checks](#verification-and-health-checks)
- [Troubleshooting](#troubleshooting)

## Project Highlights

- Role-based authentication/authorization for Admin, Doctor, Patient, and Blood Bank Staff.
- Password security hardened with Argon2 hashing on the `User` model (`set_password` / `check_password`).
- One-time demo-user password migration script (`scripts/migrate_passwords.py`) auto-invoked during startup seeding.
- JWT stateless auth added alongside session auth (`/api/token` and `/api/token/refresh`).
- Auth rate limiting enabled via Flask-Limiter (`10/min`, `50/hour` on login/token issue routes).
- Security headers middleware enabled via Flask-Talisman (HSTS/XFO/XCTO/CSP baseline).
- Pydantic v2 request schemas and reusable validation decorator for mutating API payloads.
- RFC 7807-style problem JSON helper for consistent error response structure.
- OpenAPI/Swagger UI via Flask-Smorest at `/api/openapi.json` and `/api/docs`.
- Structured JSON logging via `structlog` with per-request `X-Request-ID` propagation.
- Detailed dependency health endpoint at `/api/health` (database + cache probes).
- Prometheus exporter endpoint at `/metrics` plus custom booking business metrics.
- Monitoring profile in Docker Compose with pre-provisioned Prometheus + Grafana dashboard.
- Full Alembic migration scaffold and initial versioned schema revision.
- Application-level admin audit trail (`AuditLog`) with query endpoint at `/api/admin/audit-logs`.
- uv-native developer workflow with expanded Makefile commands for lint/format/type/test/migrate.
- Type-check workflow migrated to `ty` (Ruff + ty in dev dependency group).
- SQLite PRAGMA tuning (WAL, foreign keys ON, busy timeout) for better concurrent behavior.
- Appointment booking with conflict prevention and status workflow.
- Doctor Operations with departments, availability slots, profile metadata, and fixed consultation cost.
- Treatment history and CSV export (async via Celery task).
- Automated notifications:
	- Daily appointment reminders.
	- Monthly doctor activity reports.
- PDF generation support for reporting.
- Redis-backed caching and Celery broker/backend integration.
- Vue.js frontend served by Flask.
- Integrated Blood Bank Operations System under `/blood-bank`:
	- Donor registration and donation logging (whole blood + component split).
	- Smart compatibility-based allocation engine.
	- Critical shortage and predictive alert dashboard.
	- Full forensic audit trail with trigger-backed history.

## Architecture Overview

Runtime services and responsibilities:

- `web` (Flask app):
	- Serves API and frontend UI.
	- Initializes DB and seed roles/admin/departments plus blood-bank staff account.
	- Loads SMTP and other runtime configuration from `.env`.
	- Hosts the integrated blood-bank pages under `/blood-bank`.
- `redis`:
	- Message broker and result backend for Celery.
	- Cache backend for Flask-Caching.
- `celery-worker`:
	- Executes asynchronous jobs (emails, exports, etc.).
- `celery-beat`:
	- Triggers scheduled periodic tasks (daily reminders, monthly reports).

The Docker Compose setup replaces the classic 4-terminal local workflow with a single orchestrated stack.

## RBAC and Access Control

Application roles and capabilities:

- `admin`: full access to hospital module and blood-bank module.
- `doctor`: access to doctor workflows only.
- `patient`: access to patient workflows only.
- `blood_bank_staff`: access to blood-bank module pages and operations.

Blood bank authorization behavior:

- Blood bank module is mounted at `/blood-bank`.
- Access requires authentication and either `admin` or `blood_bank_staff` role.
- Unauthorized users are redirected back to the main HOS interface.

## Security Hardening and API Standards

This implementation now includes production-grade API hardening primitives:

- Password storage and verification:
	- Argon2 hashing through `User.set_password()` and `User.check_password()` in `models/database.py`.
	- Legacy/demo credentials are upgraded by `scripts/migrate_passwords.py`.
- Dual authentication modes:
	- Session auth remains for browser workflows.
	- JWT auth enables stateless API clients (mobile apps, Postman, service integrations).
- JWT token policy:
	- Access token expiry: 15 minutes.
	- Refresh token expiry: 7 days (HttpOnly refresh cookie).
- Request validation:
	- Pydantic v2 schemas in `backend/schemas.py`.
	- Shared `@validate(...)` decorator for consistent 422 validation behavior.
- Error contract:
	- RFC 7807-like `problem(...)` responses from `backend/errors.py`.
	- Global API error handlers in `app.py` for 404/403/422/unhandled exceptions.
- Abuse protection and headers:
	- Flask-Limiter rate limits on auth endpoints.
	- Flask-Talisman CSP and core browser security headers.

## Observability and Request Tracing

This implementation includes first-class observability primitives for production operations:

- Structured JSON logs:
	- `structlog` emits JSON events suitable for centralized log systems.
	- Request metadata (`path`, `method`, `status_code`, duration) is captured on every request.
- Request ID tracing:
	- Incoming `X-Request-ID` is accepted and echoed in every response.
	- A new UUID is generated when the header is not provided.
	- Problem JSON responses include `request_id` for fast correlation.
- Health probing:
	- `GET /api/health` runs dependency checks for database and cache.
	- Legacy `GET /health` remains available for backwards compatibility.
- Metrics:
	- `GET /metrics` exposes Prometheus metrics for HTTP traffic and runtime internals.
	- Custom metrics include:
		- `hos_appointment_booking_attempts_total{outcome=...}`
		- `hos_appointment_booking_duration_seconds{outcome=...}`

These metrics and logs are wired to the Docker monitoring profile described below.

## Tech Stack

- Backend: Flask, Flask-SQLAlchemy, Flask-Security-Too, Flask-Mail, Flask-Caching
- API hardening: Flask-JWT-Extended, Flask-Limiter, Flask-Talisman, Pydantic v2
- API docs: Flask-Smorest (OpenAPI + Swagger UI)
- Observability: structlog, prometheus-flask-exporter, prometheus-client
- Async & Scheduling: Celery, Redis
- Data: SQLite (default), SQLAlchemy ORM
- Schema migrations: Alembic
- Frontend: Vue.js + Bootstrap
- Blood Bank Engine: integrated SQL-heavy module (triggers, views, allocation logic)
- Reporting: PyMuPDF, Pandas
- Packaging: `pyproject.toml` + `uv.lock`
- Quality tooling: Ruff + ty
- Containerization: Docker + Docker Compose

## Repository Structure

- `app.py`: Flask app factory and main entrypoint.
- `backend/`: routes, tasks, celery config, schemas, errors, extensions.
- `models/`: database models and ORM definitions.
- `frontend/`: static assets and `index.html` template.
- `blood-bank-ms/`: integrated blood-bank domain logic, templates, seed/test scripts.
- `scripts/migrate_passwords.py`: one-time demo password re-hashing helper.
- `tests/`: pytest suite.
- `tests/factories.py`: factory_boy factories for model-heavy tests.
- `Dockerfile`: image build instructions.
- `docker-compose.yml`: multi-service orchestration.
- `migrations/`: Alembic environment and schema revisions.
- `monitoring/`: Prometheus config + Grafana provisioning and dashboards.
- `.env.example`: template for required environment variables.

## Environment Configuration

Create your runtime env file from the template:

### PowerShell

```powershell
Copy-Item .env.example .env
```

### Bash

```bash
cp .env.example .env
```

### Core variables in `.env`

```dotenv
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=true

SECRET_KEY=change-this-secret-key
JWT_SECRET_KEY=change-this-jwt-secret-key
SECURITY_PASSWORD_SALT=change-this-password-salt
BLOODBANK_SECRET_KEY=change-this-blood-bank-secret-key

SQLALCHEMY_DATABASE_URI=sqlite:///hospital.db
CACHE_TYPE=RedisCache
REDIS_URL=redis://redis:6379/0
CACHE_REDIS_URL=redis://redis:6379/0
BLOODBANK_DB_PATH=/app/instance/bloodbank.db

GUNICORN_WORKERS=3
GUNICORN_THREADS=2
GUNICORN_TIMEOUT=120
GUNICORN_LOG_LEVEL=info
LOG_LEVEL=INFO
METRICS_ENABLED=true

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin

SMTP_USERNAME=your-smtp-username@gmail.com
SMTP_PASSWORD=your-smtp-app-password
FROM_EMAIL=your-sender-email@gmail.com
```

If SMTP credentials are not configured, the app falls back to console logging for email payloads.

## Database Migrations (Alembic)

Alembic is configured in this repository with:

- `alembic.ini`
- `migrations/env.py`
- initial revision in `migrations/versions/*_initial_schema.py`

Common commands:

```powershell
# Apply all pending migrations
uv run alembic upgrade head

# Generate a new revision from model changes
uv run alembic revision --autogenerate -m "describe_change"
```

You can also use Make targets:

```powershell
make migrate-upgrade
make migrate-revision MSG="describe_change"
```

## SMTP Setup (Required for Real Emails)

The app expects the following `.env` keys:

- `SMTP_USERNAME`: your SMTP account username/email.
- `SMTP_PASSWORD`: SMTP password (for Gmail, use an App Password).
- `FROM_EMAIL`: sender email shown in outgoing messages.

For Gmail:

1. Enable 2-step verification on your Google account.
2. Generate an App Password.
3. Put your Gmail address in `SMTP_USERNAME`.
4. Put the generated App Password in `SMTP_PASSWORD`.
5. Put the sender address in `FROM_EMAIL`.

## Run with Docker Compose (Recommended)

The compose setup has profile-based runtimes and includes both HOS and Blood Bank modules in the same `web` service:

- `dev` profile: Flask dev server + live code mount.
- `prod` profile: Gunicorn + non-root runtime (with startup volume permission initialization).
- `monitoring` profile: Prometheus + Grafana with pre-provisioned dashboard.

### Production Profile (Recommended)

1. Build and start production with monitoring:

```powershell
docker compose --profile prod --profile monitoring up --build -d
```

2. Check service status:

```powershell
docker compose ps
```

3. Stream all logs:

```powershell
docker compose --profile prod logs -f
```

4. Open the app:

- URL: `http://localhost:5000`
- Health endpoint: `http://localhost:5000/api/health`
- Metrics endpoint: `http://localhost:5000/metrics`

5. Stop stack:

```powershell
docker compose --profile prod --profile monitoring down
```

6. Stop and remove volumes (full reset):

```powershell
docker compose --profile prod --profile monitoring down -v
```

### Development Profile

```powershell
docker compose --profile dev up --build -d
```

This starts `web-dev`, `celery-worker-dev`, and `celery-beat-dev` (plus Redis).

## Monitoring Profile (Prometheus and Grafana)

When running with `--profile monitoring`, the stack adds:

- Prometheus at `http://localhost:9090`
- Grafana at `http://localhost:3000`

Default Grafana credentials are read from `.env`:

- `GRAFANA_ADMIN_USER` (default `admin`)
- `GRAFANA_ADMIN_PASSWORD` (default `admin`)

Provisioned assets:

- Prometheus scrape config: `monitoring/prometheus/prometheus.yml`
- Grafana datasource provisioning: `monitoring/grafana/provisioning/datasources/datasource.yml`
- Grafana dashboard provisioning: `monitoring/grafana/provisioning/dashboards/dashboards.yml`
- Dashboard JSON: `monitoring/grafana/dashboards/hospital-overview.json`

### Hardening Details in Container Runtime

- Production web service runs on Gunicorn (`gunicorn.conf.py`).
- Entrypoint runs as root only long enough to initialize volume permissions.
- Application process then drops to unprivileged UID/GID (`10001:10001`).
- PID 1 uses `tini` for correct signal handling and child reaping.

### Useful Docker Operations

- Rebuild without cache:

```powershell
docker compose build --no-cache
```

- Watch only web logs:

```powershell
docker compose --profile prod logs -f web
```

- Open shell in web container:

```powershell
docker compose --profile prod exec web sh
```

- Inspect Redis quickly:

```powershell
docker compose exec redis redis-cli ping
```

## Manual Run (Equivalent to 4 Terminals)

If you prefer non-Docker local execution, this is the equivalent setup.

1. Install dependencies:

```powershell
uv sync
```

2. Terminal A: Redis

```powershell
docker run --name hos-redis -p 6379:6379 -d redis:7-alpine
```

3. Terminal B: Flask web app

```powershell
uv run python app.py
```

4. Terminal C: Celery worker

```powershell
uv run celery -A backend.celery_config worker --loglevel=info
```

5. Terminal D: Celery beat

```powershell
uv run celery -A backend.celery_config beat --loglevel=info
```

Docker Compose automates all of the above into one command.

After login, authorized users can enter the blood bank module directly at `http://localhost:5000/blood-bank`.

## Developer Commands (Makefile + uv)

Key targets from `Makefile`:

```powershell
make install
make run
make run-prod
make worker
make beat
make lint
make format
make typecheck
make test
make coverage
make seed
make stress
make migrate-upgrade
make migrate-revision MSG="describe_change"
make docker-up-prod-monitoring
make docker-down
```

All targets use `uv` for consistent dependency/environment execution.

## Usage Notes

- Default seeded admin credentials:
	- Username: `admin`
	- Password: `admin`
- Default seeded blood bank staff credentials:
	- Username: `bbstaff`
	- Password: `bbstaff`
- In production, change default credentials and all security secrets.
- SQLite data is persisted in Docker volume `hos_instance_data`.
- Export CSV files are persisted in Docker volume `hos_exports_data`.

## API Documentation and Auth Endpoints

OpenAPI and docs endpoints:

- `GET /api/openapi.json`: machine-readable OpenAPI spec.
- `GET /api/docs`: interactive Swagger UI.
- `GET /api/meta/ping`: docs-metadata health endpoint.

Session auth endpoints:

- `POST /api/login`
- `POST /api/logout`
- `POST /api/register`
- `GET /api/current-user`

JWT auth endpoints:

- `POST /api/token`: returns short-lived access token and sets refresh cookie.
- `POST /api/token/refresh`: issues a new access token from the refresh cookie.

Operational/admin observability endpoint:

- `GET /api/admin/audit-logs`: list audit entries for admin mutations with filters.

Example token issue request:

```json
{
	"username": "admin",
	"password": "admin"
}
```

Error responses follow a problem-style JSON shape:

```json
{
	"type": "https://hospital-operations-system.example/errors/validation-error",
	"title": "Validation Error",
	"status": 422,
	"detail": "Request validation failed"
}
```

## Blood Bank Module Details

Integrated blood bank pages:

- `GET /blood-bank/`: dashboard with inventory and predictive alerts.
- `POST /blood-bank/allocate_all`: run smart allocation engine.
- `GET/POST /blood-bank/donor`: donor registration, donation logging, loyalty view.
- `GET/POST /blood-bank/hospital`: recipient/hospital Operations and blood requests.
- `GET /blood-bank/audit`: forensic audit trail view.

Data and persistence:

- Blood bank database path is configured via `BLOODBANK_DB_PATH`.
- Recommended path in Docker: `/app/instance/bloodbank.db`.
- Database is initialized automatically on first blood-bank access.

## Testing Both Modules

Primary quality gate (coverage enforced):

```powershell
uv run pytest tests -q
```

The root test suite enforces:

- `--cov=backend --cov=models`
- terminal missing-line report
- fail-under threshold: 85%

Targeted test categories added in this hardening phase:

- `tests/test_security.py`:
	- Argon2 password storage checks
	- JWT issue/refresh flows
	- auth rate limiting and access-control assertions
- `tests/test_validation.py`:
	- 422 validation behavior for mutating endpoints
	- SQL injection-style and XSS payload rejection checks
- `tests/test_concurrency.py`:
	- concurrent booking race test (single-slot contention)
- `tests/test_blood_bank_logic.py`:
	- Hypothesis property-based donation behavior test
- `tests/test_celery_tasks.py`:
	- eager-mode Celery task execution and email fallback coverage
- `tests/test_pdf_reports.py`:
	- PDF binary validation and data-isolation checks
- `tests/test_api_docs.py`:
	- OpenAPI JSON and Swagger UI availability checks
- `tests/test_coverage_expansion.py`:
	- additional integration coverage across admin/doctor/patient branches

Run integrated blood-bank RBAC/route tests from HOS suite:

```powershell
uv run pytest tests/test_blood_bank_integration.py -q
```

Run original blood-bank module tests:

```powershell
Push-Location blood-bank-ms
uv run pytest tests/test_logic.py -q
Pop-Location
```

Factory-based test data helper:

- `tests/factories.py` uses `factory_boy` for model factories.

Mutation testing (optional but recommended):

```powershell
make mutation-test
```

Seed blood bank demo data (optional, standalone verification utility):

```powershell
Push-Location blood-bank-ms
uv run python seed_demo.py
Pop-Location
```

## Verification and Health Checks

After starting containers:

1. Check containers are healthy:

```powershell
docker compose ps
```

2. Verify web health endpoint:

```powershell
curl http://localhost:5000/api/health
```

3. Verify metrics endpoint:

```powershell
curl http://localhost:5000/metrics
```

4. Verify Redis connectivity:

```powershell
docker compose exec redis redis-cli ping
```

5. Verify Celery worker is connected:

```powershell
docker compose --profile prod exec celery-worker celery -A backend.celery_config inspect ping
```

6. Verify monitoring services:

```powershell
curl http://localhost:9090/-/ready
curl http://localhost:3000/api/health
```

Expected output includes `pong` from at least one worker.

## Troubleshooting

- `web` keeps restarting:
	- Check logs: `docker compose --profile prod logs -f web`
	- Ensure `.env` exists and has valid values.
- No emails received:
	- Confirm `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL` in `.env`.
	- Gmail requires App Password, not regular account password.
- Celery not processing tasks:
	- Ensure Redis is healthy: `docker compose ps` and `docker compose exec redis redis-cli ping`.
	- Check worker logs: `docker compose --profile prod logs -f celery-worker`.
- Want a clean reset:
	- `docker compose --profile prod down -v`
	- `docker compose --profile prod up --build -d`