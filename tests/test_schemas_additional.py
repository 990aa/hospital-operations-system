"""Additional schema tests to improve validation branch coverage."""

import pytest
from flask import Flask, jsonify
from pydantic import ValidationError

from backend.schemas import (
    BookAppointmentRequest,
    CompleteAppointmentRequest,
    CreateDoctorRequest,
    LoginRequest,
    ProcessPaymentRequest,
    RegisterRequest,
    RescheduleAppointmentRequest,
    UpdateAvailabilityRequest,
    UpdateDoctorRequest,
    UpdatePatientRequest,
    UpdateProfileRequest,
    UpdateTreatmentRequest,
    _reject_script_markup,
    validate,
)


def test_reject_script_markup_accepts_plain_text():
    assert _reject_script_markup("Dr Alice", "name") == "Dr Alice"


def test_reject_script_markup_rejects_angle_brackets():
    with pytest.raises(ValueError):
        _reject_script_markup("<script>", "name")


def test_login_request_username_validation():
    valid = LoginRequest(username="valid.user", password="secret")
    assert valid.username == "valid.user"

    with pytest.raises(ValidationError):
        LoginRequest(username="!!", password="secret")


def test_register_request_validates_name_and_password():
    valid = RegisterRequest(
        username="patient_ok",
        password="longpass1",
        name="Patient Name",
        email="patient@example.com",
    )
    assert valid.username == "patient_ok"

    with pytest.raises(ValidationError):
        RegisterRequest(
            username="patient_ok",
            password="short",
            name="Patient Name",
            email="patient@example.com",
        )

    with pytest.raises(ValidationError):
        RegisterRequest(
            username="patient_ok",
            password="longpass1",
            name="<bad>",
            email="patient@example.com",
        )


def test_book_appointment_request_date_validation():
    req = BookAppointmentRequest(doctor_id=1, date="2030-01-01")
    assert req.date == "2030-01-01"

    with pytest.raises(ValidationError):
        BookAppointmentRequest(doctor_id=1, date="2030/01/01")


def test_create_doctor_request_validation_rules():
    payload = {
        "name": "Dr Good",
        "username": "dr.good",
        "password": "password123",
        "email": "drgood@example.com",
        "department_id": 1,
        "availability_start": "09:00",
        "availability_end": "17:00",
        "slot_minutes": 30,
    }
    created = CreateDoctorRequest(**payload)
    assert created.slot_minutes == 30

    with pytest.raises(ValidationError):
        CreateDoctorRequest(**{**payload, "slot_minutes": 5})

    with pytest.raises(ValidationError):
        CreateDoctorRequest(**{**payload, "availability_start": "09"})


def test_update_models_require_at_least_one_field():
    with pytest.raises(ValidationError):
        UpdateDoctorRequest()

    with pytest.raises(ValidationError):
        UpdatePatientRequest()

    with pytest.raises(ValidationError):
        UpdateTreatmentRequest()


def test_update_availability_slot_range():
    good = UpdateAvailabilityRequest(slot_minutes=15)
    assert good.slot_minutes == 15

    with pytest.raises(ValidationError):
        UpdateAvailabilityRequest(slot_minutes=120)


def test_complete_and_reschedule_date_validation():
    completed = CompleteAppointmentRequest(
        diagnosis="Cold",
        prescription="Rest",
        next_visit_date="2030-02-01",
    )
    assert completed.next_visit_date == "2030-02-01"

    with pytest.raises(ValidationError):
        CompleteAppointmentRequest(
            diagnosis="Cold",
            prescription="Rest",
            next_visit_date="02-01-2030",
        )

    with pytest.raises(ValidationError):
        RescheduleAppointmentRequest(new_date="01-02-2030")


def test_update_profile_validation_and_notification_literal():
    req = UpdateProfileRequest(name="Valid Name", notification_pref="email")
    assert req.notification_pref == "email"

    with pytest.raises(ValidationError):
        UpdateProfileRequest()

    with pytest.raises(ValidationError):
        UpdateProfileRequest(name="<x>")


def test_process_payment_request_literal_values():
    payment = ProcessPaymentRequest(payment_method="credit_card", card_number="4111")
    assert payment.payment_method == "credit_card"

    with pytest.raises(ValidationError):
        ProcessPaymentRequest(payment_method="insurance", card_number="4111")


def test_validate_decorator_branches():
    app = Flask(__name__)

    @app.route("/validate-booking", methods=["POST"])
    @validate(BookAppointmentRequest)
    def validate_booking(data):
        return jsonify({"doctor_id": data.doctor_id, "date": data.date})

    client = app.test_client()

    bad_json = client.post(
        "/validate-booking",
        data="not-json",
        content_type="application/json",
    )
    assert bad_json.status_code == 400

    bad_payload = client.post(
        "/validate-booking",
        json={"doctor_id": "x", "date": "bad-date"},
    )
    assert bad_payload.status_code == 422

    good_payload = client.post(
        "/validate-booking",
        json={"doctor_id": 7, "date": "2031-01-01"},
    )
    assert good_payload.status_code == 200
    assert good_payload.get_json()["doctor_id"] == 7
