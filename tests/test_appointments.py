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
