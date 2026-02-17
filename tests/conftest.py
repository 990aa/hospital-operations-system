"""
Pytest Configuration and Fixtures.

This module provides shared fixtures for all tests including:
- Test client with in-memory database
- Authentication fixtures for admin, doctor, and patient
- Sample data creation helpers

Author: Abdul Ahad
"""

import pytest
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.database import db, User, Department, Doctor, Patient, Appointment
from flask_security import hash_password


@pytest.fixture(scope="function")
def test_client():
    """
    Create a test client with an in-memory database.

    This fixture creates a Flask app configured for testing with:
    - SQLite in-memory database
    - CSRF disabled for API testing
    - Test-specific security settings

    Yields:
        Flask test client
    """
    # Create app with test configuration
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SECURITY_PASSWORD_SALT": "testsalt",
        "SECRET_KEY": "testkey",
        "CACHE_TYPE": "SimpleCache",
        "task_always_eager": True,
        "result_backend": "cache",
        "cache_backend": "memory",
    }
    app = create_app(test_config)

    user_datastore = app.user_datastore

    with app.app_context():
        # Create all tables
        db.create_all()

        # Create default roles
        user_datastore.find_or_create_role(name="admin", description="Administrator")
        user_datastore.find_or_create_role(name="doctor", description="Doctor")
        user_datastore.find_or_create_role(name="patient", description="Patient")
        db.session.commit()

        # Create test admin
        if not user_datastore.find_user(username="admin"):
            user_datastore.create_user(
                username="admin",
                email="admin@test.com",
                phone="1234567890",
                password=hash_password("admin"),
                roles=["admin"],
                name="Test Admin",
                active=True,
            )
            db.session.commit()

        # Create test departments
        dept1 = Department.query.filter_by(name="General Medicine").first()
        if not dept1:
            dept1 = Department(
                name="General Medicine", description="General health care"
            )
            db.session.add(dept1)

        dept2 = Department.query.filter_by(name="Cardiology").first()
        if not dept2:
            dept2 = Department(
                name="Cardiology", description="Heart related treatments"
            )
            db.session.add(dept2)

        db.session.commit()

        # Create test doctor
        if not user_datastore.find_user(username="doctor"):
            doctor_user = user_datastore.create_user(
                username="doctor",
                email="doctor@test.com",
                phone="2345678901",
                password=hash_password("docpassword"),
                roles=["doctor"],
                name="Dr. Test Doctor",
                active=True,
            )
            db.session.commit()

            doctor = Doctor(
                user_id=doctor_user.id,
                department_id=dept1.id,
                availability="Mon-Fri 9AM-5PM",
                email_notifications=True,
            )
            db.session.add(doctor)
            db.session.commit()

        # Create test patient
        if not user_datastore.find_user(username="patient"):
            patient_user = user_datastore.create_user(
                username="patient",
                email="patient@test.com",
                phone="3456789012",
                password=hash_password("patientpassword"),
                roles=["patient"],
                name="Test Patient",
                active=True,
            )
            db.session.commit()

            patient = Patient(
                user_id=patient_user.id,
                medical_history="Previous surgery in 2020",
                notification_pref="email",
            )
            db.session.add(patient)
            db.session.commit()

    testing_client = app.test_client()

    with app.app_context():
        yield testing_client
        db.session.remove()
        db.drop_all()


@pytest.fixture
def admin_token(test_client):
    """
    Get authenticated admin session.

    Returns:
        Test client with admin session
    """
    test_client.post("/api/login", json={"username": "admin", "password": "admin"})
    return test_client


@pytest.fixture
def doctor_token(test_client):
    """
    Get authenticated doctor session.

    Returns:
        Test client with doctor session
    """
    test_client.post(
        "/api/login", json={"username": "doctor", "password": "docpassword"}
    )
    return test_client


@pytest.fixture
def patient_token(test_client):
    """
    Get authenticated patient session.

    Returns:
        Test client with patient session
    """
    test_client.post(
        "/api/login", json={"username": "patient", "password": "patientpassword"}
    )
    return test_client


@pytest.fixture
def sample_appointment(test_client):
    """
    Create a sample appointment for testing.

    Returns:
        Appointment object
    """
    with test_client.application.app_context():
        patient = Patient.query.filter_by(
            user_id=User.query.filter_by(username="patient").first().id
        ).first()
        doctor = Doctor.query.filter_by(
            user_id=User.query.filter_by(username="doctor").first().id
        ).first()

        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            date="2025-12-25",
            time="10:00",
            status="Booked",
        )
        db.session.add(appointment)
        db.session.commit()

        yield appointment

        # Cleanup
        db.session.delete(appointment)
        db.session.commit()
