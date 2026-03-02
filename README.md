# Hospital Management System

A professional Hospital Management System with role-based access control for Admins, Doctors, and Patients.

## Features

### Core Functionality
- **Role-Based Access**: Separate dashboards for Admin, Doctor, and Patient roles
- **Appointment Management**: Book, complete, and cancel appointments with conflict prevention
- **Patient Records**: Automatic medical history tracking updated after each completed appointment (read-only to patients)
- **Doctor Management**: Add/remove doctors, assign departments, set fixed consultation fees
- **Doctor Card Profiles**: Patient booking shows browsable doctor profile cards with department filter and name search
- **PDF Reports**: Generate professional monthly activity reports for doctors
- **Background Jobs**: Automated email reminders and monthly reports via Celery

---

## Quick Start

### Step 1: Install Dependencies

```powershell
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

```powershell
uv run python app.py
```

### Step 4: Start Background Jobs

**Terminal 1 - Celery Worker:**
```bash
uv run celery -A backend.celery_config worker --loglevel=info
```

**Terminal 2 - Celery Beat (Scheduler):**
```bash
uv run celery -A backend.celery_config beat --loglevel=info
```

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