# Hospital Management System

A professional, production-grade Hospital Management System with role-based access control for Admins, Doctors, and Patients.

## Features

### Core Functionality
- **Role-Based Access**: Separate dashboards for Admin, Doctor, and Patient roles
- **Appointment Management**: Book, complete, and cancel appointments with conflict prevention
- **Patient Records**: Track medical history, treatments, and prescriptions
- **Doctor Management**: Add/remove doctors, assign departments
- **PDF Reports**: Generate professional monthly activity reports for doctors
- **Payment Portal**: Dummy payment system for appointments (demonstration only)
- **Background Jobs**: Automated email reminders and monthly reports via Celery

### Technical Features
- **Caching**: Redis-based caching for performance
- **Security**: Argon2 password hashing, role-based authorization
- **Validation**: Comprehensive backend input validation
- **Testing**: 50+ test cases with pytest
- **Professional UI**: Clean hospital-themed interface (no gradients, professional colors)

---

## Requirements

- **Python 3.14+** (or 3.10+)
- **Redis** (for caching and Celery)
- **uv** (Python package manager)

---

## Quick Start

### Step 1: Install Dependencies

```bash
# Using uv
uv sync

# Or using pip
pip install -r requirements.txt
```

### Step 2: Start Redis Server

```
docker run --name hms-redis -p 6379:6379 -d redis
```

### Step 3: Run the Application

```bash
# Start the Flask development server
uv run python app.py

# The application will be available at:
# http://localhost:5000
```

The first time you run the app, it will automatically:
- Create the database (`instance/hospital.db`)
- Set up default roles (admin, doctor, patient)
- Create admin user: **username:** `admin` **password:** `admin`
- Create default departments (Cardiology, Neurology, etc.)

### Step 4: Start Background Workers

For background jobs like email reminders and monthly reports:

**Terminal 1 - Celery Worker:**
```bash
uv run celery -A backend.celery_config worker --loglevel=info
```

**Terminal 2 - Celery Beat (Scheduler):**
```bash
uv run celery -A backend.celery_config beat --loglevel=info
```

---

## Default Login Credentials

### Admin
- **Username:** `admin`
- **Password:** `admin`

### Doctor (Create via Admin Dashboard)
1. Login as admin
2. Go to "Doctors" tab
3. Click "Add Doctor"

### Patient
1. Click "Register here" on login page
2. Fill in details
3. Login with your credentials

---

## Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_auth.py

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=backend --cov=models
```

All 53 tests should pass successfully.

---

## Database Schema

The system uses 10 tables:

1. **USER** - All system users (admin, doctors, patients)
2. **ROLE** - User roles (admin, doctor, patient)
3. **ROLES_USERS** - Many-to-many relationship for user roles
4. **DEPARTMENT** - Medical departments (Cardiology, Neurology, etc.)
5. **DOCTOR** - Doctor profiles linked to users
6. **PATIENT** - Patient profiles linked to users
7. **APPOINTMENT** - Appointment records
8. **TREATMENT** - Treatment records for completed appointments
9. **EXPORT_JOB** - Background CSV export jobs
10. **PAYMENT** - Payment records (dummy portal)

See `er_diagram.png` for visual representation.

---

## Configuration

### Database
- SQLite (`instance/hospital.db`)

### Redis
- Default: `redis://localhost:6379/0`
- To change, update `CACHE_REDIS_URL` in `app.py`

### Security Keys
- `SECRET_KEY` in `app.py`
- `SECURITY_PASSWORD_SALT` in `app.py`

---

## UI Design Philosophy

The frontend follows a professional hospital aesthetic:

✅ **DO:**
- Clean white and gray backgrounds
- Medical green (#388e3c) for primary actions
- Medical red (#d32f2f) for alerts
- Simple, readable fonts
- Clear data tables

❌ **DON'T:**
- Gradients or fancy effects
- Bright blues/purples
- Emojis or informal language
- Cluttered layouts

---

## Making Modifications

The codebase is designed to be easily modifiable:

### Add a new field to Doctor:
1. Update `Doctor` model in `models/database.py`
2. Update `to_dict()` method
3. Update admin form in `frontend/index.html`
4. Update `addDoctor()` method in `frontend/static/js/app.js`
5. Update tests if needed

### Add a new route:
1. Add route function in appropriate file under `backend/routes/`
2. Add validation decorators from `backend/validators.py`
3. Add frontend method in `frontend/static/js/app.js`
4. Add UI elements in `frontend/index.html`
5. Test with pytest

### Change colors:
1. Update CSS variables in `frontend/index.html` `<style>` section
2. Look for `:root` variables (e.g., `--hospital-green`)

---

### Stop/Restart Servers

- Stop Redis:
```
docker stop hms-redis
```
- Start again:
```
docker start hms-redis
```
---
