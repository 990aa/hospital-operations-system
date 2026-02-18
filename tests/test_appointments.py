"""
Appointment and Patient Tests.

Tests for:
- Appointment booking with conflict prevention
- Appointment status updates
- Doctor viewing patient history
- Treatment records
- Profile updates

Author: Abdul Ahad
"""

from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from models.database import db, Appointment, Patient, Doctor, User, ExportJob


def login(client, username, password):
    return client.post("/api/login", json={"username": username, "password": password})


def test_book_appointment_success(test_client):
    """
    Test successful appointment booking.
    """
    login(test_client, "patient", "patientpassword")

    # Get doctors
    resp = test_client.get("/api/doctors")
    doctors = resp.get_json()
    assert resp.status_code == 200
    assert len(doctors) > 0
    doctor_id = doctors[0]["id"]

    # Book tomorrow
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    response = test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert "appointment_id" in data
    assert "assigned_time" in data


def test_book_appointment_past_date(test_client):
    """
    Test booking appointment in the past.
    """
    login(test_client, "patient", "patientpassword")
    resp = test_client.get("/api/doctors")
    doctor_id = resp.get_json()[0]["id"]

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    response = test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": yesterday},
    )
    assert response.status_code == 400


def test_book_appointment_serial_slots_for_same_doctor(test_client):
    """Test serial slot assignment for same doctor/day."""
    login(test_client, "patient", "patientpassword")
    resp = test_client.get("/api/doctors")
    doctor_id = resp.get_json()[0]["id"]

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # First booking
    first = test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow},
    )
    assert first.status_code == 201

    second = test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow},
    )
    assert second.status_code == 201
    assert first.get_json()["assigned_time"] != second.get_json()["assigned_time"]


def test_complete_appointment(test_client):
    """
    Test completing an appointment.
    """
    # Patient books
    login(test_client, "patient", "patientpassword")
    resp = test_client.get("/api/doctors")
    doctor_id = resp.get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow},
    )

    # Patient pays before consultation completion.
    appointment_id = test_client.get("/api/my-appointments").get_json()[0]["id"]
    pay_response = test_client.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={
            "amount": 500,
            "payment_method": "credit_card",
            "card_number": "1111222233334444",
        },
    )
    assert pay_response.status_code == 201

    # Doctor completes it
    login(test_client, "doctor", "docpassword")
    resp = test_client.get("/api/doctor/appointments")
    appointments = resp.get_json()
    assert resp.status_code == 200
    booked = [a for a in appointments if a["status"] == "Booked"]
    assert len(booked) > 0

    appointment_id = booked[0]["id"]
    response = test_client.post(
        f"/api/appointments/{appointment_id}/complete",
        json={"diagnosis": "Test diagnosis", "prescription": "Test prescription"},
    )
    assert response.status_code == 200


def test_doctor_view_patient_summary(test_client):
    """
    Test doctor viewing patient summary.
    """
    # Patient books with doctor
    login(test_client, "patient", "patientpassword")
    resp = test_client.get("/api/doctors")
    doctor_id = resp.get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow},
    )

    # Get patient ID
    resp = test_client.get("/api/my-appointments")
    patient_id = resp.get_json()[0]["patient_id"]

    # Doctor views summary
    login(test_client, "doctor", "docpassword")
    response = test_client.get(f"/api/doctor/patients/{patient_id}/summary")
    assert response.status_code == 200
    data = response.get_json()
    assert "patient" in data


def test_patient_export_trigger(test_client):
    """
    Test patient triggering CSV export.
    """
    login(test_client, "patient", "patientpassword")
    response = test_client.post("/api/export/treatments")
    assert response.status_code in [200, 201]
    data = response.get_json()
    assert "job_id" in data


def test_book_appointment_outside_7_day_window(test_client):
    """Test appointments cannot be booked outside upcoming 7 days."""
    login(test_client, "patient", "patientpassword")
    resp = test_client.get("/api/doctors")
    doctor_id = resp.get_json()[0]["id"]
    outside_range = (datetime.now() + timedelta(days=8)).strftime("%Y-%m-%d")
    response = test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": outside_range},
    )
    assert response.status_code == 400


def test_cancel_appointment_patient(test_client):
    """
    Test patient cancelling their appointment.
    """
    login(test_client, "patient", "patientpassword")
    resp = test_client.get("/api/doctors")
    doctor_id = resp.get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow},
    )

    resp = test_client.get("/api/my-appointments")
    appointments = resp.get_json()
    appointment_id = appointments[0]["id"]

    response = test_client.post(f"/api/appointments/{appointment_id}/cancel")
    assert response.status_code == 200


def test_doctor_view_patient_full_history(test_client):
    """
    Test doctor viewing patient full history.
    """
    login(test_client, "patient", "patientpassword")
    resp = test_client.get("/api/doctors")
    doctor_id = resp.get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow},
    )

    # Get patient ID
    resp = test_client.get("/api/my-appointments")
    patient_id = resp.get_json()[0]["patient_id"]
    appointment_id = resp.get_json()[0]["id"]

    # Pay before doctor can complete.
    test_client.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={
            "amount": 400,
            "payment_method": "debit_card",
            "card_number": "9999000011112222",
        },
    )

    # Complete it
    login(test_client, "doctor", "docpassword")
    test_client.post(
        f"/api/appointments/{appointment_id}/complete",
        json={"diagnosis": "History test", "prescription": "Meds"},
    )

    # View history
    response = test_client.get(f"/api/doctor/patients/{patient_id}/history")
    assert response.status_code == 200
    assert "appointments" in response.get_json()


def test_patient_update_profile(test_client):
    """
    Test patient updating profile.
    """
    login(test_client, "patient", "patientpassword")
    response = test_client.post(
        "/api/profile",
        json={
            "name": "New Name",
            "email": "new@test.com",
            "phone": "1231231234",
            "history": "None",
            "notification_pref": "sms",
        },
    )
    assert response.status_code == 200


def test_search_doctors(test_client):
    """
    Test searching doctors.
    """
    login(test_client, "patient", "patientpassword")
    # Search by name
    response = test_client.get("/api/doctors?search=Doctor")
    assert response.status_code == 200
    assert len(response.get_json()) > 0

    # Search by specialization
    response = test_client.get("/api/doctors?search=General")
    assert response.status_code == 200
    assert len(response.get_json()) > 0


def test_doctor_availability_next_7_days_endpoint(test_client):
    """Test doctor-specific upcoming availability endpoint."""
    login(test_client, "patient", "patientpassword")
    doctors = test_client.get("/api/doctors").get_json()
    doctor_id = doctors[0]["id"]

    response = test_client.get(f"/api/doctors/{doctor_id}/availability")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["availability"]) == 7
    assert "remaining_slots" in data["availability"][0]


def test_profile_update_reflects_in_get_profile(test_client):
    """Test patient profile updates are retrievable immediately."""
    login(test_client, "patient", "patientpassword")
    update_response = test_client.post(
        "/api/profile",
        json={
            "name": "Updated Patient",
            "email": "updated.patient@test.com",
            "phone": "9998887777",
            "history": "Updated medical history",
            "notification_pref": "chat",
        },
    )
    assert update_response.status_code == 200

    profile_response = test_client.get("/api/profile")
    assert profile_response.status_code == 200
    profile = profile_response.get_json()
    assert profile["name"] == "Updated Patient"
    assert profile["email"] == "updated.patient@test.com"
    assert profile["notification_pref"] == "chat"


def test_doctor_cannot_complete_without_payment(test_client):
    """Doctor completion requires successful pre-payment."""
    login(test_client, "patient", "patientpassword")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post("/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow})

    login(test_client, "doctor", "docpassword")
    appointment_id = test_client.get("/api/doctor/appointments").get_json()[0]["id"]
    response = test_client.post(
        f"/api/appointments/{appointment_id}/complete",
        json={"diagnosis": "No pay", "prescription": "None"},
    )
    assert response.status_code == 400


def test_patient_cancel_triggers_refund_record(test_client):
    """Paid appointment cancellation should produce refund record."""
    login(test_client, "patient", "patientpassword")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post("/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow})

    appointment_id = test_client.get("/api/my-appointments").get_json()[0]["id"]
    test_client.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={
            "amount": 450,
            "payment_method": "credit_card",
            "card_number": "5555666677778888",
        },
    )

    cancel_response = test_client.post(f"/api/appointments/{appointment_id}/cancel")
    assert cancel_response.status_code == 200

    payments = test_client.get("/api/patient/payments").get_json()
    statuses = [payment["status"] for payment in payments]
    assert "completed" in statuses
    assert "refunded" in statuses


def test_admin_and_doctor_payment_visibility_endpoints(test_client):
    """Admin and doctor should view payment summary/ledger endpoints."""
    login(test_client, "patient", "patientpassword")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post("/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow})
    appointment_id = test_client.get("/api/my-appointments").get_json()[0]["id"]
    test_client.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={
            "amount": 500,
            "payment_method": "credit_card",
            "card_number": "1234123412341234",
        },
    )

    login(test_client, "admin", "admin")
    admin_response = test_client.get("/api/admin/payments")
    assert admin_response.status_code == 200
    admin_payload = admin_response.get_json()
    assert "payments" in admin_payload
    assert "summary" in admin_payload

    login(test_client, "doctor", "docpassword")
    doctor_response = test_client.get("/api/doctor/payments")
    assert doctor_response.status_code == 200
    doctor_payload = doctor_response.get_json()
    assert "payments" in doctor_payload
    assert "summary" in doctor_payload


def test_doctor_monthly_report_handles_string_dates(test_client):
    """Monthly report endpoint should not fail on string-based appointment dates."""
    login(test_client, "doctor", "docpassword")
    today = datetime.now()
    response = test_client.get(f"/api/doctor/monthly-report/{today.month}/{today.year}")
    assert response.status_code == 200


def test_complete_with_follow_up_schedules_next_visit(test_client):
    """Doctor completion should optionally auto-book follow-up using same slot policy."""
    login(test_client, "patient", "patientpassword")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post("/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow})

    appointment_id = test_client.get("/api/my-appointments").get_json()[0]["id"]
    test_client.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={"amount": 500, "payment_method": "credit_card", "card_number": "1111222233334444"},
    )

    login(test_client, "doctor", "docpassword")
    follow_up_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    response = test_client.post(
        f"/api/appointments/{appointment_id}/complete",
        json={
            "diagnosis": "Needs review",
            "prescription": "Continue meds",
            "notes": "Follow-up required",
            "next_visit_date": follow_up_date,
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["follow_up"] is not None

    login(test_client, "patient", "patientpassword")
    apps = test_client.get("/api/my-appointments").get_json()
    follow_ups = [a for a in apps if a.get("is_follow_up")]
    assert follow_ups


def test_export_contains_data_rows_not_only_headers(test_client):
    """CSV export should include appointment rows even when only booked appointments exist."""
    login(test_client, "patient", "patientpassword")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post("/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow})

    trigger = test_client.post("/api/export/treatments")
    assert trigger.status_code in [200, 201]
    job_id = trigger.get_json()["job_id"]

    with test_client.application.app_context():
        job = ExportJob.query.get(job_id)
        assert job is not None
        assert job.file_path is not None
        with open(job.file_path, "r", encoding="utf-8") as handle:
            lines = [line.strip() for line in handle.readlines() if line.strip()]
        assert len(lines) > 1


def test_unique_constraint_blocks_duplicate_doctor_slot(test_client):
    """DB-level unique constraint must block duplicate doctor/date/time rows."""
    with test_client.application.app_context():
        patient = Patient.query.filter_by(
            user_id=User.query.filter_by(username="patient").first().id
        ).first()
        doctor = Doctor.query.filter_by(
            user_id=User.query.filter_by(username="doctor").first().id
        ).first()

        a1 = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            date="2026-12-25",
            time="10:00",
            status="Booked",
        )
        db.session.add(a1)
        db.session.commit()

        a2 = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            date="2026-12-25",
            time="10:00",
            status="Booked",
        )
        db.session.add(a2)
        raised = False
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raised = True

        assert raised
