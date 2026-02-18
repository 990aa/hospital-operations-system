"""Manual flow verifier for Hospital Management System.

This script mirrors the requested UI flows using HTTP sessions and prints
PASS/FAIL with details. It is intended to run against a live local server.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import requests

BASE_URL = "http://127.0.0.1:5000"
API = f"{BASE_URL}/api"


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str = ""):
        self.name = name
        self.ok = ok
        self.detail = detail


results: list[CheckResult] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append(CheckResult(name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name} {('- ' + detail) if detail else ''}")


admin = requests.Session()
patient = requests.Session()
doctor = requests.Session()


def login(session: requests.Session, username: str, password: str) -> dict:
    response = session.post(f"{API}/login", json={"username": username, "password": password}, timeout=15)
    response.raise_for_status()
    return response.json()


# 1) Login response should not include "logged in successfully" message.
try:
    data = login(admin, "admin", "admin")
    record(
        "Login response omits success message",
        "message" not in data,
        f"keys={list(data.keys())}",
    )
except Exception as exc:
    record("Login response omits success message", False, str(exc))


# 2) Department create + case-insensitive filter.
try:
    create_resp = admin.post(
        f"{API}/departments",
        json={"name": "Nephrology", "description": "Kidney care"},
        timeout=15,
    )
    ok_create = create_resp.status_code in (200, 201)

    search_resp = admin.get(f"{API}/departments?search=nePH", timeout=15)
    search_resp.raise_for_status()
    found = any(item["name"].lower() == "nephrology" for item in search_resp.json())
    record("Department create + case-insensitive filter", ok_create and found)
except Exception as exc:
    record("Department create + case-insensitive filter", False, str(exc))


# 3) Add doctor with explicit availability.
new_doc_username = f"flowdoc_{date.today().strftime('%m%d')}"
new_doc_password = "flowdocpass"
new_doc_id = None
try:
    departments = admin.get(f"{API}/departments", timeout=15).json()
    dept_id = departments[0]["id"]
    add_doc = admin.post(
        f"{API}/admin/doctors",
        json={
            "name": "Flow Doctor",
            "username": new_doc_username,
            "password": new_doc_password,
            "email": f"{new_doc_username}@test.com",
            "phone": "5550001234",
            "department_id": dept_id,
            "availability_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "availability_start": "09:00",
            "availability_end": "12:00",
            "slot_minutes": 30,
            "bio": "Flow verification doctor.",
        },
        timeout=15,
    )
    ok_add = add_doc.status_code in (201, 400)

    docs = admin.get(f"{API}/admin/doctors?search={new_doc_username}", timeout=15).json()
    target = next((d for d in docs if d["username"] == new_doc_username), None)
    if target:
        new_doc_id = target["id"]
    ok_availability = bool(target) and target["availability_start"] == "09:00" and target["slot_minutes"] == 30
    record("Doctor availability create/store", ok_add and ok_availability)
except Exception as exc:
    record("Doctor availability create/store", False, str(exc))


# 4) HTML password visibility checks for register/login/add-doctor.
try:
    html = requests.get(BASE_URL, timeout=15).text
    has_login_password_hidden = 'v-if="isLogin"' in html and 'type="password" v-model="authForm.password"' in html
    has_register_password_text = 'v-if="!isLogin"' in html and 'type="text" v-model="authForm.password"' in html
    has_add_doctor_password_text = 'type="text" v-model="newDoctor.password"' in html
    record(
        "Password visibility policy in frontend",
        has_login_password_hidden and has_register_password_text and has_add_doctor_password_text,
    )
except Exception as exc:
    record("Password visibility policy in frontend", False, str(exc))


# 5/7) Mutating APIs return JSON (not HTML) and no parse-breaking body.
try:
    # Register patient then delete patient to cover mutation actions.
    reg_username = f"flowpatient_{date.today().strftime('%m%d')}"
    reg = requests.Session()
    reg_resp = reg.post(
        f"{API}/register",
        json={
            "username": reg_username,
            "password": "flowpatientpass",
            "name": "Flow Patient",
            "email": f"{reg_username}@test.com",
        },
        timeout=15,
    )
    reg_json_ok = reg_resp.headers.get("content-type", "").startswith("application/json")

    patients_payload = admin.get(f"{API}/admin/patients?search={reg_username}", timeout=15).json()
    patient_id = patients_payload["patients"][0]["id"]
    del_resp = admin.delete(f"{API}/admin/patients/{patient_id}", timeout=15)
    del_json_ok = del_resp.headers.get("content-type", "").startswith("application/json")

    record("Mutating endpoints return JSON", reg_json_ok and del_json_ok)
except Exception as exc:
    record("Mutating endpoints return JSON", False, str(exc))


# 6) No nameless auto-patients.
try:
    patients_payload = admin.get(f"{API}/admin/patients", timeout=15).json()
    nameless = [p for p in patients_payload.get("patients", []) if not (p.get("name") or "").strip()]
    record("No nameless auto-created patients", len(nameless) == 0, f"count={len(nameless)}")
except Exception as exc:
    record("No nameless auto-created patients", False, str(exc))


# 9) No appointments should return empty list (no error payload dependency).
try:
    user = f"apptless_{date.today().strftime('%m%d')}"
    requests.post(
        f"{API}/register",
        json={"username": user, "password": "apptlesspass", "name": "No Appointment", "email": f"{user}@test.com"},
        timeout=15,
    )
    empty_patient = requests.Session()
    login(empty_patient, user, "apptlesspass")
    my_apps = empty_patient.get(f"{API}/my-appointments", timeout=15)
    my_json = my_apps.json()
    record("No-appointments flow returns empty list", my_apps.status_code == 200 and isinstance(my_json, list))
except Exception as exc:
    record("No-appointments flow returns empty list", False, str(exc))


# 10) Patient profile edit reflected in admin list.
try:
    profile_user = f"profile_{date.today().strftime('%m%d')}"
    requests.post(
        f"{API}/register",
        json={"username": profile_user, "password": "profilepass", "name": "Profile Name", "email": f"{profile_user}@test.com"},
        timeout=15,
    )
    p = requests.Session()
    login(p, profile_user, "profilepass")
    upd = p.post(
        f"{API}/profile",
        json={"name": "Profile Updated", "phone": "7778889999", "history": "Updated history", "notification_pref": "sms"},
        timeout=15,
    )
    profile_view = p.get(f"{API}/profile", timeout=15).json()
    admin_view = admin.get(f"{API}/admin/patients?search={profile_user}", timeout=15).json()
    reflected = admin_view["patients"][0]["name"] == "Profile Updated"
    record("Patient profile edit reflected for admin", upd.status_code == 200 and profile_view["name"] == "Profile Updated" and reflected)
except Exception as exc:
    record("Patient profile edit reflected for admin", False, str(exc))


# 11/12) 7-day availability + serial booking + time visibility.
try:
    if new_doc_id is None:
        raise RuntimeError("No doctor available for serial booking check")

    # Register and login booking patient.
    booking_user = f"book_{date.today().strftime('%m%d')}"
    requests.post(
        f"{API}/register",
        json={"username": booking_user, "password": "bookpass123", "name": "Book User", "email": f"{booking_user}@test.com"},
        timeout=15,
    )
    login(patient, booking_user, "bookpass123")

    # Ensure doctors API includes 7-day payload.
    docs = patient.get(f"{API}/doctors?search={new_doc_username}", timeout=15).json()
    doc = next((d for d in docs if d["username"] == new_doc_username), None)
    has_7_day = bool(doc) and len(doc.get("upcoming_availability", [])) == 7

    # Pick first bookable day.
    day = next((d for d in doc["upcoming_availability"] if d["remaining_slots"] > 1), None)
    if not day:
        raise RuntimeError("No available day with at least 2 slots")

    # Two bookings should get serial times.
    b1 = patient.post(f"{API}/appointments", json={"doctor_id": new_doc_id, "date": day["date"]}, timeout=15).json()
    b2 = patient.post(f"{API}/appointments", json={"doctor_id": new_doc_id, "date": day["date"]}, timeout=15).json()

    t1 = b1.get("assigned_time")
    t2 = b2.get("assigned_time")

    # Validate time appears in patient/doctor/admin appointment views.
    patient_apps = patient.get(f"{API}/my-appointments", timeout=15).json()
    login(doctor, new_doc_username, new_doc_password)
    doctor_apps = doctor.get(f"{API}/doctor/appointments", timeout=15).json()
    admin_apps = admin.get(f"{API}/my-appointments", timeout=15).json()

    in_patient = any(a.get("time") in (t1, t2) for a in patient_apps)
    in_doctor = any(a.get("time") in (t1, t2) for a in doctor_apps)
    in_admin = any(a.get("time") in (t1, t2) for a in admin_apps)

    serial = bool(t1 and t2 and t1 != t2)
    record("7-day availability + serial booking + time visibility", has_7_day and serial and in_patient and in_doctor and in_admin)
except Exception as exc:
    record("7-day availability + serial booking + time visibility", False, str(exc))


print("\nSummary")
print("-------")
passed = sum(1 for result in results if result.ok)
print(f"{passed}/{len(results)} checks passed")
if passed != len(results):
    raise SystemExit(1)
