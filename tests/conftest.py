"""
Pytest Configuration and Fixtures.

This module provides shared fixtures for all tests including:
- Test client with in-memory database
- Authentication fixtures for admin, doctor, and patient
- Sample data creation helpers with multiple departments, doctors, and patients
- Concurrent appointment booking scenarios

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
    - Multiple departments and doctors (same username=password for easy login)
    - Multiple patients
    - Celery in eager/synchronous mode for background job testing

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

        # Create test admin (username = password for easy login)
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

        # Create multiple test departments
        dept_names = [
            ("General Medicine", "General health care"),
            ("Cardiology", "Heart related treatments"),
            ("Neurology", "Brain and nervous system"),
            ("Orthopedics", "Bone and joint care"),
        ]
        depts = []
        for dname, ddesc in dept_names:
            dept = Department.query.filter_by(name=dname).first()
            if not dept:
                dept = Department(name=dname, description=ddesc)
                db.session.add(dept)
                db.session.flush()
            depts.append(dept)
        db.session.commit()

        # Create multiple test doctors - username = password for easy login
        doctor_data = [
            ("doctor", "doctor@test.com", "2345678901", "Dr. Test Doctor", 0),
            ("doctor2", "doctor2@test.com", "2345678902", "Dr. Cardio Doctor", 1),
            ("doctor3", "doctor3@test.com", "2345678903", "Dr. Neuro Doctor", 2),
            ("doctor4", "doctor4@test.com", "2345678904", "Dr. Ortho Doctor", 3),
        ]
        for uname, email, phone, fullname, dept_idx in doctor_data:
            if not user_datastore.find_user(username=uname):
                doc_user = user_datastore.create_user(
                    username=uname,
                    email=email,
                    phone=phone,
                    password=hash_password(uname),  # username = password
                    roles=["doctor"],
                    name=fullname,
                    active=True,
                )
                db.session.commit()
                doc = Doctor(
                    user_id=doc_user.id,
                    department_id=depts[dept_idx].id,
                    availability="Mon-Fri 9AM-5PM",
                    availability_days="Mon,Tue,Wed,Thu,Fri",
                    availability_start="09:00",
                    availability_end="17:00",
                    slot_minutes=30,
                    email_notifications=True,
                )
                db.session.add(doc)
                db.session.commit()

        # Create multiple test patients - username = password for easy login
        patient_data = [
            ("patient", "patient@test.com", "3456789012", "Test Patient"),
            ("patient2", "patient2@test.com", "3456789013", "Test Patient Two"),
            ("patient3", "patient3@test.com", "3456789014", "Test Patient Three"),
        ]
        for uname, email, phone, fullname in patient_data:
            if not user_datastore.find_user(username=uname):
                p_user = user_datastore.create_user(
                    username=uname,
                    email=email,
                    phone=phone,
                    password=hash_password(uname),  # username = password
                    roles=["patient"],
                    name=fullname,
                    active=True,
                )
                db.session.commit()
                p = Patient(
                    user_id=p_user.id,
                    medical_history="Test medical history",
                    notification_pref="email",
                )
                db.session.add(p)
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
    Get authenticated doctor session (doctor1 - General Medicine).
    Password same as username for easy login.

    Returns:
        Test client with doctor session
    """
    test_client.post("/api/login", json={"username": "doctor", "password": "doctor"})
    return test_client


@pytest.fixture
def patient_token(test_client):
    """
    Get authenticated patient session (patient1).
    Password same as username for easy login.

    Returns:
        Test client with patient session
    """
    test_client.post("/api/login", json={"username": "patient", "password": "patient"})
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
