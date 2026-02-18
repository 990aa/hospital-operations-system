"""Stress and concurrency validation script for Hospital Management System.

This script executes a high-usage scenario against a running local server:
- Creates multiple doctors and patients
- Performs concurrent bookings against same doctor/day
- Executes payment, completion, follow-up scheduling, and cancellation/refund flows
- Verifies duplicate doctor/date/time appointments are blocked

Run:
    uv run python scripts/stress_test.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import random
import string
from typing import Any
import requests

BASE_URL = os.environ.get("HMS_BASE_URL", "http://127.0.0.1:5000")
API = f"{BASE_URL}/api"
TIMEOUT = 20
DOCTOR_PASSWORD = "stressdocpass"
PATIENT_PASSWORD = "stresspatientpass"


@dataclass
class Stats:
    """Aggregated run statistics printed at the end."""

    doctors_created: int = 0
    patients_created: int = 0
    booking_success: int = 0
    booking_conflicts: int = 0
    payments_success: int = 0
    complete_success: int = 0
    follow_ups_created: int = 0
    refunds_created: int = 0
    duplicate_slots_detected: int = 0


class ApiClient:
    """Small session-based API client with cookie persistence."""

    def __init__(self) -> None:
        self.session = requests.Session()

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, f"{API}{path}", timeout=TIMEOUT, **kwargs)
        return response

    def login(self, username: str, password: str) -> dict[str, Any]:
        response = self.request("POST", "/login", json={"username": username, "password": password})
        response.raise_for_status()
        return response.json()


def _suffix(length: int = 6) -> str:
    """Generate a random lowercase suffix for unique usernames/emails."""
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))


def create_stress_doctor(admin: ApiClient, department_id: int) -> dict[str, Any]:
    """Create a doctor record for stress flows and return doctor metadata."""
    username = f"stress_doc_{_suffix()}"
    payload = {
        "name": f"Dr. {username}",
        "username": username,
        "password": DOCTOR_PASSWORD,
        "email": f"{username}@test.local",
        "phone": "5551002000",
        "department_id": department_id,
        "availability_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "availability_start": "09:00",
        "availability_end": "17:00",
        "slot_minutes": 30,
        "bio": "Stress test doctor profile.",
    }
    response = admin.request("POST", "/admin/doctors", json=payload)
    if response.status_code not in (201, 200):
        response.raise_for_status()

    search = admin.request("GET", f"/admin/doctors?search={username}")
    search.raise_for_status()
    doctor = search.json()[0]
    return {"id": doctor["id"], "username": username}


def create_stress_patient() -> dict[str, str]:
    """Register a patient account and return patient credentials."""
    username = f"stress_patient_{_suffix()}"
    payload = {
        "username": username,
        "password": PATIENT_PASSWORD,
        "name": f"Patient {username}",
        "email": f"{username}@test.local",
        "phone": "5553004000",
    }
    response = requests.post(f"{API}/register", json=payload, timeout=TIMEOUT)
    if response.status_code not in (200, 201):
        response.raise_for_status()
    return {"username": username, "password": PATIENT_PASSWORD}


def patient_book_flow(patient_creds: dict[str, str], doctor_id: int, target_date: str) -> dict[str, Any]:
    """Execute booking + payment flow for one patient, returning status and IDs."""
    client = ApiClient()
    client.login(patient_creds["username"], patient_creds["password"])

    booking = client.request("POST", "/appointments", json={"doctor_id": doctor_id, "date": target_date})
    if booking.status_code == 201:
        appointment_id = booking.json()["appointment_id"]
        payment = client.request(
            "POST",
            f"/patient/payment/appointment/{appointment_id}",
            json={
                "amount": 500,
                "payment_method": "credit_card",
                "card_number": "9999888877776666",
            },
        )
        paid = payment.status_code == 201
        return {
            "booked": True,
            "appointment_id": appointment_id,
            "paid": paid,
            "patient_username": patient_creds["username"],
        }

    return {
        "booked": False,
        "status": booking.status_code,
        "message": booking.text,
        "patient_username": patient_creds["username"],
    }


def run() -> None:
    """Main stress-test runner."""
    stats = Stats()
    admin = ApiClient()
    admin.login("admin", "admin")

    # Resolve a department for doctor creation.
    dept_response = admin.request("GET", "/departments")
    dept_response.raise_for_status()
    departments = dept_response.json()
    department_id = departments[0]["id"]

    # Create multiple doctors and patients.
    doctors: list[dict[str, Any]] = []
    for _ in range(4):
        doctors.append(create_stress_doctor(admin, department_id))
        stats.doctors_created += 1

    patients: list[dict[str, str]] = []
    for _ in range(18):
        patients.append(create_stress_patient())
        stats.patients_created += 1

    # Pick one doctor as the high-contention target.
    hot_doctor = doctors[0]
    booking_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Execute concurrent booking/payment attempts.
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [
            executor.submit(patient_book_flow, patient_creds, hot_doctor["id"], booking_date)
            for patient_creds in patients
        ]
        for future in as_completed(futures):
            results.append(future.result())

    successful = [item for item in results if item.get("booked")]
    conflicts = [item for item in results if not item.get("booked")]
    stats.booking_success = len(successful)
    stats.booking_conflicts = len(conflicts)
    stats.payments_success = len([item for item in successful if item.get("paid")])

    # Doctor completes a subset and schedules follow-ups.
    doctor_client = ApiClient()
    doctor_client.login(hot_doctor["username"], DOCTOR_PASSWORD)
    doctor_appointments = doctor_client.request("GET", "/doctor/appointments")
    doctor_appointments.raise_for_status()
    booked_items = [item for item in doctor_appointments.json() if item["status"] == "Booked"]

    to_complete = booked_items[: min(8, len(booked_items))]
    follow_up_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    for appointment in to_complete:
        completion = doctor_client.request(
            "POST",
            f"/appointments/{appointment['id']}/complete",
            json={
                "diagnosis": "Stress diagnosis",
                "prescription": "Stress prescription",
                "notes": "Stress note",
                "next_visit_date": follow_up_date,
            },
        )
        if completion.status_code == 200:
            stats.complete_success += 1
            follow_up = completion.json().get("follow_up")
            if follow_up:
                stats.follow_ups_created += 1

    # Cancel some paid-booked appointments as patients to trigger refunds.
    cancelled_count = 0
    for item in successful:
        if cancelled_count >= 4:
            break
        patient_client = ApiClient()
        patient_client.login(item["patient_username"], PATIENT_PASSWORD)
        my_apps = patient_client.request("GET", "/my-appointments")
        if my_apps.status_code != 200:
            continue
        booked_paid = [
            app
            for app in my_apps.json()
            if app["status"] == "Booked" and app.get("payment_status") == "completed"
        ]
        if not booked_paid:
            continue
        cancel_response = patient_client.request(
            "POST", f"/appointments/{booked_paid[0]['id']}/cancel"
        )
        if cancel_response.status_code == 200:
            cancelled_count += 1

    # Verify duplicate slots are prevented by checking doctor/date/time uniqueness.
    latest = admin.request("GET", "/my-appointments")
    latest.raise_for_status()
    tuples = [(a["doctor_id"], a["date"], a["time"]) for a in latest.json()]
    stats.duplicate_slots_detected = len(tuples) - len(set(tuples))

    # Count refunds from admin payment feed.
    payments = admin.request("GET", "/admin/payments")
    payments.raise_for_status()
    stats.refunds_created = len([p for p in payments.json().get("payments", []) if p.get("status") == "refunded"])

    print("\n=== Stress Test Summary ===")
    print(f"Doctors created: {stats.doctors_created}")
    print(f"Patients created: {stats.patients_created}")
    print(f"Concurrent booking success: {stats.booking_success}")
    print(f"Concurrent booking conflicts: {stats.booking_conflicts}")
    print(f"Payments success: {stats.payments_success}")
    print(f"Consultations completed: {stats.complete_success}")
    print(f"Follow-ups created: {stats.follow_ups_created}")
    print(f"Refund records observed: {stats.refunds_created}")
    print(f"Duplicate doctor/date/time slots found: {stats.duplicate_slots_detected}")

    if stats.duplicate_slots_detected != 0:
        raise SystemExit("FAIL: Duplicate appointment slots detected.")

    print("PASS: Stress and concurrency checks completed.")


if __name__ == "__main__":
    run()
