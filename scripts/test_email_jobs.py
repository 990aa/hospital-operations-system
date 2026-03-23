"""
Live Email Job Tester

Invokes each Celery email task and waits for results.
Run with: uv run python scripts/test_email_jobs.py

Requires:
  - Redis running (Docker port 6379)
  - Celery worker running:  uv run celery -A backend.celery_config worker --loglevel=info --pool=solo
  - Flask app importable
  - .env with SMTP credentials
"""

import os
import sys
import time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import create_app
from models.database import db, Appointment, Patient, ExportJob
from datetime import datetime

app = create_app()


def wait_for_result(async_result, label, timeout=60):
    """Poll an AsyncResult and print status."""
    print(f"\n{'=' * 60}")
    print(f"  TASK: {label}")
    print(f"  ID  : {async_result.id}")
    print(f"{'=' * 60}")
    start = time.time()
    while not async_result.ready():
        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"  TIMEOUT after {timeout}s — state={async_result.state}")
            return None
        print(f"  ... waiting ({async_result.state}) [{elapsed:.0f}s]")
        time.sleep(2)
    elapsed = time.time() - start
    if async_result.successful():
        result = async_result.result
        print(f"  SUCCESS in {elapsed:.1f}s")
        print(f"  Result: {result}")
        return result
    else:
        print(f"  FAILED in {elapsed:.1f}s")
        try:
            print(f"  Error : {async_result.result}")
        except Exception as e:
            print(f"  Error : {e}")
        return None


# ── 1. Daily Reminders ─────────────────────────────────────────
def test_daily_reminders():
    print("\n" + "#" * 60)
    print("#  TEST 1: send_daily_reminders")
    print("#" * 60)
    with app.app_context():
        # Show today's booked appointments
        today = datetime.now().strftime("%Y-%m-%d")
        booked = Appointment.query.filter_by(date=today, status="Booked").all()
        print(f"\n  Today ({today}) has {len(booked)} booked appointments.")
        for a in booked:
            print(
                f"    - Patient: {a.patient.user.name} ({a.patient.user.email})"
                f"  Doctor: {a.doctor.user.name}  Time: {a.time}"
            )

    from backend.tasks import send_daily_reminders

    r = send_daily_reminders.delay()
    return wait_for_result(r, "send_daily_reminders")


# ── 2. Monthly Reports ─────────────────────────────────────────
def test_monthly_reports():
    print("\n" + "#" * 60)
    print("#  TEST 2: send_monthly_reports")
    print("#" * 60)
    with app.app_context():
        from models.database import Doctor

        doctors = Doctor.query.all()
        print(f"\n  {len(doctors)} doctors registered.")
        for d in doctors:
            print(f"    - {d.user.name} ({d.user.email}) notif={d.email_notifications}")

    from backend.tasks import send_monthly_reports

    r = send_monthly_reports.delay()
    return wait_for_result(r, "send_monthly_reports")


# ── 3. CSV Export (with email attachment) ───────────────────────
def test_export_treatments():
    print("\n" + "#" * 60)
    print("#  TEST 3: export_patient_treatments (CSV + email attachment)")
    print("#" * 60)
    with app.app_context():
        patient = Patient.query.first()
        if not patient:
            print("  No patients found — skipping.")
            return None
        patient_id = patient.id
        patient_name = patient.user.name
        patient_email = patient.user.email
        print(f"\n  Patient: {patient_name} ({patient_email})")

        # Create an ExportJob record
        job = ExportJob(
            patient_id=patient_id,
            status="pending",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id
        print(f"  ExportJob ID: {job_id}")

    from backend.tasks import export_patient_treatments

    r = export_patient_treatments.delay(patient_id, job_id)
    result = wait_for_result(r, "export_patient_treatments")

    # Check job status in DB
    with app.app_context():
        job = db.session.get(ExportJob, job_id)
        if job:
            print(f"\n  DB ExportJob status : {job.status}")
            print(f"  DB ExportJob file   : {job.file_path}")
    return result


# ── Run all ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  LIVE EMAIL JOB TESTING")
    print("=" * 60)

    r1 = test_daily_reminders()
    r2 = test_monthly_reports()
    r3 = test_export_treatments()

    print("\n\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for label, result in [
        ("Daily Reminders", r1),
        ("Monthly Reports", r2),
        ("CSV Export+Email", r3),
    ]:
        status = "PASS" if result is not None else "FAIL/TIMEOUT"
        print(f"  [{status}] {label}: {result}")
    print()
