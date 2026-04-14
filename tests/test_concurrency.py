"""Concurrency safety tests for appointment booking."""

import threading
from datetime import datetime, timedelta

import pytest

from app import create_app
from models.database import Appointment, Department, Doctor, Patient, User, db


@pytest.fixture()
def concurrency_app(tmp_path):
    db_path = tmp_path / "concurrency.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "WTF_CSRF_ENABLED": False,
            "SECURITY_PASSWORD_SALT": "testsalt",
            "SECRET_KEY": "testkey",
            "CACHE_TYPE": "SimpleCache",
            "RATELIMIT_ENABLED": False,
            "task_always_eager": True,
            "result_backend": "cache",
            "cache_backend": "memory",
        }
    )

    user_datastore = app.user_datastore
    with app.app_context():
        db.create_all()

        user_datastore.find_or_create_role(name="admin", description="Administrator")
        user_datastore.find_or_create_role(name="doctor", description="Doctor")
        user_datastore.find_or_create_role(name="patient", description="Patient")
        db.session.commit()

        dept = Department(name="General Medicine", description="General")
        db.session.add(dept)
        db.session.commit()

        doctor_user = user_datastore.create_user(
            username="doctor",
            email="doctor@test.com",
            password="doctor",
            name="Doctor",
            active=True,
        )
        doctor_user.set_password("doctor")
        user_datastore.add_role_to_user(doctor_user, "doctor")
        db.session.commit()

        doctor = Doctor(
            user_id=doctor_user.id,
            department_id=dept.id,
            availability="Dynamic 09:00-09:30",
            availability_days=(datetime.now().date() + timedelta(days=1)).strftime(
                "%a"
            ),
            availability_start="09:00",
            availability_end="09:30",
            slot_minutes=30,
        )
        db.session.add(doctor)

        patient_user = user_datastore.create_user(
            username="patient",
            email="patient@test.com",
            password="patient",
            name="Patient",
            active=True,
        )
        patient_user.set_password("patient")
        user_datastore.add_role_to_user(patient_user, "patient")
        db.session.commit()

        patient = Patient(user_id=patient_user.id, medical_history="")
        db.session.add(patient)
        db.session.commit()

    yield app


def test_simultaneous_booking_same_slot_allows_single_success(concurrency_app):
    target_date = (datetime.now().date() + timedelta(days=1)).isoformat()
    results = []
    lock = threading.Lock()

    def book():
        client = concurrency_app.test_client()
        client.post("/api/login", json={"username": "patient", "password": "patient"})
        response = client.post(
            "/api/appointments",
            json={"doctor_id": 1, "date": target_date},
        )
        with lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=book) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    successes = results.count(201)
    assert successes == 1, f"Expected 1 booking, got {successes}. Statuses: {results}"

    with concurrency_app.app_context():
        appointments = Appointment.query.filter_by(doctor_id=1, date=target_date).all()
        assert len(appointments) == 1
