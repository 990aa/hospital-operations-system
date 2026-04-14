"""
Appointment and Patient Tests.

Tests for:
- Appointment booking with conflict prevention
- Appointment status updates
- Doctor viewing patient history
- Treatment records
- Profile updates
- Concurrent booking by multiple patients
- Multi-doctor multi-department scenarios

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
    login(test_client, "patient", "patient")

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
    login(test_client, "patient", "patient")
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
    login(test_client, "patient", "patient")
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
    login(test_client, "patient", "patient")
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
    login(test_client, "doctor", "doctor")
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
    login(test_client, "patient", "patient")
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
    login(test_client, "doctor", "doctor")
    response = test_client.get(f"/api/doctor/patients/{patient_id}/summary")
    assert response.status_code == 200
    data = response.get_json()
    assert "patient" in data


def test_patient_export_trigger(test_client):
    """
    Test patient triggering CSV export.
    """
    login(test_client, "patient", "patient")
    response = test_client.post("/api/export/treatments")
    assert response.status_code in [200, 201]
    data = response.get_json()
    assert "job_id" in data


def test_book_appointment_outside_7_day_window(test_client):
    """Test appointments cannot be booked outside upcoming 7 days."""
    login(test_client, "patient", "patient")
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
    login(test_client, "patient", "patient")
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
    login(test_client, "patient", "patient")
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
    login(test_client, "doctor", "doctor")
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
    login(test_client, "patient", "patient")
    response = test_client.post(
        "/api/profile",
        json={
            "name": "New Name",
            "email": "new@test.com",
            "phone": "1231231234",
            "history": "None",
            "notification_pref": "email",
        },
    )
    assert response.status_code == 200


def test_search_doctors(test_client):
    """
    Test searching doctors.
    """
    login(test_client, "patient", "patient")
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
    login(test_client, "patient", "patient")
    doctors = test_client.get("/api/doctors").get_json()
    doctor_id = doctors[0]["id"]

    response = test_client.get(f"/api/doctors/{doctor_id}/availability")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["availability"]) == 7
    assert "remaining_slots" in data["availability"][0]


def test_profile_update_reflects_in_get_profile(test_client):
    """Test patient profile updates are retrievable immediately."""
    login(test_client, "patient", "patient")
    update_response = test_client.post(
        "/api/profile",
        json={
            "name": "Updated Patient",
            "email": "updated.patient@test.com",
            "phone": "9998887777",
            "notification_pref": "email",
        },
    )
    assert update_response.status_code == 200

    profile_response = test_client.get("/api/profile")
    assert profile_response.status_code == 200
    profile = profile_response.get_json()
    assert profile["name"] == "Updated Patient"
    assert profile["email"] == "updated.patient@test.com"
    assert profile["notification_pref"] == "email"


def test_doctor_cannot_complete_without_payment(test_client):
    """Doctor completion requires successful pre-payment."""
    login(test_client, "patient", "patient")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )

    login(test_client, "doctor", "doctor")
    appointment_id = test_client.get("/api/doctor/appointments").get_json()[0]["id"]
    response = test_client.post(
        f"/api/appointments/{appointment_id}/complete",
        json={"diagnosis": "No pay", "prescription": "None"},
    )
    assert response.status_code == 400


def test_patient_cancel_triggers_refund_record(test_client):
    """Paid appointment cancellation should produce refund record."""
    login(test_client, "patient", "patient")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )

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
    login(test_client, "patient", "patient")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )
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

    login(test_client, "doctor", "doctor")
    doctor_response = test_client.get("/api/doctor/payments")
    assert doctor_response.status_code == 200
    doctor_payload = doctor_response.get_json()
    assert "payments" in doctor_payload
    assert "summary" in doctor_payload


def test_doctor_monthly_report_handles_string_dates(test_client):
    """Monthly report endpoint should not fail on string-based appointment dates."""
    login(test_client, "doctor", "doctor")
    today = datetime.now()
    response = test_client.get(f"/api/doctor/monthly-report/{today.month}/{today.year}")
    assert response.status_code == 200


def test_complete_with_follow_up_schedules_next_visit(test_client):
    """Doctor completion should optionally auto-book follow-up using same slot policy."""
    login(test_client, "patient", "patient")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )

    appointment_id = test_client.get("/api/my-appointments").get_json()[0]["id"]
    test_client.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={
            "amount": 500,
            "payment_method": "credit_card",
            "card_number": "1111222233334444",
        },
    )

    # Select a valid availability date for deterministic follow-up scheduling.
    availability = test_client.get(f"/api/doctors/{doctor_id}/availability").get_json()[
        "availability"
    ]
    candidate_dates = [
        day["date"]
        for day in availability
        if day.get("remaining_slots", 0) > 0 and day["date"] != tomorrow
    ]
    follow_up_date = candidate_dates[0] if candidate_dates else tomorrow

    login(test_client, "doctor", "doctor")
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

    login(test_client, "patient", "patient")
    apps = test_client.get("/api/my-appointments").get_json()
    follow_ups = [a for a in apps if a.get("is_follow_up")]
    assert follow_ups


def test_export_contains_data_rows_not_only_headers(test_client):
    """CSV export should include appointment rows even when only booked appointments exist."""
    login(test_client, "patient", "patient")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )

    trigger = test_client.post("/api/export/treatments")
    assert trigger.status_code in [200, 201]
    job_id = trigger.get_json()["job_id"]

    with test_client.application.app_context():
        from backend.tasks import export_patient_treatments

        job = ExportJob.query.get(job_id)
        assert job is not None
        export_patient_treatments.run(job.patient_id, job_id)
        db.session.refresh(job)
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


def test_admin_slot_minutes_accepts_any_value_between_10_and_60(admin_token):
    """Doctor creation should allow slot minutes in [10, 60]."""
    dept_id = admin_token.get("/api/departments").get_json()[0]["id"]

    ok_response = admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Flexible Slot Doctor",
            "username": "flexslotdoc",
            "password": "flexslotdoc",
            "department_id": dept_id,
            "slot_minutes": 17,
        },
    )
    assert ok_response.status_code == 201

    bad_response = admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Invalid Slot Doctor",
            "username": "invalidslotdoc",
            "password": "invalidslotdoc",
            "department_id": dept_id,
            "slot_minutes": 9,
        },
    )
    assert bad_response.status_code == 422


def test_doctor_can_update_availability_schedule(test_client):
    """Doctor should be able to update next-7-day schedule settings."""
    login(test_client, "doctor", "doctor")
    response = test_client.put(
        "/api/doctor/availability",
        json={
            "availability_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            "availability_start": "08:00",
            "availability_end": "12:00",
            "slot_minutes": 20,
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["doctor"]["slot_minutes"] == 20


def test_doctor_can_update_completed_treatment(test_client):
    """Doctor should be able to revise diagnosis/prescription for completed visits."""
    login(test_client, "patient", "patient")
    doctor_id = test_client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    test_client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )

    appointment_id = test_client.get("/api/my-appointments").get_json()[0]["id"]
    test_client.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={
            "amount": 500,
            "payment_method": "credit_card",
            "card_number": "1234123412341234",
        },
    )

    login(test_client, "doctor", "doctor")
    complete = test_client.post(
        f"/api/appointments/{appointment_id}/complete",
        json={
            "diagnosis": "Initial",
            "prescription": "Initial Rx",
            "notes": "Initial note",
        },
    )
    assert complete.status_code == 200

    update = test_client.put(
        f"/api/doctor/appointments/{appointment_id}/treatment",
        json={
            "diagnosis": "Updated",
            "prescription": "Updated Rx",
            "notes": "Updated note",
        },
    )
    assert update.status_code == 200
    assert update.get_json()["treatment"]["diagnosis"] == "Updated"


# ── Multi-doctor / multi-department / concurrent booking tests ─────────────────


def test_multiple_departments_exist(test_client):
    """Conftest creates 4 departments; verify all are present."""
    login(test_client, "admin", "admin")
    resp = test_client.get("/api/departments")
    assert resp.status_code == 200
    depts = resp.get_json()
    assert len(depts) >= 4, f"Expected ≥4 departments, got {len(depts)}"
    dept_names = [d["name"] for d in depts]
    assert "General Medicine" in dept_names
    assert "Cardiology" in dept_names
    assert "Neurology" in dept_names
    assert "Orthopedics" in dept_names


def test_multiple_doctors_across_departments(test_client):
    """Conftest creates doctors in different departments; verify via patient API."""
    login(test_client, "patient", "patient")
    resp = test_client.get("/api/doctors")
    assert resp.status_code == 200
    doctors = resp.get_json()
    assert len(doctors) >= 4, f"Expected ≥4 doctors, got {len(doctors)}"
    depts_represented = {d["department"] for d in doctors if d.get("department")}
    assert len(depts_represented) >= 4, (
        f"Expected doctors from ≥4 departments, got: {depts_represented}"
    )


def test_multiple_patients_can_all_book_same_doctor(test_client):
    """Patient 1, 2 and 3 can each book the same doctor on different slots same day."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    results = {}

    for uname in ["patient", "patient2", "patient3"]:
        login(test_client, uname, uname)
        doctors = test_client.get("/api/doctors").get_json()
        doctor_id = doctors[0]["id"]
        resp = test_client.post(
            "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
        )
        results[uname] = resp.status_code

    # All three bookings should succeed
    for uname, code in results.items():
        assert code == 201, f"{uname} booking failed with {code}"

    # All assigned times should be distinct
    times = []
    for uname in ["patient", "patient2", "patient3"]:
        login(test_client, uname, uname)
        apts = test_client.get("/api/my-appointments").get_json()
        booked = [a["time"] for a in apts if a["status"] == "Booked"]
        times.extend(booked)

    # Check no two are the same
    assert len(times) == len(set(times)), f"Duplicate slot times assigned: {times}"


def test_concurrent_booking_same_doctor_same_day(test_client):
    """
    Simulate two patients racing to book the same doctor/day.

    True OS threading with in-memory SQLite isn't safe in tests
    (scoped sessions are thread-local), so we simulate the race by having
    both patients book sequentially and verifying the system assigns
    unique, non-conflicting time slots - demonstrating the serialisation
    logic that would protect against real concurrent writes.
    """
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    app = test_client.application

    client1 = app.test_client()
    client2 = app.test_client()

    login(client1, "patient2", "patient2")
    login(client2, "patient3", "patient3")

    # Get a doctor both patients will target
    doctors = client1.get("/api/doctors").get_json()
    doctor_id = doctors[0]["id"]

    # Sequential booking simulation (same doctor, same day)
    resp1 = client1.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )
    resp2 = client2.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )

    assert resp1.status_code == 201, f"patient2 booking failed: {resp1.get_json()}"
    assert resp2.status_code == 201, f"patient3 booking failed: {resp2.get_json()}"

    # Slots must differ - system serialises slot assignment
    time1 = resp1.get_json().get("assigned_time")
    time2 = resp2.get_json().get("assigned_time")
    assert time1 != time2, f"Both patients got the same slot: {time1}"


def test_patient_can_book_doctors_in_different_departments(test_client):
    """A single patient should be able to book appointments with doctors from different departments."""
    login(test_client, "patient", "patient")
    doctors = test_client.get("/api/doctors").get_json()
    # Pick two doctors from different departments
    seen_depts = set()
    selected = []
    for doc in doctors:
        dept = doc.get("department")
        if dept not in seen_depts:
            seen_depts.add(dept)
            selected.append(doc)
        if len(selected) >= 2:
            break

    assert len(selected) >= 2, "Need at least 2 doctors in different departments"

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    dates = [tomorrow, day_after]

    for i, doc in enumerate(selected):
        resp = test_client.post(
            "/api/appointments", json={"doctor_id": doc["id"], "date": dates[i]}
        )
        assert resp.status_code == 201, (
            f"Booking failed for doctor in {doc.get('department')}: {resp.get_json()}"
        )


def test_admin_sees_appointments_across_all_doctors(test_client):
    """Admin appointment view should contain appointments from multiple doctors."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    # Patient books two different doctors
    login(test_client, "patient", "patient")
    all_doctors = test_client.get("/api/doctors").get_json()
    assert len(all_doctors) >= 2

    test_client.post(
        "/api/appointments", json={"doctor_id": all_doctors[0]["id"], "date": tomorrow}
    )
    test_client.post(
        "/api/appointments", json={"doctor_id": all_doctors[1]["id"], "date": day_after}
    )

    # Admin views appointments
    login(test_client, "admin", "admin")
    resp = test_client.get("/api/admin/appointments")
    assert resp.status_code == 200
    data = resp.get_json()
    appointments = data if isinstance(data, list) else data.get("appointments", [])
    doctor_ids = {a["doctor_id"] for a in appointments}
    assert len(doctor_ids) >= 2, (
        f"Expected appointments from ≥2 doctors, found: {doctor_ids}"
    )


def test_doctor2_and_doctor3_have_independent_slots(test_client):
    """Appointments with doctor2 and doctor3 on same date use independent slot sequences."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    login(test_client, "patient", "patient")
    doctors = test_client.get("/api/doctors").get_json()
    doc2 = next(d for d in doctors if "doctor2" in d.get("username", ""))
    doc3 = next(d for d in doctors if "doctor3" in d.get("username", ""))

    resp2 = test_client.post(
        "/api/appointments", json={"doctor_id": doc2["id"], "date": tomorrow}
    )
    assert resp2.status_code == 201
    time_doc2 = resp2.get_json()["assigned_time"]

    login(test_client, "patient2", "patient2")
    resp3 = test_client.post(
        "/api/appointments", json={"doctor_id": doc3["id"], "date": tomorrow}
    )
    assert resp3.status_code == 201
    time_doc3 = resp3.get_json()["assigned_time"]

    # Both doctors start at 09:00, so both first slots should be 09:00
    assert time_doc2 == time_doc3, (
        f"Expected both first slots to be equal (independent queues), "
        f"got doc2={time_doc2} doc3={time_doc3}"
    )
