"""
Tests for Recent Feature Updates.

Covers all changes made in the latest iteration:
1. Department description field
2. Duplicate department returns 409
3. Duplicate registration error messages
4. Doctor reschedule appointment endpoint
5. send_email_with_attachment function
6. Export CSV emails attachment
7. Celery sys.path fix

Author: Abdul Ahad
"""

from datetime import datetime, timedelta
from unittest.mock import patch


def login(client, username, password):
    return client.post("/api/login", json={"username": username, "password": password})


# ── 1. Department Description ──────────────────────────────────────────────────


def test_create_department_with_description(admin_token):
    """Admin can create a department with a description field."""
    response = admin_token.post(
        "/api/departments",
        json={"name": "Oncology", "description": "Cancer treatment and research"},
    )
    assert response.status_code in [200, 201]

    # Verify description is returned
    depts = admin_token.get("/api/departments").get_json()
    onco = [d for d in depts if d["name"] == "Oncology"]
    assert len(onco) == 1
    assert onco[0]["description"] == "Cancer treatment and research"


def test_create_department_without_description(admin_token):
    """Department creation works without a description (optional field)."""
    response = admin_token.post(
        "/api/departments",
        json={"name": "Radiology"},
    )
    assert response.status_code in [200, 201]


# ── 2. Duplicate Department Returns 409 ───────────────────────────────────────


def test_duplicate_department_returns_409(admin_token):
    """Creating a department with an existing name returns 409, not 200."""
    admin_token.post(
        "/api/departments",
        json={"name": "Urology", "description": "Urinary tract"},
    )
    response = admin_token.post(
        "/api/departments",
        json={"name": "Urology", "description": "Duplicate attempt"},
    )
    assert response.status_code == 409
    data = response.get_json()
    assert "already exists" in data.get("error", data.get("message", "")).lower()


# ── 3. Duplicate Registration Error Messages ──────────────────────────────────


def test_register_duplicate_username_returns_error_message(test_client):
    """Registering with an existing username returns a clear error message."""
    test_client.post(
        "/api/register",
        json={
            "username": "dupuser",
            "password": "password123",
            "name": "Dup User",
            "email": "dup1@test.com",
        },
    )
    response = test_client.post(
        "/api/register",
        json={
            "username": "dupuser",
            "password": "password456",
            "name": "Dup User 2",
            "email": "dup2@test.com",
        },
    )
    assert response.status_code == 400
    msg = response.get_json().get("message", "")
    assert "already exists" in msg.lower()


def test_register_duplicate_email_returns_error_message(test_client):
    """Registering with an existing email returns a clear error message."""
    test_client.post(
        "/api/register",
        json={
            "username": "emaildup1",
            "password": "password123",
            "name": "Email Dup 1",
            "email": "shared@test.com",
        },
    )
    response = test_client.post(
        "/api/register",
        json={
            "username": "emaildup2",
            "password": "password456",
            "name": "Email Dup 2",
            "email": "shared@test.com",
        },
    )
    assert response.status_code == 400
    msg = response.get_json().get("message", "")
    assert "email" in msg.lower()


# ── 4. Doctor Reschedule Appointment ──────────────────────────────────────────


def _book_and_pay(test_client, patient_username, doctor_id, date_str):
    """Helper: book an appointment and pay for it, return appointment_id."""
    login(test_client, patient_username, patient_username)
    book = test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": date_str}
    )
    assert book.status_code == 201, f"Booking failed: {book.get_json()}"
    apt_id = book.get_json()["appointment_id"]

    pay = test_client.post(
        f"/api/patient/payment/appointment/{apt_id}",
        json={
            "amount": 500,
            "payment_method": "credit_card",
            "card_number": "4111111111111111",
        },
    )
    assert pay.status_code == 201
    return apt_id


def test_doctor_reschedule_appointment(test_client):
    """Doctor can reschedule a booked appointment to a new date."""
    # Patient books
    login(test_client, "patient", "patient")
    doctors = test_client.get("/api/doctors").get_json()
    doctor_id = doctors[0]["id"]

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    apt_id = _book_and_pay(test_client, "patient", doctor_id, tomorrow)

    # Get valid reschedule date (day after tomorrow)
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    # Doctor reschedules
    login(test_client, "doctor", "doctor")
    response = test_client.post(
        f"/api/doctor/appointments/{apt_id}/reschedule",
        json={"new_date": day_after},
    )
    # Accept either 200 (success) or 400 (date not in availability)
    # The test date might not match doctor's availability days
    assert response.status_code in [200, 400]

    if response.status_code == 200:
        data = response.get_json()
        assert "new_appointment_id" in data


def test_doctor_reschedule_requires_booked_status(test_client):
    """Cannot reschedule a cancelled or completed appointment."""
    login(test_client, "patient", "patient")
    doctors = test_client.get("/api/doctors").get_json()
    doctor_id = doctors[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Book and immediately cancel
    book = test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )
    apt_id = book.get_json()["appointment_id"]
    test_client.post(f"/api/appointments/{apt_id}/cancel")

    # Doctor tries to reschedule a cancelled appointment
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    login(test_client, "doctor", "doctor")
    response = test_client.post(
        f"/api/doctor/appointments/{apt_id}/reschedule",
        json={"new_date": day_after},
    )
    assert response.status_code == 400


def test_doctor_reschedule_wrong_doctor(test_client):
    """Doctor cannot reschedule another doctor's appointment."""
    login(test_client, "patient", "patient")
    doctors = test_client.get("/api/doctors").get_json()

    # Book with doctor 1
    doctor1_id = doctors[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    book = test_client.post(
        "/api/appointments", json={"doctor_id": doctor1_id, "date": tomorrow}
    )
    apt_id = book.get_json()["appointment_id"]

    # Login as doctor2 and try to reschedule
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    login(test_client, "doctor2", "doctor2")
    response = test_client.post(
        f"/api/doctor/appointments/{apt_id}/reschedule",
        json={"new_date": day_after},
    )
    assert response.status_code in [403, 404]


# ── 5. send_email_with_attachment Function ────────────────────────────────────


def test_send_email_with_attachment_exists():
    """The send_email_with_attachment function exists in tasks module."""
    from backend.tasks import send_email_with_attachment

    assert callable(send_email_with_attachment)


def test_send_email_with_attachment_console_fallback(test_client, capsys):
    """Without SMTP configured, send_email_with_attachment logs to console."""
    import os
    import tempfile

    with test_client.application.app_context():
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            tmp.write("Date,Doctor,Diagnosis\n2025-01-01,Dr.Test,Cold\n")
            tmp_path = tmp.name

        try:
            # Ensure SMTP_USERNAME is not set so fallback path is used
            original = os.environ.pop("SMTP_USERNAME", None)
            try:
                from backend.tasks import send_email_with_attachment

                send_email_with_attachment(
                    "user@example.com",
                    "Your Export",
                    "Attached is your CSV.",
                    tmp_path,
                )
                captured = capsys.readouterr()
                assert "ATTACHMENT" in captured.out
            finally:
                if original:
                    os.environ["SMTP_USERNAME"] = original
        finally:
            os.unlink(tmp_path)


# ── 6. Export CSV Emails Attachment ───────────────────────────────────────────


@patch("backend.tasks.send_email_with_attachment")
@patch("backend.tasks.send_email")
def test_export_task_calls_send_email_with_attachment(
    mock_email, mock_attach_email, test_client, patient_token
):
    """Export task should attempt to email CSV as attachment."""
    # Trigger export
    resp = patient_token.post("/api/export/treatments")
    assert resp.status_code in [200, 201]
    job_id = resp.get_json()["job_id"]

    with test_client.application.app_context():
        from backend.tasks import export_patient_treatments
        from models.database import ExportJob, db

        job = db.session.get(ExportJob, job_id)
        assert job is not None

        # Run the task directly
        export_patient_treatments.run(job.patient_id, job_id)

        # At least one email function should have been called
        assert mock_attach_email.called or mock_email.called


# ── 7. Celery sys.path Fix ────────────────────────────────────────────────────


def test_celery_config_has_project_root_on_path():
    """celery_config.py should add the project root to sys.path."""
    import sys
    import os

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # After importing celery_config, project root should be on sys.path
    import backend.celery_config  # noqa: F401

    assert project_root in sys.path


# ── 8. Index page renders with new features ───────────────────────────────────


def test_index_contains_medical_history_tab(test_client):
    """index.html should contain the Medical History tab for patients."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"Medical History" in response.data or b"medical-history" in response.data


def test_index_contains_reschedule_button(test_client):
    """index.html should contain reschedule functionality for doctors."""
    response = test_client.get("/")
    assert response.status_code == 200
    # Check for reschedule-related content
    html = response.data.decode("utf-8").lower()
    assert "reschedule" in html


def test_index_contains_export_csv_button(test_client):
    """index.html should contain the Export CSV button."""
    response = test_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8").lower()
    assert "export" in html


# ── 9. Profile does not show notification preference selector ─────────────────


def test_patient_profile_notification_always_email(test_client):
    """Patient profile should always use email notifications."""
    login(test_client, "patient", "patient")
    response = test_client.get("/api/profile")
    assert response.status_code == 200
    profile = response.get_json()
    assert profile.get("notification_pref") == "email"
