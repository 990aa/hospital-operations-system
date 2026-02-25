# Hospital Management System — Implementation Reference

This document is a personal deep-dive reference for the entire application. It covers every major component, how it was built, why certain design decisions were made, and how all pieces interconnect. Use this if you are asked a question about any part of the app.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Backend — Flask App Factory and Startup](#2-backend--flask-app-factory-and-startup)
3. [Models and Database Design](#3-models-and-database-design)
4. [SQLAlchemy and SQLite in Detail](#4-sqlalchemy-and-sqlite-in-detail)
5. [Flask-Security — Auth and RBAC](#5-flask-security--auth-and-rbac)
6. [Blueprint-Based Routing](#6-blueprint-based-routing)
7. [Admin Routes — Detailed Walkthrough](#7-admin-routes--detailed-walkthrough)
8. [Doctor Routes — Detailed Walkthrough](#8-doctor-routes--detailed-walkthrough)
9. [Patient Routes — Detailed Walkthrough](#9-patient-routes--detailed-walkthrough)
10. [Auth Routes](#10-auth-routes)
11. [Redis — Caching in Detail](#11-redis--caching-in-detail)
12. [Celery — Task Queue and Scheduling](#12-celery--task-queue-and-scheduling)
13. [Background Tasks — Each Task Explained](#13-background-tasks--each-task-explained)
14. [PDF Report Generation (ReportLab)](#14-pdf-report-generation-reportlab)
15. [Validators and Input Handling](#15-validators-and-input-handling)
16. [Frontend Architecture (Vue.js 3)](#16-frontend-architecture-vuejs-3)
17. [Vue.js — Data Model and State](#17-vuejs--data-model-and-state)
18. [Vue.js — Methods Reference](#18-vuejs--methods-reference)
19. [Vue.js — Template Sections](#19-vuejs--template-sections)
20. [Full Request-Response Flow Examples](#20-full-request-response-flow-examples)
21. [Error Handling Strategy](#21-error-handling-strategy)
22. [Test Infrastructure (Overview)](#22-test-infrastructure-overview)

---

## 1. Project Structure

```
hospital-management-system/
├── app.py                    # Flask application factory + app entry point
├── pyproject.toml            # uv/pip package configuration
├── er_diagram.mmd            # Mermaid entity-relationship diagram
├── report.md                 # Academic report
├── implementation-reference.md  # This file
├── backend/
│   ├── __init__.py
│   ├── celery_config.py      # Celery Beat schedule + Windows pool fix
│   ├── ensure_vendors.py     # Downloads front-end vendor assets on first run
│   ├── extensions.py         # Shared Flask extension singletons (Cache)
│   ├── pdf_reports.py        # ReportLab PDF generation helpers
│   ├── tasks.py              # All Celery task definitions
│   ├── validators.py         # Input validation decorators
│   └── routes/
│       ├── __init__.py
│       ├── auth_routes.py    # Login, logout, register
│       ├── admin_routes.py   # Admin CRUD and stats
│       ├── doctor_routes.py  # Doctor appointments and records
│       └── patient_routes.py # Patient booking, history, export
├── models/
│   └── database.py           # All SQLAlchemy model classes
├── frontend/
│   ├── index.html            # The entire SPA HTML
│   └── static/
│       ├── css/style.css
│       ├── js/app.js         # All Vue.js logic
│       └── vendor/           # Auto-downloaded on first startup by ensure_vendors.py
│           ├── css/          # Bootstrap CSS, Bootstrap Icons CSS
│           │   └── fonts/    # Bootstrap icon fonts (woff/woff2)
│           └── js/           # Bootstrap JS, Vue 3, Plotly
├── tests/
│   ├── conftest.py           # Shared fixtures
│   ├── test_admin.py
│   ├── test_auth.py
│   ├── test_appointments.py
│   ├── test_cache.py
│   ├── test_celery.py
│   ├── test_flow.py
│   └── test_routes_rendering.py
├── exports/                  # Generated CSV export files live here
└── scripts/
    └── stress_test.py        # Concurrency stress test
```

**Key principle:** Each backend domain (admin, doctor, patient, auth) has its own blueprint file. The Vue.js SPA is a single file (`index.html`) served statically. All API calls go to `/api/...` endpoints.

> **Vendor assets**: Front-end libraries (Bootstrap, Vue, Plotly) are **not** committed to the repository. Instead, `backend/ensure_vendors.py` downloads them on first startup and caches them under `frontend/static/vendor/`. This keeps the repository lightweight while still serving everything locally.

---

## 2. Backend — Flask App Factory and Startup

### `app.py` — The Factory Function

The entire Flask application is created inside `create_app(test_config=None)`. This is the **application factory pattern**.

#### `HospitalApp` — typed Flask subclass

A thin subclass of `Flask` is defined in `app.py`:

```python
class HospitalApp(Flask):
    user_datastore: SQLAlchemyUserDatastore
```

This adds a typed `user_datastore` attribute so that type checkers (e.g. `ty`) can verify accesses like `current_app.user_datastore.find_user(...)` without emitting `unknown-attribute` errors.

#### `backend/extensions.py` — shared extension singletons

Flask extensions that need to be imported by multiple blueprint files (currently `flask_caching.Cache`) are instantiated once in `backend/extensions.py`:

```python
from flask_caching import Cache
cache: Cache = Cache()
```

All route files import `from backend.extensions import cache` and call `cache.get/set/delete()` directly.  `cache.init_app(app)` is called inside `create_app()`. This avoids circular imports that would occur if cache were instantiated inside `app.py` and imported from there.

#### Why use a factory?

- Tests can call `create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})` and get a fresh isolated instance without polluting the real database.
- Configuration can be injected at creation time.

#### What `create_app` does step by step:

1. **Calls `ensure_vendors()`** at module import time (before the factory runs) to download any missing front-end vendor assets to `frontend/static/vendor/`.
2. **Instantiates Flask** using `HospitalApp` (a typed subclass) with `static_folder='frontend/static'` and `template_folder='frontend'`.
3. **Loads configuration** — default values are set in code (Redis URLs, SQLite path, mail settings). If `test_config` is passed, those values override the defaults.
4. **Initialises extensions** — `db.init_app(app)`, `mail.init_app(app)`, `cache.init_app(app)`, `security = Security(app, user_datastore)` (Flask-Security).
5. **Initialises Celery** — calls `make_celery(app)` from `backend/celery_config.py`.
6. **Registers blueprints** — all four blueprints (`auth_bp`, `admin_bp`, `doctor_bp`, `patient_bp`) are registered with `app.register_blueprint(bp, url_prefix='/api')`.
7. **Calls `create_initial_data(app)`** inside a `with app.app_context()` block to seed the database.
8. **Registers the frontend route** — `GET /` serves `index.html`.
9. **Returns the configured app**.

#### `create_initial_data(app)`

This function runs once on startup inside the app context:

- Creates all tables: `db.create_all()` is idempotent — it only creates tables that don't yet exist.
- Uses SQLite's `PRAGMA table_info(...)` to check whether new columns exist, then runs `ALTER TABLE ... ADD COLUMN` for any that are missing. This is the additive migration strategy (no migration framework is needed for the project's scale).
- Creates the admin user if not already present (`user_datastore.find_user(email=...)`).
- Creates default departments (General Medicine, Cardiology, Neurology, Orthopedics) if the Department table is empty.
- Ensures `admin`, `doctor`, and `patient` roles exist.

#### Starting the Application

With `uv` (configured in `pyproject.toml`):

```bash
# Start Flask
uv run flask run

# Start Celery worker
uv run celery -A backend.tasks.celery_app worker --loglevel=info

# Start Celery Beat (scheduler)
uv run celery -A backend.tasks.celery_app beat --loglevel=info
```

Redis must be running locally on port 6379 for Celery and caching to function.

---

## 3. Models and Database Design

All models are in `models/database.py`.

### `User` Model

Inherits from both SQLAlchemy's `db.Model` and Flask-Security's `fsqla.FsUserMixin`. Provides:

- `id`, `email`, `password`, `active`, `fs_uniquifier` (Flask-Security internal token field)
- `roles` — many-to-many with `Role` via `roles_users` join table
- `name`, `phone` — extra custom fields

The `FsUserMixin` brings all Flask-Security-required columns. The `roles_users` table is a plain `db.Table` association table (no model class needed).

### `Role` Model

Inherits from `fsqla.FsRoleMixin`. Contains `id`, `name`, `description`. Three roles exist: `admin`, `doctor`, `patient`.

### `Department` Model

Simple model: `id`, `name` (unique), `description`. Used to categorise doctors into specialisations.

### `Doctor` Model

Profile extension for doctor users:

- `id`, `user_id` (FK → User), `department_id` (FK → Department)
- `specialization` — text field for specific expertise
- `bio` — longer description for patient-facing display
- `experience_years` — integer
- `availability_days` — comma-separated string, e.g. `"Mon,Tue,Wed"`. Parsed in Python at query time.
- `availability_start`, `availability_end` — strings like `"09:00"`, `"17:00"`
- `slot_minutes` — integer, e.g. 30 for 30-minute slots
- `is_available` — boolean flag to globally enable/disable the doctor
- `notification_pref` — boolean, whether to send monthly email reports
- `appointment_cost` — float, fixed consultation fee in ₹ set by admin (default 500.0)
- Relationships: `user`, `department`, `appointments`

### `Patient` Model

Profile extension for patient users:

- `id`, `user_id` (FK → User)
- `date_of_birth`, `gender`, `address`, `blood_group`, `emergency_contact`
- `medical_history` — text blob accumulating short summaries appended each time a treatment is completed (read-only to patients; managed by clinical workflow)
- `notification_pref` — always `"email"`; all notifications are sent via email only (SMS has been removed)
- Relationships: `user`, `appointments`, `export_jobs`

### `Appointment` Model

Core scheduling entity:

- `id`, `patient_id` (FK → Patient), `doctor_id` (FK → Doctor)
- `date` — Python date object; stored as SQLite DATE type
- `time` — string in HH:MM format
- `status` — string enum: `"Booked"`, `"Completed"`, `"Cancelled"`
- `notes` — optional patient-provided notes at booking time
- `is_follow_up` — boolean
- `follow_up_source_appointment_id` — self-referencing FK for traceability
- Relationships: `patient`, `doctor`, `treatment`, `payments`
- Unique index: `UniqueConstraint('doctor_id', 'date', 'time')` — database-level double-booking prevention

### `Treatment` Model

One-to-one with Appointment (only for completed appointments):

- `id`, `appointment_id` (FK → Appointment, unique)
- `diagnosis`, `prescription`, `notes` — text fields
- `created_at` — timestamp

### `Payment` Model

Financial ledger entries:

- `id`, `appointment_id` (FK → Appointment), `patient_id` (FK → Patient)
- `amount` — float. Positive = charge, negative = refund
- `payment_method` — `"credit_card"` or `"debit_card"` only (insurance not accepted)
- `transaction_id` — randomly generated UUID-style string
- `status` — `"completed"` or `"refunded"`
- `card_last_four` — last 4 digits only (never store full card)
- `created_at`, `updated_at`

### `ExportJob` Model

Tracks asynchronous CSV exports:

- `id`, `patient_id` (FK → Patient)
- `status` — `"pending"`, `"processing"`, `"completed"`, `"failed"`
- `file_path` — absolute filesystem path to generated CSV
- `created_at`, `completed_at`

---

## 4. SQLAlchemy and SQLite in Detail

### How SQLAlchemy Works in this Project

SQLAlchemy is the **ORM (Object-Relational Mapper)**. It lets you work with database records as Python objects instead of writing raw SQL.

The global `db` object is created as `SQLAlchemy()` in `models/database.py` and then bound to the app via `db.init_app(app)` in the factory. This separation is important for the factory pattern — `db` exists before any app is created and is reusable across multiple app instances (e.g. test instances).

#### Session Management

`db.session` is a thread-local session. Operations:

- **Query:** `Doctor.query.filter_by(id=doctor_id).first()`
- **Add:** `db.session.add(new_obj)` + `db.session.commit()`
- **Update:** Modify object attributes, then `db.session.commit()`
- **Delete:** `db.session.delete(obj)` + `db.session.commit()`
- **Rollback:** `db.session.rollback()` — used in the retry loop for concurrent bookings

#### SQLite Specifics

SQLite is a file-based database stored at `instance/hospital.db`. Characteristics:

- **No separate server process** — SQLite reads/writes directly to a file.
- **Limited concurrency** — SQLite uses file-level locking. Under high concurrent writes (e.g. the booking race condition), `IntegrityError` is raised on the loser.
- **No ALTER TABLE restrictions workaround** — SQLite does not support adding constraints to existing columns via ALTER TABLE. To add columns, use `ALTER TABLE table ADD COLUMN col type`. This is exactly what `create_initial_data` does for columns added after the initial migration.

#### Additive Migrations Strategy

No migration framework (like Alembic) is used. Instead, `create_initial_data` checks for missing columns:

```python
import sqlite3
con = sqlite3.connect(db_path)
cur = con.cursor()
cur.execute("PRAGMA table_info(appointment)")
existing_cols = [row[1] for row in cur.fetchall()]
if "is_follow_up" not in existing_cols:
    cur.execute("ALTER TABLE appointment ADD COLUMN is_follow_up BOOLEAN DEFAULT 0")
con.commit()
con.close()
```

This pattern runs on every startup and is idempotent (the check prevents re-running the ALTER).

---

## 5. Flask-Security — Auth and RBAC

Flask-Security-Too provides:

- **User datastore:** `SQLAlchemyUserDatastore(db, User, Role)` wraps database operations for creating/finding/deleting users and assigning roles.
- **Password hashing:** `SECURITY_PASSWORD_HASH = "argon2"` (or sha512 with salt). Passwords are never stored plain.
- **Session management:** After login, a session cookie is set. All subsequent requests carry this cookie and Flask-Security's `current_user` proxy resolves to the logged-in user.
- **`@login_required`** — Returns 401 if no active session.
- **`@roles_required("doctor")`** — Returns 403 if the user lacks the specified role.

### Login Flow

1. POST `/api/login` with `{email, password, role}`.
2. Route fetches the user from DB, verifies the password hash, checks the expected role.
3. On success, `login_user(user)` is called — Flask-Security sets the session cookie.
4. Returns `{role, user: {id, name, email}}` JSON.

### Logout

GET `/api/logout` calls `logout_user()` which clears the session.

### Register (Patient Only)

POST `/api/register` creates a new User + Patient profile + assigns the `patient` role. Doctor creation is exclusively through the admin panel to prevent privilege escalation.

---

## 6. Blueprint-Based Routing

Blueprints are Flask's way of organising routes into modular groups.

```python
# In doctor_routes.py:
doctor_bp = Blueprint("doctor", __name__)

@doctor_bp.route("/doctor/appointments", methods=["GET"])
@login_required
@roles_required("doctor")
def get_doctor_appointments():
    ...
```

```python
# In app.py:
from backend.routes.doctor_routes import doctor_bp
app.register_blueprint(doctor_bp, url_prefix="/api")
# So the full URL is: GET /api/doctor/appointments
```

All four blueprints are registered under `/api`:

| Blueprint | Prefix | Typical Routes |
|---|---|---|
| `auth_bp` | `/api` | `/api/login`, `/api/logout`, `/api/register` |
| `admin_bp` | `/api` | `/api/admin/stats`, `/api/admin/doctors`, etc. |
| `doctor_bp` | `/api` | `/api/doctor/appointments`, `/api/doctor/patients`, etc. |
| `patient_bp` | `/api` | `/api/my-appointments`, `/api/appointments` (POST), etc. |

The frontend always calls `/api/...` base paths, and the server routes them to the correct blueprint.

---

## 7. Admin Routes — Detailed Walkthrough

**File:** `backend/routes/admin_routes.py`

### `GET /api/admin/stats`

Returns aggregate counts for the admin dashboard. Queries:
- Total doctors (joins on User), total patients, total appointments (by status), total revenue (sum of positive payments).
- Also returns recent appointments and monthly appointment trend as arrays for Plotly charts.
- Result is cached with a 5-minute TTL. Cache key: `"admin_stats"`.

### `GET /api/admin/doctors`

Lists all doctors with their user info, department name, and appointment counts. Joins `Doctor`, `User`, `Department` tables. Cache key: `"all_doctors"` with 60-second TTL.

### `POST /api/admin/doctors`

Creates a new doctor. Steps:
1. Validates required fields (name, email, password, specialization, department_id).
2. Checks email uniqueness.
3. Creates `User` + assigns `doctor` role via `user_datastore`.
4. Creates `Doctor` profile record.
5. Commits both in one transaction.
6. Invalidates `"all_doctors"` cache.

### `PUT /api/admin/doctors/<id>`

Updates doctor profile. Handles:
- Updating `User` fields (name, phone).
- Updating `Doctor` fields (specialization, bio, experience, availability, department).
- Password change if `new_password` is provided (re-hashes via Flask-Security).
- Invalidates `"all_doctors"` cache.

### `DELETE /api/admin/doctors/<id>`

Deletes the doctor record and the associated User record. Cascades to appointments (via SQLAlchemy relationship cascade).

### `GET /api/admin/patients`

Lists all patients with profile info, appointment stats, and last visit date.

### `PUT /api/admin/patients/<id>`

Allows admin to edit a patient's profile — name, phone, medical history, date of birth, gender, etc.

### `DELETE /api/admin/patients/<id>`

Deletes Patient + User records.

### `GET /api/admin/appointments`

Returns all appointments across all doctors/patients. Supports query-string filters: `doctor_id`, `patient_id`, `status`, `date_from`, `date_to`. Also supports `search` string matched against doctor/patient names.

### `GET /api/admin/payments`

Lists all payment records sorted by most recent. Includes doctor name, patient name, amount, status.

### `GET /api/admin/doctors/<doctor_id>/patients`

Lists all unique patients who have had any appointment with the specified doctor. Returns patient profile + appointment statistics. Used by the admin "Doctor's Patients" panel.

---

## 8. Doctor Routes — Detailed Walkthrough

**File:** `backend/routes/doctor_routes.py`

### `GET /api/doctor/profile`

Returns the current doctor's full profile — from both User and Doctor tables — including specialization, department name, availability settings, and bio.

### `PUT /api/doctor/availability`

Allows the doctor to update their availability:
- `availability_days` as comma-separated string
- `availability_start`, `availability_end` as HH:MM strings
- `slot_minutes` as integer
- `is_available` boolean

Also invalidates the `"all_doctors"` cache key since patients use that list.

### `GET /api/doctor/appointments`

Returns the current doctor's appointments filtered by optional `status` query param. Joins treatment and payment data. Cached with 30-second TTL.

### `POST /api/appointments/<id>/complete`

Marks an appointment as Completed and records the treatment:
1. Verifies the appointment belongs to this doctor and is currently "Booked".
2. Checks payment: the appointment must have a completed payment before it can be marked complete.
3. Creates or updates a `Treatment` record with diagnosis, prescription, notes.
4. Appends a summary line to `patient.medical_history`.
5. If `create_follow_up` is True and a follow-up date is provided, creates a new Appointment with `is_follow_up=True` and links it back.
6. Invalidates patient history and doctor appointment caches.

### `PUT /api/doctor/appointments/<id>/treatment`

Allows editing a treatment record after completion. Validates:
- Appointment belongs to this doctor.
- Treatment record exists (cannot edit non-existent treatment).
Updates `diagnosis`, `prescription`, `notes` fields and commits.

### `GET /api/doctor/patients`

Lists all unique patients assigned to this doctor — i.e., patients with at least one appointment with this doctor (any status). Returns per-patient stats: total/completed/cancelled/booked appointment counts, last visit date, and full profile info.

### `GET /api/doctor/patients/<id>/history`

Returns full treatment history for a specific patient visible to this doctor: all of their Appointments + linked Treatment records. Sorted by date descending. Cached with 60-second TTL.

### `GET /api/doctor/patients/<id>/summary`

Returns a brief summary: patient name, age (computed from DOB), total treatments, most common diagnosis, last visit.

### `GET /api/doctor/monthly-report/<month>/<year>`

Computes monthly statistics for the doctor: appointments in that period broken down by status, revenue, and a list of all patients treated. Used for the Reports tab.

### `GET /api/doctor/patient-history-pdf/<patient_id>`

Generates a PDF using ReportLab containing the patient's full treatment history with this doctor. Returns as a binary download stream with `application/pdf` content type.

### `GET /api/doctor/payments`

Lists all payments received by this doctor, with patient names and appointment details. Supports filter params `date_from`, `date_to`, `status`.

---

## 9. Patient Routes — Detailed Walkthrough

**File:** `backend/routes/patient_routes.py`

### `GET /api/doctors` (Public-ish)

Returns all available doctors for the patient's booking flow. Supports `department_id` filter. Computes upcoming slot availability for each doctor (scans the next 7 days of the doctor's availability schedule and subtracts already-booked slots). Cached with 60-second TTL.

### `GET /api/patient/departments`

Returns all departments (used to populate the department-browse UI). Wraps the global `Department.query.all()`.

### `GET /api/doctors/<id>/availability`

For a specific doctor in a date range (default next 7 days), returns the available (unbooked) time slots per day. Used in the booking modal after a patient selects a doctor.

### `POST /api/appointments`

Books an appointment:
1. Loads the doctor and validates availability for that day.
2. Generates all theoretical slots for that day.
3. Subtracts booked slots.
4. Assigns the first free slot (serial assignment).
5. Creates an `Appointment` record.
6. Retry loop (up to 3 times) if `IntegrityError` is raised.
7. Invalidates all relevant cache keys.
8. Returns the new appointment's ID.

### `GET /api/my-appointments`

Returns the current patient's appointments. Supports `status` filter. Includes linked treatment data (if completed), payment status (whether payment has been made), and `appointment_cost` (the doctor's fixed fee, so the frontend can display and pre-populate the payment form with the correct amount).

### `POST /api/appointments/<id>/cancel`

Cancels a Booked appointment. Checks:
- Appointment belongs to this patient (or doctor if called from doctor role — the same route handles both via role check).
- Status is currently "Booked".
If a payment exists for this appointment, a refund record is created automatically.

### `GET /api/appointments/<id>/status`

Returns the current status of a specific appointment (used to poll for updates after booking).

### `POST /api/patient/payment/appointment/<id>`

Creates a payment for a booked appointment:
1. Verifies appointment belongs to this patient.
2. Verifies no payment already exists.
3. Derives the payment amount from the doctor's `appointment_cost` (not from the request body — the amount is fixed and cannot be overridden by the client).
4. Validates `payment_method` — only `"credit_card"` or `"debit_card"` are accepted.
5. Creates a `Payment` record (stores only last 4 digits of card).
6. Returns payment confirmation with transaction ID.

All monetary values use Indian Rupees (₹).

### `GET /api/patient/payments`

Returns all payment records for this patient, with appointment and doctor details.

### `POST /api/export/treatments`

Initiates a CSV export:
1. Checks for an existing pending export (prevents duplicate jobs).
2. Creates an `ExportJob` record with status "pending".
3. Dispatches a Celery task `export_patient_treatments.delay(job_id, patient_id)`.
4. Returns the job ID for polling.

### `GET /api/export/treatments/status`

Returns the status of the most recent export job for this patient. If completed, returns the download URL.

### `GET /api/export/treatments/download`

Serves the generated CSV file as a download response.

### `GET /api/profile` and `PUT /api/profile`

Fetch and update the current patient's profile fields.

---

## 10. Auth Routes

**File:** `backend/routes/auth_routes.py`

### `POST /api/login`

Request body: `{email, password, role}`. The `role` field is validated first — if the user exists but their role doesn't match, a 401 is returned. This prevents a doctor from logging in via the patient login path. On success, `login_user(user)` establishes the session and returns basic user info.

### `POST /api/logout`

Calls `logout_user()`. Returns 200.

### `POST /api/register`

Creates a new patient user. Steps:
1. Validates email format, password strength.
2. Checks email not already registered.
3. `user_datastore.create_user(email=..., password=hash_password(password), name=name)`.
4. `user_datastore.add_role_to_user(user, "patient")`.
5. Creates a `Patient` profile record linked to the new user.
6. Commits and returns success.

### `GET /api/current-user`

Returns the session's current user info — used on frontend page load to restore an active session without re-login. Returns 401 if not authenticated.

---

## 11. Redis — Caching in Detail

Redis serves two purposes in this app: **Celery broker/backend** and **Flask-Caching backend**.

### Flask-Caching Configuration

```python
CACHE_TYPE = "RedisCache"
CACHE_REDIS_URL = "redis://localhost:6379/0"
CACHE_DEFAULT_TIMEOUT = 300
```

The `cache` object is an instance of `Flask-Caching`'s `Cache` class, initialised with `cache.init_app(app)`.

### How Caching is Used

Cache decorator pattern:

```python
@cache.cached(timeout=60, key_prefix="all_doctors")
def get_all_doctors():
    # This body runs only if cache miss
    ...
```

Manual cache usage (for more control):

```python
result = cache.get("admin_stats")
if result is None:
    result = compute_expensive_stats()
    cache.set("admin_stats", result, timeout=300)
return result
```

### Cache Keys Used

| Key Pattern | TTL | Invalidated When |
|---|---|---|
| `"admin_stats"` | 300s | Any doctor/patient/appointment change |
| `"all_doctors"` | 60s | Doctor profile updated, availability changed |
| `"doctor_appointments_{id}"` | 30s | Appointment status changes |
| `"doctor_appointments_{id}_Booked"` | 30s | New booking, cancellation |
| `"doctor_appointments_{id}_Completed"` | 30s | Appointment completed |
| `"doctor_appointments_{id}_Cancelled"` | 30s | Appointment cancelled |
| `"patient_history_{id}"` | 60s | Treatment added/updated for this patient |

### Why Multiple Keys Per Doctor?

The `GET /api/doctor/appointments` route accepts an optional `status` query param. If status=Booked, it caches under `doctor_appointments_{id}_Booked`. If no filter, it caches under `doctor_appointments_{id}`. On a write, **all four variants** are invalidated:

```python
for suffix in [None, "Booked", "Completed", "Cancelled"]:
    key = f"doctor_appointments_{doctor_id}" + (f"_{suffix}" if suffix else "")
    cache.delete(key)
```

### Celery Broker Role

Redis also receives Celery task messages. When Python code calls `export_patient_treatments.delay(job_id, patient_id)`, Celery serialises the task and arguments and pushes the message to a Redis list (`celery` queue by default). The Celery worker process continuously polls Redis, pops the message, deserialises it, and executes the task function.

---

## 12. Celery — Task Queue and Scheduling

### Windows — `solo` worker pool

Celery's default `prefork` pool relies on `os.fork()`, which does not exist on Windows. Running the worker on Windows without setting the pool raises `PermissionError` / `OSError` at startup. 

`backend/celery_config.py` detects the platform and downgrades to the `solo` pool on Windows:

```python
import sys

_is_windows = sys.platform == "win32"
celery.conf.update(
    worker_pool="solo" if _is_windows else "prefork",
    worker_concurrency=1 if _is_windows else (os.cpu_count() or 1),
)
```

The `solo` pool runs tasks synchronously in the worker process with concurrency 1. It is functionally identical for development; POSIX servers use `prefork` with full concurrency.

### Configuration (`backend/celery_config.py`)

```python
def make_celery(app):
    celery = Celery(
        app.import_name,
        broker=app.config["CELERY_BROKER_URL"],   # redis://localhost:6379/1
        backend=app.config["CELERY_RESULT_BACKEND"],  # redis://localhost:6379/2
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
```

The `ContextTask` base class is critical. Without it, task code cannot access `db.session`, Flask-Mail, or any other extension that needs the app context.

### Celery Beat — Scheduler

Celery Beat is a separate process that reads a schedule and dispatches tasks at the right times. It writes a persistent schedule state to `celerybeat-schedule` (SQLite-format binary file in the project root).

The Beat schedule is defined in `backend/celery_config.py`:

```python
celery.conf.beat_schedule = {
    "daily-appointment-reminders": {
        "task": "backend.tasks.send_appointment_reminders",
        "schedule": crontab(hour=8, minute=0),  # Every day at 8 AM
    },
    "monthly-doctor-reports": {
        "task": "backend.tasks.send_monthly_doctor_reports",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),  # 1st of each month at 6 AM
    },
}
```

### Workflow: From Task Dispatch to Execution

1. Application code (e.g. `patient_routes.py`) calls `some_task.delay(arg1, arg2)`.
2. Celery serialises `("backend.tasks.some_task", [arg1, arg2], {})` as a JSON message.
3. The message is pushed into the Redis `celery` queue (a Redis list).
4. The Celery worker (running in its own process) blocks on `BRPOP celery 0` — Redis pops the message and delivers it.
5. The worker instantiates the `ContextTask` subclass, which wraps execution in `with app.app_context()`.
6. The task function runs with full Flask context access.
7. The return value (or exception) is stored in the Redis result backend under a key derived from the task ID.
8. The original caller can optionally call `.get()` on the `AsyncResult` to retrieve the return value — but in this project, results are tracked via the `ExportJob` model instead.

---

## 13. Background Tasks — Each Task Explained

**File:** `backend/tasks.py`

### `send_appointment_reminders()`

- Scheduled: daily at 8:00 AM via Celery Beat.
- Logic: Queries `Appointment.query.filter_by(date=today, status="Booked")`. For each, sends an email to the patient with appointment time, doctor name.
- Uses: `Flask-Mail` with Gmail SMTP configured via `.env` file.

### `send_monthly_doctor_reports()`

- Scheduled: 1st of each month at 6:00 AM.
- Logic: Iterates all doctors with `email_notifications=True`. For each, queries appointments in the previous month, computes counts, formats an HTML email with statistics and a list of treated patients. Sends via Flask-Mail.

### `export_patient_treatments(job_id, patient_id)`

- Triggered: on demand when patient requests CSV export.
- Logic:
  1. Sets `ExportJob.status = "processing"`.
  2. Queries all completed appointments for the patient with linked Treatment records.
  3. Writes a CSV to `exports/patient_{id}_treatments_{timestamp}.csv`.
  4. Updates `ExportJob.status = "completed"`, `ExportJob.file_path = <path>`.
  5. Sends a notification email to the patient.
- Error handling: if any exception occurs, sets `ExportJob.status = "failed"`.

---

## 14. PDF Report Generation (ReportLab)

**File:** `backend/pdf_reports.py`

The `generate_patient_history_pdf(doctor, patient, appointments)` function uses ReportLab's `SimpleDocTemplate` and `Paragraph` objects to compose a structured PDF:

1. Creates a `BytesIO` buffer (in-memory file).
2. Builds a list of `Flowable` objects — table headers, `Paragraph` elements for each appointment block.
3. Calls `doc.build(story)` to render the layout into PDF bytes.
4. The route streams the buffer back with `Content-Disposition: attachment; filename=...`.

The doctor-side monthly report PDF follows the same pattern — a `SimpleDocTemplate` populated with the month's appointment log.

---

## 15. Validators and Input Handling

**File:** `backend/validators.py`

Custom validation decorators are applied to route functions:

```python
@validate_required_fields(["email", "password", "name"])
def register():
    ...
```

How it works: the decorator wraps the route function. Before the original function is called, it parses `request.json` and checks each required field is present and non-empty. If any are missing, it returns a JSON 400 response immediately without calling the original function.

Available validators:
- `validate_required_fields([fields])` — checks fields are present and non-empty
- `validate_string_length(field, min, max)` — returns 400 if string is too short or long
- `validate_email(field)` — uses `re.match` against email pattern
- `validate_password_strength(field)` — checks minimum length and character complexity

---

## 16. Frontend Architecture (Vue.js 3)

**Files:** `frontend/index.html`, `frontend/static/js/app.js`, `backend/ensure_vendors.py`

### Front-end Vendor Asset Management

Large third-party libraries (Bootstrap, Vue.js, Plotly) are **not** committed to the repository to keep it lightweight and avoid plagiarism-checker false positives on minified third-party code.

Instead, `backend/ensure_vendors.py` is a pure-stdlib Python module that:

1. Defines a list of 7 assets (CSS, fonts, JS) with their CDN URLs and local destination paths.
2. On each import it checks whether every file exists under `frontend/static/vendor/`.
3. Downloads any missing file using `urllib.request` (no third-party libraries required) with a descriptive `User-Agent` header.
4. On subsequent imports it exits immediately (all `Path.exists()` checks are true).

`app.py` imports and calls `ensure_vendors()` at module scope, so the check runs once per process start — before any request is served.

To force a re-download (e.g. to update a library version):

```bash
uv run python -m backend.ensure_vendors --force
```

### `v-cloak` and the Loading Spinner

The entire `<div id="app">` carries a `v-cloak` attribute. The CSS rule:

```css
[v-cloak] { display: none; }
```

suppresses raw `{{ }}` interpolation tokens that would flash before Vue processes the template. Vue removes `v-cloak` automatically when the app mounts.

Because Plotly alone is ~4.4 MB and loaded synchronously, there is a brief blank-page period while the browser downloads and parses the bundles. A CSS-only spinner solves this:

```css
#app-loading { position: fixed; inset: 0; display: flex; … }
body:has(#app:not([v-cloak])) #app-loading { display: none; }
```

A `<div id="app-loading">` placed before `<div id="app">` is always visible. The `:has()` selector automatically hides it the moment Vue removes `v-cloak` — no JavaScript needed.

### Single-File SPA Pattern

The entire SPA is served as a single HTML file (`index.html`). It:

1. Loads Bootstrap 5 CSS from the local vendor directory.
2. Loads Vue.js 3 from the local vendor directory.
3. Loads Plotly.js from the local vendor directory.
4. Loads the custom `style.css`.
5. Contains all HTML template markup inside a single `<div id="app" v-cloak>`.
6. Loads `app.js` which defines and mounts the Vue app.

There is no build system, Webpack, or separate component files. This is intentional for simplicity — the system runs without any Node.js compilation step.

### Vue App Mounting

In `app.js`:

```javascript
const app = Vue.createApp({
    data() { return { /* all state */ } },
    computed: { /* derived state */ },
    methods: { /* all methods */ },
    async mounted() {
        await this.checkCurrentUser();
    }
})
app.mount('#app')
```

### Request Helpers

All HTTP calls use the native `fetch` API:

```javascript
const response = await fetch('/api/doctor/appointments', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
});
const data = await response.json();
```

CSRF is not separately managed — Flask-Security uses the session cookie which is included automatically by the browser with each request to the same origin.

---

## 17. Vue.js — Data Model and State

All reactive state is declared in `data()`. Key groups:

### Authentication State
- `currentUser` — `{id, name, email, role}` or null
- `isLogin` — boolean toggle between login and register forms
- `selectedRole` — which role tab is active on the login page (`"patient"`, `"doctor"`, `"admin"`)

### Role Routing
- `activeRole` — the authenticated user's role string. Controls which dashboard renders.

### Admin State
- `adminStats` — statistics object from `/admin/stats`
- `adminDoctors` — array of doctor objects
- `adminPatients` — array of patient objects
- `adminAppointments` — array of appointment objects
- `adminPayments` — array of payment objects
- `adminDoctorForm` — form object for create/edit doctor
- `adminEditingDoctor` — currently being edited doctor, or null
- `adminViewDoctorPatients` — doctor object whose patients are being viewed, or null
- `adminDoctorPatientsList` — list of patients for admin's doctor patients panel

### Doctor State
- `doctorTab` — active tab: `"appointments"`, `"patients"`, `"reports"`, `"payments"`, `"availability"`, `"profile"`
- `doctorAppointments` — array from `/doctor/appointments`
- `doctorPatients` — array from `/doctor/patients`
- `filteredDoctorPatients` — locally filtered version of `doctorPatients`
- `doctorPatientSearch` — search string for patient filtering
- `selectedPatientHistory` — history array for currently viewed patient
- `editingHistoryRecord` — treatment record being edited in the history view
- `treatmentForm` — form for completing an appointment
- `treatmentEditForm` — form for editing an existing treatment

### Patient State
- `patientTab` — active tab: `"book"`, `"appointments"`, `"payments"`, `"profile"`
- `bookingDepartments` — array of departments for the booking department-browser
- `selectedBookingDepartment` — currently selected department ID filter
- `availableDoctors` — array of doctors shown for booking as profile cards
- `bookingDeptFilter` — currently selected department ID filter
- `bookingDoctorSearch` — name search string for filtering booking doctor cards
- `filteredBookingDoctors` — computed/filtered list of doctor cards
- `myAppointments` — patient's own appointments
- `selectedAppointment` — appointment being acted on (cancel, pay, view treatment)
- `paymentForm` — payment form state; `amount` is auto-set from `appointment.appointment_cost` and is read-only
- `profileForm.notif_email` — always true; all notifications go via email (SMS removed)

### UI State
- `successMessage`, `isLoading`, various modal/dropdown toggles

---

## 18. Vue.js — Methods Reference

### Auth Methods
- `checkCurrentUser()` — calls `GET /api/current-user`, restores session if active
- `login()` — `POST /api/login`, sets `currentUser`, calls `loadInitialDataForRole()`
- `logout()` — `GET /api/logout`, resets all state
- `register()` — `POST /api/register`

### Initialisation
- `loadInitialDataForRole()` — calls the correct set of load functions based on `currentUser.role`. For patients, also calls `loadBookingDepartments()`.
- `resetTransientState()` — clears all transient UI and form state on role switch.

### Doctor Methods
- `loadDoctorAppointments()` — fetches appointments, sorts upcoming (Booked + today-or-future) first; secondary sort by date/time ascending
- `isUpcomingAppointment(apt)` — returns true if `apt.status === 'Booked'` and `apt.date >= today`
- `completeAppointment()` — `POST /api/appointments/{id}/complete`
- `cancelAppointment(id)` — `POST /api/appointments/{id}/cancel`
- `updateTreatment()` — `PUT /api/doctor/appointments/{id}/treatment`
- `loadDoctorPatients()` — fetches `/doctor/patients`
- `filterDoctorPatients()` — filters `doctorPatients` by `doctorPatientSearch` string
- `viewPatientHistory(patientId)` — fetches `/doctor/patients/${patientId}/history`
- `closePatientHistory()` — clears `selectedPatientHistory` and `editingHistoryRecord`
- `startEditTreatmentFromHistory(record)` — populates `treatmentEditForm`, sets `editingHistoryRecord`
- `saveHistoryTreatmentEdit()` — `PUT /api/doctor/appointments/{id}/treatment` using `treatmentEditForm`, then reloads patient history

### Patient Methods
- `loadBookingDepartments()` — fetches `/patient/departments`
- `selectBookingDepartment(deptId)` — sets `bookingDeptFilter` and filters doctor cards
- `loadDoctorsForBooking()` — fetches `/api/doctors`, then filters by `bookingDeptFilter` and `bookingDoctorSearch`
- `onDoctorCardClick(doc)` — sets `bookingForm.doctor_id`, triggers `onDoctorChange()`
- `bookAppointment()` — `POST /api/appointments`
- `loadMyAppointments()` — fetches `/api/my-appointments`
- `cancelAppointment(id)` — `POST /api/appointments/{id}/cancel`
- `showPaymentForm(appointment)` — opens payment form, sets `paymentForm.amount` from `appointment.appointment_cost`
- `processPayment()` / `makePayment()` — `POST /api/patient/payment/appointment/{id}`
- `initiateExport()` — `POST /api/export/treatments`
- `pollExportStatus()` — `GET /api/export/treatments/status` on interval until complete

### Admin Methods
- `loadAdminStats()` — fetches `/admin/stats`, draws Plotly charts
- `loadAdminDoctors()`, `saveDoctor()`, `deleteDoctor()`
- `loadAdminPatients()`, `savePatient()`, `deletePatient()`
- `viewDoctorPatients(doc)` — fetches `/admin/doctors/${doc.id}/patients`, sets `adminViewDoctorPatients`
- `loadAdminAppointments()` with filter support
- `loadAdminPayments()`

---

## 19. Vue.js — Template Sections

The `index.html` template is divided into role-scoped regions controlled by `v-if="activeRole === 'X'"`. Key sections:

### Login / Register (`v-if="!currentUser"`)
- Login form with tabs for role selection (Admin / Doctor / Patient).
- Patient register link: `@click.prevent="isLogin=false; selectedRole='patient'"` to switch to the register form.
- Register form (only shown for patient role).

### Admin Dashboard (`v-if="activeRole === 'admin'"`)
- Nav tabs: Stats, Doctors, Patients, Appointments, Payments.
- Stats tab: Plotly bar chart for monthly appointments + summary cards.
- Doctors tab: table with Edit / Delete / Patients buttons. "Doctor's Patients" panel (`v-if="adminViewDoctorPatients"`) below the table.
- Patients tab: table with Edit / Delete buttons.

### Doctor Dashboard (`v-if="activeRole === 'doctor'"`)
- Nav tabs: Appointments, My Patients, Reports, Payments, Availability, Profile.
- Appointments tab: table with colour-coded rows (green for `isUpcomingAppointment`), sort is pre-applied in JS; Cancel button for Booked appointments.
- My Patients tab: searchable patient list, patient history viewer with inline treatment editor.

### Patient Dashboard (`v-if="activeRole === 'patient'"`)
- Nav tabs: Book Appointment, My Appointments, Payments, Profile.
- Book tab: Department filter buttons, text search input for doctor name, then scrollable grid of doctor profile cards (name, dept, availability, slot, fee ₹, bio). Clicking a card selects that doctor. Below the cards sits the date picker and booking confirmation.
- My Appointments tab: appointment rows with treatment detail accordion; upcoming (Booked + future date) rows highlighted in light green. Cancel and Pay buttons as appropriate.
- Profile tab: Email notification preference is always enabled (read-only); medical history displayed as read-only text (not editable by patient).

---

## 20. Full Request-Response Flow Examples

### Patient Books an Appointment

1. Patient loads app → `checkCurrentUser()` → returns `{role: "patient", ...}` → `loadInitialDataForRole()` is called.
2. `loadInitialDataForRole()` calls `loadBookingDepartments()` → `GET /api/patient/departments` → populates department buttons.
3. Patient browses doctor profile cards (all doctors visible). Selects "Cardiology" filter → only cardiologists shown. Types in search box to narrow by name.
4. Patient clicks a doctor card → that doctor is selected; a date picker appears.
5. Patient picks date and clicks "Confirm Booking" → `bookAppointment()` → `POST /api/appointments` with `{doctor_id: 5, date: "2026-03-10"}`.
6. Backend: generates slots for that date, removes booked ones, assigns first free slot, creates Appointment, invalidates caches, returns `{appointment_id: 42}`.
7. Success message shown. `loadMyAppointments()` refreshed.

### Doctor Completes a Consultation

1. Doctor on Appointments tab sees appointment #42 (Booked, today) highlighted in green.
2. Clicks "Complete" → form appears asking for diagnosis, prescription, notes.
3. Clicks "Save" → `completeAppointment()` → `POST /api/appointments/42/complete` with treatment payload.
4. Backend: validates payment exists, creates Treatment record, appends to patient's `medical_history`, optionally creates follow-up, invalidates all relevant caches.
5. Appointment row in table now shows status "Completed" (no longer green).
6. Patient sees updated treatment in their "My Appointments" tab next time they load.

---

## 21. Error Handling Strategy

### Backend

- All route functions are wrapped in try-except. On exception, a generic `{"error": "Internal server error"}` is returned with HTTP 500.
- Full tracebacks are printed to the terminal with `import traceback; traceback.print_exc()`.
- Validation errors return 400 with specific field-level messages.
- Auth errors return 401 or 403.
- Not-found entities return 404 with a descriptive message.

### Frontend

- Every `fetch` call is wrapped in try-catch. On error, `this.successMessage = "..."` is set with a user-friendly message (or the server's error string).
- The `sendClientLog(level, message)` function forwards frontend errors to `POST /api/client-log`, which prints them server-side.
- No raw error objects or stack traces are ever shown to the user.

---

## 22. Test Infrastructure (Overview)

**Framework:** pytest with a custom `conftest.py`.

### `conftest.py` Key Fixtures

- `app` fixture: calls `create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'WTF_CSRF_ENABLED': False, 'CELERY_TASK_ALWAYS_EAGER': True})`. Fresh in-memory DB per test session.
- `client` fixture: returns Flask test client from `app.test_client()`.
- `admin_client`, `doctor_client`, `patient_client` fixtures: log in as the respective user and return an authenticated test client with the session cookie set.
- Seed fixtures create: 4 departments, 2 doctors, 2 patients, several appointments.

### Test Files

- `test_auth.py` — register, login, logout, invalid credentials.
- `test_admin.py` — CRUD for doctors/patients/departments, stats endpoint.
- `test_appointments.py` — booking, slot conflict, cancellation, payment, completion.
- `test_flow.py` — full end-to-end workflows across multiple steps.
- `test_cache.py` — verifies cache hit/miss behaviour and invalidation.
- `test_celery.py` — verifies task execution with `CELERY_TASK_ALWAYS_EAGER=True` (tasks run synchronously in tests).

---

## 12. Challenges and Solutions

### 12.1 Concurrent Booking Race Condition

**Challenge:** Multiple patients attempting to book the last available slot simultaneously could each read the slot as available and commit conflicting appointments.

**Solution:** A unique database index on `(doctor_id, date, time)` raises an `IntegrityError` on the second commit. The booking function catches this, rolls back, and retries up to three times. This concurrency approach is efficient in the common case while safe in the edge case.

### 12.2 Date Serialisation Inconsistency

**Challenge:** Database date columns could return either Python `date` objects or plain strings depending on context, causing `AttributeError` exceptions during JSON serialisation.

**Solution:** A `_normalize_date_str` helper function accepts both string and date-object inputs and consistently returns a `YYYY-MM-DD` string. All serialisation paths use this function.

### 12.3 Flask App Context in Celery Tasks

**Challenge:** Celery worker processes run outside the Flask request context. Database models and Flask extensions are not available by default.

**Solution:** A custom `ContextTask` base class overrides Celery's `__call__` method to execute each task body inside a `with app.app_context()` block, making all Flask resources available transparently.

### 12.4 Multi-Variant Cache Invalidation

**Challenge:** Patient appointment caches are keyed by both `patient_id` and `status_filter`, producing four cache entries per patient. A status-changing write must invalidate all four.

**Solution:** Every relevant write operation explicitly calls `cache.delete()` for all four key variants (None, Booked, Completed, Cancelled). This guarantees consistency without a more complex cache tagging system.
