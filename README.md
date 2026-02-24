# Hospital Management System

A professional, production-grade Hospital Management System with role-based access control for Admins, Doctors, and Patients.

## Features

### Core Functionality
- **Role-Based Access**: Separate dashboards for Admin, Doctor, and Patient roles
- **Appointment Management**: Book, complete, and cancel appointments with conflict prevention
- **Patient Records**: Automatic medical history tracking updated after each completed appointment (read-only to patients)
- **Doctor Management**: Add/remove doctors, assign departments, set fixed consultation fees
- **Doctor Card Profiles**: Patient booking shows browsable doctor profile cards with department filter and name search
- **PDF Reports**: Generate professional monthly activity reports for doctors
- **Payment Portal**: Fixed-fee payment system in Indian Rupees (₹); credit card and debit card only
- **Background Jobs**: Automated email/SMS reminders and monthly reports via Celery
- **Upcoming Appointment Highlighting**: All dashboards (admin, doctor, patient) highlight upcoming appointments in green for easy visual differentiation

### Technical Features
- **Caching**: Redis-based caching for performance
- **Security**: Argon2 password hashing, role-based authorization
- **Validation**: Comprehensive backend input validation
- **Testing**: 77 test cases with pytest
- **Professional UI**: Clean hospital-themed interface with ₹ (INR) currency throughout

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
4. Fill in doctor details including the **Consultation Fee (₹)** field (default ₹500)

### Patient
1. Click "Register here" on login page
2. Fill in details
3. Login with your credentials
> **Note:** If you attempt to log in without having registered, the app will show a prompt to register first.

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

All 77 tests should pass successfully.

---

## Database Schema

The system uses 10 tables:

1. **USER** - All system users (admin, doctors, patients)
2. **ROLE** - User roles (admin, doctor, patient)
3. **ROLES_USERS** - Many-to-many relationship for user roles
4. **DEPARTMENT** - Medical departments (Cardiology, Neurology, etc.)
5. **DOCTOR** - Doctor profiles linked to users, includes `appointment_cost` (fixed consultation fee in ₹)
6. **PATIENT** - Patient profiles; `notification_pref` stores comma-separated channels: `email`, `sms`, or `email,sms`
7. **APPOINTMENT** - Appointment records
8. **TREATMENT** - Treatment records for completed appointments
9. **EXPORT_JOB** - Background CSV export jobs
10. **PAYMENT** - Payment records; `payment_method` is `credit_card` or `debit_card` only

See `er_diagram.png` for visual representation.

---

## Key Behaviours

### Payment System
- The consultation fee is **set by the Admin** for each doctor (default ₹500).
- When a patient goes to pay, the amount is **fixed and read-only** — it cannot be changed.
- Payment is in **Indian Rupees (₹)** throughout the system.
- Accepted methods: **Credit Card** and **Debit Card** only.

### Medical History
- Medical history is **automatically updated** when a doctor completes an appointment and records diagnosis/prescription.
- Patients **cannot manually edit** their medical history.

### Notification Preferences
- Patients can choose to receive reminders via **Email**, **SMS**, or **both**.
- Selected via checkboxes in the profile settings.

### Booking Flow (Patient)
1. Go to **Book Appointment** tab.
2. Browse doctor profile cards — filter by department or search by name.
3. Click a doctor card to select it.
4. Choose available date and confirm booking.

### Upcoming Appointments
- Rows for upcoming (booked, future-dated) appointments are highlighted in **light green** in all three dashboards for quick visual identification.

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
- Clear data tables with ₹ (INR) currency

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
4. Update `newDoctor` data and `openCreateDoctor()`/`openEditDoctor()` in `frontend/static/js/app.js`
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

## Demo & Testing Guide

See [demo-guide.md](demo-guide.md) for a complete step-by-step guide covering every feature with exact field values for admin, doctor, and patient roles — suitable for demos and manual testing.


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
