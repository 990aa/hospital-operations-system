# Hospital Management System

Hospital Management System is a full-stack, role-based web application for managing hospital operations with integrated Blood Bank Management capabilities.

The platform includes two tightly integrated modules in one runtime:

- Hospital Management module (appointments, doctor/patient/admin workflows, reports, exports, payments).
- Blood Bank Management module (inventory, donor workflows, smart allocation, shortage alerts, audit trail).

Both modules share the same authentication/session layer and are deployed together in one Docker stack.

## Table of Contents

- [Project Highlights](#project-highlights)
- [Architecture Overview](#architecture-overview)
- [RBAC and Access Control](#rbac-and-access-control)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Environment Configuration](#environment-configuration)
- [SMTP Setup (Required for Real Emails)](#smtp-setup-required-for-real-emails)
- [Run with Docker Compose (Recommended)](#run-with-docker-compose-recommended)
- [Manual Run (Equivalent to 4 Terminals)](#manual-run-equivalent-to-4-terminals)
- [Usage Notes](#usage-notes)
- [Blood Bank Module Details](#blood-bank-module-details)
- [Testing Both Modules](#testing-both-modules)
- [Verification and Health Checks](#verification-and-health-checks)
- [Troubleshooting](#troubleshooting)

## Project Highlights

- Role-based authentication/authorization for Admin, Doctor, Patient, and Blood Bank Staff.
- Appointment booking with conflict prevention and status workflow.
- Doctor management with departments, availability slots, profile metadata, and fixed consultation cost.
- Treatment history and CSV export (async via Celery task).
- Automated notifications:
	- Daily appointment reminders.
	- Monthly doctor activity reports.
- PDF generation support for reporting.
- Redis-backed caching and Celery broker/backend integration.
- Vue.js frontend served by Flask.
- Integrated Blood Bank Management System under `/blood-bank`:
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
- Unauthorized users are redirected back to the main HMS interface.

## Tech Stack

- Backend: Flask, Flask-SQLAlchemy, Flask-Security-Too, Flask-Mail, Flask-Caching
- Async & Scheduling: Celery, Redis
- Data: SQLite (default), SQLAlchemy ORM
- Frontend: Vue.js + Bootstrap
- Blood Bank Engine: integrated SQL-heavy module (triggers, views, allocation logic)
- Reporting: PyMuPDF, Pandas
- Packaging: `requirements.txt` generated from `pyproject.toml`
- Containerization: Docker + Docker Compose

## Repository Structure

- `app.py`: Flask app factory and main entrypoint.
- `backend/`: routes, tasks, celery config, validators, extensions.
- `models/`: database models and ORM definitions.
- `frontend/`: static assets and `index.html` template.
- `blood-bank-ms/`: integrated blood-bank domain logic, templates, seed/test scripts.
- `tests/`: pytest suite.
- `Dockerfile`: image build instructions.
- `docker-compose.yml`: multi-service orchestration.
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
SECURITY_PASSWORD_SALT=change-this-password-salt

SQLALCHEMY_DATABASE_URI=sqlite:///hospital.db
CACHE_TYPE=RedisCache
REDIS_URL=redis://redis:6379/0
CACHE_REDIS_URL=redis://redis:6379/0
BLOODBANK_DB_PATH=/app/instance/bloodbank.db

GUNICORN_WORKERS=3
GUNICORN_THREADS=2
GUNICORN_TIMEOUT=120
GUNICORN_LOG_LEVEL=info

SMTP_USERNAME=your-smtp-username@gmail.com
SMTP_PASSWORD=your-smtp-app-password
FROM_EMAIL=your-sender-email@gmail.com
```

If SMTP credentials are not configured, the app falls back to console logging for email payloads.

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

The compose setup has profile-based runtimes and includes both HMS and Blood Bank modules in the same `web` service:

- `dev` profile: Flask dev server + live code mount.
- `prod` profile: Gunicorn + non-root runtime (with startup volume permission initialization).

### Production Profile (Recommended)

1. Build and start everything:

```powershell
docker compose --profile prod up --build -d
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
- Health endpoint: `http://localhost:5000/health`

5. Stop stack:

```powershell
docker compose --profile prod down
```

6. Stop and remove volumes (full reset):

```powershell
docker compose --profile prod down -v
```

### Development Profile

```powershell
docker compose --profile dev up --build -d
```

This starts `web-dev`, `celery-worker-dev`, and `celery-beat-dev` (plus Redis).

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
docker run --name hms-redis -p 6379:6379 -d redis:7-alpine
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

## Usage Notes

- Default seeded admin credentials:
	- Username: `admin`
	- Password: `admin`
- Default seeded blood bank staff credentials:
	- Username: `bbstaff`
	- Password: `bbstaff`
- In production, change default credentials and all security secrets.
- SQLite data is persisted in Docker volume `hms_instance_data`.
- Export CSV files are persisted in Docker volume `hms_exports_data`.

## Blood Bank Module Details

Integrated blood bank pages:

- `GET /blood-bank/`: dashboard with inventory and predictive alerts.
- `POST /blood-bank/allocate_all`: run smart allocation engine.
- `GET/POST /blood-bank/donor`: donor registration, donation logging, loyalty view.
- `GET/POST /blood-bank/hospital`: recipient/hospital management and blood requests.
- `GET /blood-bank/audit`: forensic audit trail view.

Data and persistence:

- Blood bank database path is configured via `BLOODBANK_DB_PATH`.
- Recommended path in Docker: `/app/instance/bloodbank.db`.
- Database is initialized automatically on first blood-bank access.

## Testing Both Modules

Run HMS tests:

```powershell
uv run pytest tests -q
```

Run integrated blood-bank RBAC/route tests from HMS suite:

```powershell
uv run pytest tests/test_blood_bank_integration.py -q
```

Run original blood-bank module tests:

```powershell
Push-Location blood-bank-ms
uv run pytest tests/test_logic.py -q
Pop-Location
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
curl http://localhost:5000/health
```

3. Verify Redis connectivity:

```powershell
docker compose exec redis redis-cli ping
```

4. Verify Celery worker is connected:

```powershell
docker compose --profile prod exec celery-worker celery -A backend.celery_config inspect ping
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