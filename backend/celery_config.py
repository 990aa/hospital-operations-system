"""
Celery Configuration for Background Jobs.

This module configures Celery for handling asynchronous tasks and scheduled jobs
in the Hospital Management System. It uses Redis as the message broker and backend.

Tasks include:
- Daily appointment reminders (sent via email/SMS/Google Chat)
- Monthly doctor activity reports (sent via email)
- Async CSV export of patient treatment history

Author: Abdul Ahad
"""

import os
import sys

from celery import Celery
from celery.schedules import crontab


def make_celery(app=None):
    """
    Create and configure a Celery instance.

    This factory function creates a Celery instance with Redis as both the
    message broker and result backend. It can optionally be initialized with
    a Flask app context.

    Args:
        app: Optional Flask application instance for context

    Returns:
        Configured Celery instance
    """
    # Redis URL - uses environment variable or defaults to localhost
    # Format: redis://username:password@host:port/db
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Create Celery instance
    celery = Celery(
        "hospital_tasks",  # Name of the Celery app
        broker=redis_url,  # Redis as message broker
        backend=redis_url,  # Redis as result backend
        include=["backend.tasks"],  # Import tasks from this module
    )

    # On Windows the default 'prefork' pool uses shared memory primitives
    # (billiard) that fail with PermissionError / OSError.  The 'solo' pool
    # executes tasks inline in the main worker process and has no such issues.
    # On POSIX systems we keep 'prefork' for true concurrency.
    _is_windows = sys.platform == "win32"
    _worker_pool = "solo" if _is_windows else "prefork"
    # solo pool is single-threaded, so concurrency must be 1
    _worker_concurrency = 1 if _is_windows else (os.cpu_count() or 1)

    # Celery configuration
    celery.conf.update(
        # Task serialization
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",  # Use UTC for all task scheduling
        enable_utc=True,
        # Task execution settings
        task_track_started=True,  # Track when tasks start
        task_time_limit=3600,  # 1 hour time limit for tasks
        # Result backend settings
        result_expires=86400,  # Results expire after 24 hours
        # Worker pool – 'solo' on Windows avoids prefork PermissionError/OSError
        worker_pool=_worker_pool,
        worker_concurrency=_worker_concurrency,
        # Worker settings
        worker_prefetch_multiplier=1,  # Prefetch one task at a time
    )

    # Optional: Auto-discover tasks from installed apps
    # celery.autodiscover_tasks()

    return celery


# Create the Celery instance
# This is imported by app.py and tasks.py
celery = make_celery()


# Beat schedule configuration for periodic tasks
# This defines when scheduled tasks should run
celery.conf.beat_schedule = {
    # Daily reminders - run every day at 8:00 AM
    # Sends reminders to patients about their appointments for today
    "daily-appointment-reminders": {
        "task": "backend.tasks.send_daily_reminders",
        "schedule": crontab(hour=8, minute=0),  # 8:00 AM daily
    },
    # Monthly reports - run on the 1st day of every month at 9:00 AM
    # Sends activity reports to doctors for the previous month
    "monthly-doctor-reports": {
        "task": "backend.tasks.send_monthly_reports",
        "schedule": crontab(day_of_month=1, hour=9, minute=0),  # 1st of month at 9 AM
    },
}
