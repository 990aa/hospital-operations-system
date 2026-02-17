# Hospital Management System (HMS)

A modern, professional Hospital Management System built with Flask (backend), Vue.js (frontend), and Celery/Redis (background jobs).

## Key Features

### Role-Based Access Control
- **Admin**: Full system management (doctors, patients, statistics).
- **Doctor**: Appointment management, patient history access, and treatment recording.
- **Patient**: Booking appointments, tracking treatment history, and profile management.

### Enhanced Functionality
- **Scheduled Reminders**: Automated daily alerts for patients with upcoming visits.
- **Monthly Reports**: Automated activity summaries for doctors.
- **Async Exports**: User-triggered CSV exports of treatment history processed in the background.
- **Conflict Prevention**: Intelligent scheduling to prevent double-booking for doctors.
- **Advanced Search**: Search for doctors by name or specialization; search for patients by name, ID, or contact.
- **Performance**: Integrated caching with Redis for faster data access.

### Professional UI
- Clean, minimalist design following professional standards.
- Interactive data visualizations using **Plotly**.
- Responsive layout using Bootstrap 5.

## Technology Stack
- **Backend**: Flask, Flask-SQLAlchemy, Flask-Security-Too, Flask-Caching.
- **Task Queue**: Celery with Redis broker.
- **Frontend**: Vue.js 3, Plotly.js, Bootstrap 5.
- **Environment**: Managed via `uv`.

## Setup Instructions

### Prerequisites
- Python 3.14+
- Redis (running on `localhost:6379`)

### 1. Install Dependencies
Using `uv`:
```bash
uv sync --all-extras
```

### 2. Start Redis
Ensure your Redis server is running. On Windows, you might use WSL or a native port.

### 3. Run Background Worker
Start Celery worker and beat in separate terminals:
```bash
# Terminal 1: Worker
uv run celery -A backend.celery_config worker --loglevel=info

# Terminal 2: Beat (for scheduled jobs)
uv run celery -A backend.celery_config beat --loglevel=info
```

### 4. Run the Application
```bash
uv run python app.py
```
This will initialize the database (`hospital.db`) and create the initial Admin user on the first run.

### 5. Access the App
Open your browser to: `http://127.0.0.1:5000`

## Initial Credentials
- **Admin Username**: `admin`
- **Admin Password**: `admin`

## Testing
Run the comprehensive test suite:
```bash
uv run pytest
```

---
*Developed by: Abdul Ahad*
