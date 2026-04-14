"""Validation and input-hardening tests for mutating API endpoints."""


def test_register_missing_required_fields_returns_422(test_client):
    response = test_client.post(
        "/api/register",
        json={
            "username": "partialuser",
            "password": "StrongPass123",
            "name": "Partial User",
        },
    )
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["title"] == "Validation Error"


def test_book_appointment_wrong_type_returns_422(patient_token):
    response = patient_token.post(
        "/api/appointments",
        json={"doctor_id": "not-an-int", "date": "2026-12-01"},
    )
    assert response.status_code == 422


def test_create_doctor_out_of_range_slot_minutes_returns_422(admin_token):
    departments = admin_token.get("/api/departments").get_json()
    dept_id = departments[0]["id"]

    response = admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Range Doctor",
            "username": "rangedoc",
            "password": "StrongPass123",
            "email": "range@test.com",
            "department_id": dept_id,
            "availability_days": ["Mon"],
            "availability_start": "09:00",
            "availability_end": "11:00",
            "slot_minutes": 5,
        },
    )
    assert response.status_code == 422


def test_sql_injection_username_rejected_cleanly(test_client):
    response = test_client.post(
        "/api/register",
        json={
            "username": "'; DROP TABLE users; --",
            "password": "StrongPass123",
            "name": "Injection User",
            "email": "inject@test.com",
            "phone": "9000099999",
        },
    )
    assert response.status_code == 422

    # Verify application still operates after rejection.
    login_response = test_client.post(
        "/api/login", json={"username": "admin", "password": "admin"}
    )
    assert login_response.status_code == 200


def test_xss_payload_in_name_rejected(test_client):
    register_response = test_client.post(
        "/api/register",
        json={
            "username": "safeprofile",
            "password": "StrongPass123",
            "name": "Safe Profile",
            "email": "safeprofile@test.com",
            "phone": "9000011111",
        },
    )
    assert register_response.status_code == 200

    login_response = test_client.post(
        "/api/login", json={"username": "safeprofile", "password": "StrongPass123"}
    )
    assert login_response.status_code == 200

    response = test_client.post(
        "/api/profile",
        json={"name": "<script>alert('xss')</script>"},
    )
    assert response.status_code == 422
