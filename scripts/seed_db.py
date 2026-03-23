"""
Database Seed Script — Hospital Management System


Populates the database with realistic test data for all roles and entities.

Usage:
    cd hospital-management-system
    uv run python scripts/seed_db.py

This will DROP all existing data (except the admin user) and re-seed from
scratch.  It is safe to run multiple times.

All emails use Gmail plus-addressing:  hms238537+<alias>@gmail.com
so every notification lands in the same inbox.

SEEDED CREDENTIALS

  Admin
  -----
  username: admin        password: admin

  Doctors  (all passwords are "password")
  -------
  username: dr.carter    password: password   email: hms238537+dr.carter@gmail.com    Dept: Cardiology        Days: Mon-Fri  09:00-17:00  30-min slots  ₹800
  username: dr.morgan    password: password   email: hms238537+dr.morgan@gmail.com    Dept: Neurology         Days: Mon,Wed,Fri 10:00-16:00  45-min slots  ₹1000
  username: dr.brooks    password: password   email: hms238537+dr.brooks@gmail.com    Dept: General Medicine  Days: Mon-Sat  08:00-14:00  20-min slots  ₹500
  username: dr.hayes     password: password   email: hms238537+dr.hayes@gmail.com     Dept: Dermatology       Days: Tue,Thu,Sat 09:00-13:00  30-min slots  ₹700
  username: dr.reed      password: password   email: hms238537+dr.reed@gmail.com      Dept: Pediatrics        Days: Mon-Fri  11:00-18:00  30-min slots  ₹600
  username: dr.walsh     password: password   email: hms238537+dr.walsh@gmail.com     Dept: Cardiology        Days: Tue,Thu   14:00-20:00  60-min slots  ₹1200

  Patients  (all passwords are "password")
  --------
  username: emma.taylor   password: password  email: hms238537+emma.taylor@gmail.com
  username: liam.harris   password: password  email: hms238537+liam.harris@gmail.com
  username: olivia.clark  password: password  email: hms238537+olivia.clark@gmail.com
  username: noah.lewis    password: password  email: hms238537+noah.lewis@gmail.com
  username: sophia.king   password: password  email: hms238537+sophia.king@gmail.com

SEEDED ENTITIES

  - 5 Departments (created by app startup): General Medicine, Cardiology, Dermatology, Pediatrics, Neurology
  - 6 Doctors across 5 departments with varied availability
  - 5 Patients with diverse profiles
  - 12 Appointments (mix of Booked, Completed, Cancelled across different doctors/patients)
  - 6 Treatments (for completed appointments)
  - 8 Payments (for booked and completed appointments, including 1 refund)
"""

import os
import sys
import uuid
from datetime import date, timedelta

# Ensure project root is on sys.path so imports work when
# running as `python scripts/seed_db.py` from the repo root.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app import create_app, create_initial_data
from models.database import (
    db,
    User,
    Doctor,
    Patient,
    Department,
    Appointment,
    Treatment,
    Payment,
    ExportJob,
)
from flask_security.utils import hash_password


def _clear_data():
    """Remove all rows from tables in dependency order."""
    ExportJob.query.delete()
    Payment.query.delete()
    Treatment.query.delete()
    Appointment.query.delete()
    Doctor.query.delete()
    Patient.query.delete()
    # Delete non-admin users
    admin_user = User.query.filter_by(username="admin").first()
    for user in User.query.all():
        if user.id != (admin_user.id if admin_user else -1):
            db.session.delete(user)
    db.session.commit()
    print("  Cleared existing seed data.")


def _get_or_create_departments():
    """Return a dict mapping department names to Department objects."""
    depts = {d.name: d for d in Department.query.all()}
    return depts


def _seed_doctors(app, depts):
    """Create 6 doctors with diverse availability."""
    user_datastore = app.extensions["security"].datastore

    doctors_data = [
        {
            "username": "dr.carter",
            "name": "Dr. Nathan Carter",
            "email": "hms238537+dr.carter@gmail.com",
            "phone": "9876543210",
            "department": "Cardiology",
            "bio": "Senior cardiologist with 15 years of experience in interventional cardiology and cardiac imaging.",
            "availability_days": "Mon,Tue,Wed,Thu,Fri",
            "availability_start": "09:00",
            "availability_end": "17:00",
            "slot_minutes": 30,
            "appointment_cost": 800.0,
        },
        {
            "username": "dr.morgan",
            "name": "Dr. Claire Morgan",
            "email": "hms238537+dr.morgan@gmail.com",
            "phone": "9876543211",
            "department": "Neurology",
            "bio": "Neurologist specializing in epilepsy, stroke rehabilitation, and movement disorders.",
            "availability_days": "Mon,Wed,Fri",
            "availability_start": "10:00",
            "availability_end": "16:00",
            "slot_minutes": 45,
            "appointment_cost": 1000.0,
        },
        {
            "username": "dr.brooks",
            "name": "Dr. Daniel Brooks",
            "email": "hms238537+dr.brooks@gmail.com",
            "phone": "9876543212",
            "department": "General Medicine",
            "bio": "General physician with broad experience in primary care, diabetes management, and preventive health.",
            "availability_days": "Mon,Tue,Wed,Thu,Fri,Sat",
            "availability_start": "08:00",
            "availability_end": "14:00",
            "slot_minutes": 20,
            "appointment_cost": 500.0,
        },
        {
            "username": "dr.hayes",
            "name": "Dr. Rachel Hayes",
            "email": "hms238537+dr.hayes@gmail.com",
            "phone": "9876543213",
            "department": "Dermatology",
            "bio": "Dermatologist focusing on acne, eczema, psoriasis, and cosmetic dermatology procedures.",
            "availability_days": "Tue,Thu,Sat",
            "availability_start": "09:00",
            "availability_end": "13:00",
            "slot_minutes": 30,
            "appointment_cost": 700.0,
        },
        {
            "username": "dr.reed",
            "name": "Dr. Marcus Reed",
            "email": "hms238537+dr.reed@gmail.com",
            "phone": "9876543214",
            "department": "Pediatrics",
            "bio": "Pediatrician with expertise in neonatal care, childhood vaccinations, and developmental disorders.",
            "availability_days": "Mon,Tue,Wed,Thu,Fri",
            "availability_start": "11:00",
            "availability_end": "18:00",
            "slot_minutes": 30,
            "appointment_cost": 600.0,
        },
        {
            "username": "dr.walsh",
            "name": "Dr. Helen Walsh",
            "email": "hms238537+dr.walsh@gmail.com",
            "phone": "9876543215",
            "department": "Cardiology",
            "bio": "Cardiac surgeon specializing in bypass surgery, valve repair, and heart failure management.",
            "availability_days": "Tue,Thu",
            "availability_start": "14:00",
            "availability_end": "20:00",
            "slot_minutes": 60,
            "appointment_cost": 1200.0,
        },
    ]

    created = []
    for d in doctors_data:
        # Skip if already exists
        if User.query.filter_by(username=d["username"]).first():
            doc_user = User.query.filter_by(username=d["username"]).first()
            created.append(Doctor.query.filter_by(user_id=doc_user.id).first())
            continue

        user = user_datastore.create_user(
            username=d["username"],
            email=d["email"],
            phone=d["phone"],
            password=hash_password("password"),
            name=d["name"],
            active=True,
        )
        user_datastore.add_role_to_user(user, "doctor")
        db.session.flush()

        dept = depts.get(d["department"])
        doctor = Doctor(
            user_id=user.id,
            department_id=dept.id,
            availability=f"{d['availability_days']} {d['availability_start']}-{d['availability_end']}",
            availability_days=d["availability_days"],
            availability_start=d["availability_start"],
            availability_end=d["availability_end"],
            slot_minutes=d["slot_minutes"],
            bio=d["bio"],
            email_notifications=True,
            appointment_cost=d["appointment_cost"],
        )
        db.session.add(doctor)
        db.session.flush()
        created.append(doctor)

    db.session.commit()
    print(f"  Created {len(created)} doctors.")
    return created


def _seed_patients(app):
    """Create 5 patients with diverse profiles."""
    user_datastore = app.extensions["security"].datastore

    patients_data = [
        {
            "username": "emma.taylor",
            "name": "Emma Taylor",
            "email": "hms238537+emma.taylor@gmail.com",
            "phone": "9988776601",
            "medical_history": "Mild hypertension diagnosed 2023. On ACE inhibitors.",
        },
        {
            "username": "liam.harris",
            "name": "Liam Harris",
            "email": "hms238537+liam.harris@gmail.com",
            "phone": "9988776602",
            "medical_history": "Seasonal allergies. No chronic conditions.",
        },
        {
            "username": "olivia.clark",
            "name": "Olivia Clark",
            "email": "hms238537+olivia.clark@gmail.com",
            "phone": "9988776603",
            "medical_history": "Type 2 diabetes (diet-controlled). Annual eye exams.",
        },
        {
            "username": "noah.lewis",
            "name": "Noah Lewis",
            "email": "hms238537+noah.lewis@gmail.com",
            "phone": "9988776604",
            "medical_history": "Childhood asthma (resolved). No current medications.",
        },
        {
            "username": "sophia.king",
            "name": "Sophia King",
            "email": "hms238537+sophia.king@gmail.com",
            "phone": "9988776605",
            "medical_history": "",
        },
    ]

    created = []
    for p in patients_data:
        if User.query.filter_by(username=p["username"]).first():
            pat_user = User.query.filter_by(username=p["username"]).first()
            created.append(Patient.query.filter_by(user_id=pat_user.id).first())
            continue

        user = user_datastore.create_user(
            username=p["username"],
            email=p["email"],
            phone=p["phone"],
            password=hash_password("password"),
            name=p["name"],
            active=True,
        )
        user_datastore.add_role_to_user(user, "patient")
        db.session.flush()

        patient = Patient(
            user_id=user.id,
            medical_history=p["medical_history"],
            notification_pref="email",
        )
        db.session.add(patient)
        db.session.flush()
        created.append(patient)

    db.session.commit()
    print(f"  Created {len(created)} patients.")
    return created


def _seed_appointments_and_treatments(doctors, patients):
    """Create 12 appointments with treatments and payments."""

    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    three_days = today + timedelta(days=3)
    last_week = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)
    three_weeks_ago = today - timedelta(days=21)

    # doctors[0] = dr.carter  (Cardiology)
    # doctors[1] = dr.morgan  (Neurology)
    # doctors[2] = dr.brooks  (General Medicine)
    # doctors[3] = dr.hayes   (Dermatology)
    # doctors[4] = dr.reed    (Pediatrics)
    # doctors[5] = dr.walsh   (Cardiology)

    # patients[0] = emma.taylor
    # patients[1] = liam.harris
    # patients[2] = olivia.clark
    # patients[3] = noah.lewis
    # patients[4] = sophia.king

    appointments_data = [
        # --- Completed appointments (past dates) with treatments ---
        {
            "patient": patients[0],
            "doctor": doctors[0],
            "date": three_weeks_ago.isoformat(),
            "time": "09:00",
            "status": "Completed",
            "treatment": {
                "diagnosis": "Hypertension Stage 1",
                "prescription": "Amlodipine 5mg daily",
                "notes": "BP 150/95. Follow-up in 3 weeks.",
            },
        },
        {
            "patient": patients[1],
            "doctor": doctors[2],
            "date": two_weeks_ago.isoformat(),
            "time": "08:00",
            "status": "Completed",
            "treatment": {
                "diagnosis": "Seasonal Allergic Rhinitis",
                "prescription": "Cetirizine 10mg, Fluticasone nasal spray",
                "notes": "Avoid dust exposure.",
            },
        },
        {
            "patient": patients[2],
            "doctor": doctors[2],
            "date": two_weeks_ago.isoformat(),
            "time": "08:20",
            "status": "Completed",
            "treatment": {
                "diagnosis": "Type 2 Diabetes - Routine Check",
                "prescription": "Continue diet plan. Metformin 500mg if HbA1c > 7",
                "notes": "HbA1c: 6.8. Good control.",
            },
        },
        {
            "patient": patients[3],
            "doctor": doctors[3],
            "date": last_week.isoformat(),
            "time": "09:00",
            "status": "Completed",
            "treatment": {
                "diagnosis": "Contact Dermatitis",
                "prescription": "Hydrocortisone cream 1%, avoid irritant",
                "notes": "Rash on forearms. Likely detergent allergy.",
            },
        },
        {
            "patient": patients[0],
            "doctor": doctors[1],
            "date": last_week.isoformat(),
            "time": "10:00",
            "status": "Completed",
            "treatment": {
                "diagnosis": "Tension Headache",
                "prescription": "Ibuprofen 400mg PRN, stress management",
                "notes": "MRI normal. Likely work-related stress.",
            },
        },
        {
            "patient": patients[4],
            "doctor": doctors[4],
            "date": last_week.isoformat(),
            "time": "11:00",
            "status": "Completed",
            "treatment": {
                "diagnosis": "Upper Respiratory Infection",
                "prescription": "Amoxicillin 500mg TID x 7 days, rest, fluids",
                "notes": "Mild sore throat, no complications.",
            },
        },
        # --- Cancelled appointment ---
        {
            "patient": patients[1],
            "doctor": doctors[0],
            "date": last_week.isoformat(),
            "time": "09:30",
            "status": "Cancelled",
        },
        # --- Upcoming booked appointments (future dates) ---
        {
            "patient": patients[0],
            "doctor": doctors[0],
            "date": tomorrow.isoformat(),
            "time": "09:00",
            "status": "Booked",
            "is_follow_up": True,
        },
        {
            "patient": patients[2],
            "doctor": doctors[5],
            "date": tomorrow.isoformat(),
            "time": "14:00",
            "status": "Booked",
        },
        {
            "patient": patients[3],
            "doctor": doctors[4],
            "date": day_after.isoformat(),
            "time": "11:00",
            "status": "Booked",
        },
        {
            "patient": patients[4],
            "doctor": doctors[2],
            "date": day_after.isoformat(),
            "time": "08:00",
            "status": "Booked",
        },
        {
            "patient": patients[1],
            "doctor": doctors[3],
            "date": three_days.isoformat(),
            "time": "09:00",
            "status": "Booked",
        },
    ]

    created_appointments = []
    for a_data in appointments_data:
        apt = Appointment(
            patient_id=a_data["patient"].id,
            doctor_id=a_data["doctor"].id,
            date=a_data["date"],
            time=a_data["time"],
            status=a_data["status"],
            is_follow_up=a_data.get("is_follow_up", False),
        )
        db.session.add(apt)
        db.session.flush()
        created_appointments.append((apt, a_data))

    db.session.commit()

    # Create treatments for completed appointments
    treatment_count = 0
    for apt, a_data in created_appointments:
        if a_data.get("treatment"):
            t = a_data["treatment"]
            treatment = Treatment(
                appointment_id=apt.id,
                diagnosis=t["diagnosis"],
                prescription=t["prescription"],
                notes=t.get("notes", ""),
            )
            db.session.add(treatment)
            treatment_count += 1

            # Append to patient medical history
            patient = db.session.get(Patient, apt.patient_id)
            summary = f"[{apt.date}] {t['diagnosis']} — {t['prescription']}"
            if patient.medical_history:
                patient.medical_history += "\n" + summary
            else:
                patient.medical_history = summary

    db.session.commit()
    print(
        f"  Created {len(created_appointments)} appointments, {treatment_count} treatments."
    )

    # Create payments
    payment_count = 0
    for apt, a_data in created_appointments:
        if a_data["status"] in ("Completed", "Booked"):
            doctor = db.session.get(Doctor, apt.doctor_id)
            payment = Payment(
                appointment_id=apt.id,
                patient_id=apt.patient_id,
                amount=doctor.appointment_cost or 500.0,
                payment_method=(
                    "credit_card" if payment_count % 2 == 0 else "debit_card"
                ),
                card_last4=str(1000 + payment_count),
                status="completed",
                transaction_id=f"TXN-SEED-{uuid.uuid4().hex[:12].upper()}",
            )
            db.session.add(payment)
            payment_count += 1

    # Add one refund for the cancelled appointment
    for apt, a_data in created_appointments:
        if a_data["status"] == "Cancelled":
            doctor = db.session.get(Doctor, apt.doctor_id)
            refund = Payment(
                appointment_id=apt.id,
                patient_id=apt.patient_id,
                amount=-(doctor.appointment_cost or 500.0),
                payment_method="credit_card",
                card_last4="9999",
                status="refunded",
                transaction_id=f"TXN-REFUND-{uuid.uuid4().hex[:12].upper()}",
            )
            db.session.add(refund)
            payment_count += 1

    db.session.commit()
    print(f"  Created {payment_count} payments (including refunds).")


def seed():
    """Main seed function."""
    app = create_app()
    create_initial_data(app)

    with app.app_context():
        print("\n=== Hospital Management System — Database Seed ===\n")

        print("[1/4] Clearing existing data ...")
        _clear_data()

        print("[2/4] Verifying departments ...")
        depts = _get_or_create_departments()
        print(f"  Found {len(depts)} departments: {', '.join(depts.keys())}")

        print("[3/4] Seeding doctors ...")
        doctors = _seed_doctors(app, depts)

        print("[4/4] Seeding patients, appointments, treatments, payments ...")
        patients = _seed_patients(app)
        _seed_appointments_and_treatments(doctors, patients)

        print("\n=== Seed complete! ===")
        print("Login with credentials listed in this script's docstring.\n")


if __name__ == "__main__":
    seed()
