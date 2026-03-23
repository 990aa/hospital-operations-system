# Hospital Management System

Hospital Management System is a full-stack, role-based web application for managing hospital operations across three user roles: Admin, Doctor, and Patient.

It includes appointment lifecycle management, doctor scheduling metadata, patient records, payment tracking, export workflows, PDF reporting, and background automation with Celery + Redis.

## Table of Contents

- [Project Highlights](#project-highlights)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Environment Configuration](#environment-configuration)
- [SMTP Setup (Required for Real Emails)](#smtp-setup-required-for-real-emails)
- [Run with Docker Compose (Recommended)](#run-with-docker-compose-recommended)
- [Manual Run (Equivalent to 4 Terminals)](#manual-run-equivalent-to-4-terminals)
- [Usage Notes](#usage-notes)
- [Verification and Health Checks](#verification-and-health-checks)
- [Troubleshooting](#troubleshooting)

## Project Highlights

- Role-based authentication/authorization for Admin, Doctor, Patient.
- Appointment booking with conflict prevention and status workflow.
- Doctor management with departments, availability slots, profile metadata, and fixed consultation cost.
- Treatment history and CSV export (async via Celery task).
- Automated notifications:
	- Daily appointment reminders.
	- Monthly doctor activity reports.
- PDF generation support for reporting.
- Redis-backed caching and Celery broker/backend integration.
- Vue.js frontend served by Flask.

## Architecture Overview

Runtime services and responsibilities:

- `web` (Flask app):
	- Serves API and frontend UI.
	- Initializes DB and seed roles/admin/departments on startup.
	- Loads SMTP and other runtime configuration from `.env`.
- `redis`:
	- Message broker and result backend for Celery.
	- Cache backend for Flask-Caching.
- `celery-worker`:
	- Executes asynchronous jobs (emails, exports, etc.).
- `celery-beat`:
	- Triggers scheduled periodic tasks (daily reminders, monthly reports).

The Docker Compose setup replaces the classic 4-terminal local workflow with a single orchestrated stack.

## Tech Stack

- Backend: Flask, Flask-SQLAlchemy, Flask-Security-Too, Flask-Mail, Flask-Caching
- Async & Scheduling: Celery, Redis
- Data: SQLite (default), SQLAlchemy ORM
- Frontend: Vue.js + Bootstrap
- Reporting: PyMuPDF, Pandas
- Packaging: `requirements.txt` generated from `pyproject.toml`
- Containerization: Docker + Docker Compose

## Repository Structure

- `app.py`: Flask app factory and main entrypoint.
- `backend/`: routes, tasks, celery config, validators, extensions.
- `models/`: database models and ORM definitions.
- `frontend/`: static assets and `index.html` template.
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

This starts all required services: Flask app, Redis, Celery worker, and Celery beat.

1. Build and start everything:

```powershell
docker compose up --build -d
```

2. Check service status:

```powershell
docker compose ps
```

3. Stream all logs:

```powershell
docker compose logs -f
```

4. Open the app:

- URL: `http://localhost:5000`
- Health endpoint: `http://localhost:5000/health`

5. Stop stack:

```powershell
docker compose down
```

6. Stop and remove volumes (full reset):

```powershell
docker compose down -v
```

### Useful Docker Operations

- Rebuild without cache:

```powershell
docker compose build --no-cache
```

- Watch only web logs:

```powershell
docker compose logs -f web
```

- Open shell in web container:

```powershell
docker compose exec web sh
```

- Inspect Redis quickly:

```powershell
docker compose exec redis redis-cli ping
```

## Manual Run (Equivalent to 4 Terminals)

If you prefer non-Docker local execution, this is the equivalent setup.

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

2. Terminal A: Redis

```powershell
docker run --name hms-redis -p 6379:6379 -d redis:7-alpine
```

3. Terminal B: Flask web app

```powershell
python app.py
```

4. Terminal C: Celery worker

```powershell
celery -A backend.celery_config worker --loglevel=info
```

5. Terminal D: Celery beat

```powershell
celery -A backend.celery_config beat --loglevel=info
```

Docker Compose automates all of the above into one command.

## Usage Notes

- Default seeded admin credentials:
	- Username: `admin`
	- Password: `admin`
- In production, change default credentials and all security secrets.
- SQLite data is persisted in Docker volume `hms_instance_data`.
- Export CSV files are persisted in Docker volume `hms_exports_data`.

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
docker compose exec celery-worker celery -A backend.celery_config inspect ping
```

Expected output includes `pong` from at least one worker.

## Troubleshooting

- `web` keeps restarting:
	- Check logs: `docker compose logs -f web`
	- Ensure `.env` exists and has valid values.
- No emails received:
	- Confirm `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL` in `.env`.
	- Gmail requires App Password, not regular account password.
- Celery not processing tasks:
	- Ensure Redis is healthy: `docker compose ps` and `docker compose exec redis redis-cli ping`.
	- Check worker logs: `docker compose logs -f celery-worker`.
- Want a clean reset:
	- `docker compose down -v`
	- `docker compose up --build -d`