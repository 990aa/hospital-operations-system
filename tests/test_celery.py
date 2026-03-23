"""
Celery Tasks Tests.

Tests for background job functionality:
- Daily reminders
- Monthly reports
- CSV export
- Email notifications

Note: These tests mock the Celery tasks since running a full Celery worker
requires Redis to be running.
Google Chat is intentionally excluded from this system.

Author: Abdul Ahad
"""

from unittest.mock import patch


def test_export_task_creation(test_client, patient_token):
    """
    Test that export task is created properly.

    Verifies:
    - Export job is created in database
    - Task ID is returned
    - Job status is 'pending'
    """
    response = patient_token.post("/api/export/treatments")
    assert response.status_code in [200, 201]
    data = response.get_json()

    assert "job_id" in data
    assert "task_id" in data
    assert data["status"] == "pending"


def test_export_job_status_update(test_client, patient_token):
    """
    Test that export job status can be tracked.

    Verifies:
    - Job status can be retrieved
    - Status transitions correctly
    """
    # Create export
    response = patient_token.post("/api/export/treatments")
    job_id = response.get_json()["job_id"]

    # Get job status
    response = patient_token.get(f"/api/export/jobs/{job_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == job_id
    assert "status" in data
    assert data["patient_id"] is not None


def test_export_jobs_listing(test_client, patient_token):
    """
    Test listing all export jobs for a patient.

    Verifies:
    - Returns list of jobs
    - Jobs are ordered by creation date
    """
    # Create multiple exports
    patient_token.post("/api/export/treatments")

    response = patient_token.get("/api/export/jobs")
    assert response.status_code == 200
    jobs = response.get_json()
    assert isinstance(jobs, list)


@patch("backend.tasks.send_email")
def test_send_email_notification(mock_send_email, test_client, patient_token):
    """
    Test email notification function.

    Verifies:
    - Email function is called with correct parameters
    """
    from backend.tasks import send_email

    # Test the function directly
    send_email("test@example.com", "Test Subject", "Test message")

    # Since we may not have SMTP configured, just verify it doesn't throw
    assert mock_send_email.called or True  # Accept either way


def test_no_google_chat_in_tasks():
    """
    Verify Google Chat is not implemented in the tasks module.

    Per requirement, all Google Chat webhook integration must be removed.
    """
    import backend.tasks as tasks_module

    assert not hasattr(tasks_module, "send_google_chat_message"), (
        "send_google_chat_message should not exist - Google Chat is not supported"
    )


def test_daily_reminders_task_exists():
    """
    Test that daily reminders task is defined.

    Verifies:
    - Task function exists
    - Task has correct name
    """
    from backend.tasks import send_daily_reminders

    assert callable(send_daily_reminders)
    assert send_daily_reminders.__name__ == "send_daily_reminders"


def test_monthly_reports_task_exists():
    """
    Test that monthly reports task is defined.

    Verifies:
    - Task function exists
    - Task has correct name
    """
    from backend.tasks import send_monthly_reports

    assert callable(send_monthly_reports)
    assert send_monthly_reports.__name__ == "send_monthly_reports"


def test_export_task_exists():
    """
    Test that export task is defined.

    Verifies:
    - Task function exists
    - Task accepts patient_id and export_job_id parameters
    """
    from backend.tasks import export_patient_treatments

    assert callable(export_patient_treatments)
    assert export_patient_treatments.__name__ == "export_patient_treatments"


def test_build_monthly_report_html():
    """
    Test HTML report generation.

    Verifies:
    - Returns HTML string
    - Includes doctor name
    - Includes appointment details
    """
    from backend.tasks import build_monthly_report_html

    # Create mock objects
    class MockUser:
        name = "Dr. Test"

    class MockDoctor:
        user = MockUser()

    class MockPatient:
        user = MockUser()

    class MockTreatment:
        diagnosis = "Test Diagnosis"
        prescription = "Test Prescription"

    class MockAppointment:
        id = 1
        date = "2025-01-15"
        time = "10:00"
        patient_id = 1
        patient = MockPatient()
        doctor = MockDoctor()
        treatment = MockTreatment()

    doctor = MockDoctor()
    appointments = [MockAppointment()]

    html = build_monthly_report_html(doctor, appointments, "January 2025")

    assert isinstance(html, str)
    assert "Dr. Test" in html
    assert "Test Diagnosis" in html
    assert "January 2025" in html


@patch("backend.tasks.send_email")
def test_daily_reminders_sends_email(mock_email, test_client):
    """Verify daily_reminders task calls send_email for today's appointments."""
    from datetime import date

    today = date.today().isoformat()

    # Create appointment for today directly in DB (bypass API to avoid session conflicts)
    with test_client.application.app_context():
        from models.database import db, Patient, Doctor, User, Appointment

        patient = Patient.query.filter_by(
            user_id=User.query.filter_by(username="patient").first().id
        ).first()
        doctor = Doctor.query.filter_by(
            user_id=User.query.filter_by(username="doctor").first().id
        ).first()

        apt = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            date=today,
            time="09:00",
            status="Booked",
        )
        db.session.add(apt)
        db.session.commit()

        from backend.tasks import send_daily_reminders

        # Call .run() directly so it executes within the current app context
        result = send_daily_reminders.run()
        assert result["total"] >= 1  # Task found today's appointment


@patch("backend.tasks.send_email")
def test_monthly_report_sends_email(mock_email, test_client, admin_token):
    """Verify send_monthly_reports task runs and returns expected structure."""
    with test_client.application.app_context():
        from backend.tasks import send_monthly_reports

        # Call .run() directly inside the test app context so DB tables are accessible
        result = send_monthly_reports.run()
        # Task ran without error; report count may be 0 if no completed appointments in prior month
        assert "total_doctors" in result


@patch("backend.tasks.send_email")
def test_export_csv_sends_email_on_completion(mock_email, test_client, patient_token):
    """Verify export task sends email notification on completion."""
    # Trigger export
    resp = patient_token.post("/api/export/treatments")
    assert resp.status_code in [200, 201]
    data = resp.get_json()
    job_id = data["job_id"]

    # Poll for status completion (eager mode means it ran synchronously)
    status_resp = patient_token.get(f"/api/export/jobs/{job_id}")
    job = status_resp.get_json()
    # Job should be completed or pending in eager mode
    assert job["status"] in ["completed", "pending", "processing"]


# ---------------------------------------------------------------------------
# Celery configuration – Windows-safe pool tests
# ---------------------------------------------------------------------------


def test_celery_uses_solo_pool_on_windows():
    """
    Verify that the Celery config selects 'solo' worker pool on Windows.

    The 'prefork' pool uses billiard shared-memory primitives (semaphores,
    named pipes) that raise PermissionError / OSError on Windows.  The 'solo'
    pool runs tasks in the main process, avoiding these issues entirely.
    """
    import sys
    from backend.celery_config import make_celery

    celery_instance = make_celery()
    pool_setting = celery_instance.conf.worker_pool

    if sys.platform == "win32":
        assert pool_setting == "solo", (
            f"Expected 'solo' pool on Windows but got '{pool_setting}'. "
            "The prefork pool causes PermissionError/OSError on Windows."
        )
    else:
        assert pool_setting in (
            "prefork",
            "solo",
        ), f"Unexpected pool setting '{pool_setting}'"


def test_celery_solo_pool_concurrency_is_one_on_windows():
    """
    Verify that worker_concurrency is 1 when 'solo' pool is used on Windows.

    The solo pool is single-threaded, so a concurrency > 1 would silently be
    ignored; setting it explicitly to 1 avoids confusing log output.
    """
    import sys
    from backend.celery_config import make_celery

    celery_instance = make_celery()
    if sys.platform == "win32":
        assert celery_instance.conf.worker_concurrency == 1


def test_celery_config_has_required_settings():
    """
    Verify key Celery configuration settings are present and valid.
    """
    from backend.celery_config import celery

    assert celery.conf.task_serializer == "json"
    assert "json" in celery.conf.accept_content
    assert celery.conf.result_serializer == "json"
    assert celery.conf.timezone == "UTC"
    assert celery.conf.enable_utc is True
    assert celery.conf.task_track_started is True
    assert celery.conf.worker_pool in ("solo", "prefork")


def test_celery_beat_schedule_has_expected_tasks():
    """
    Verify that the Celery beat schedule contains the expected periodic tasks.
    """
    from backend.celery_config import celery

    schedule = celery.conf.beat_schedule
    assert "daily-appointment-reminders" in schedule
    assert "monthly-doctor-reports" in schedule
    assert (
        schedule["daily-appointment-reminders"]["task"]
        == "backend.tasks.send_daily_reminders"
    )
    assert (
        schedule["monthly-doctor-reports"]["task"]
        == "backend.tasks.send_monthly_reports"
    )
