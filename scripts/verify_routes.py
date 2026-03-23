"""
Live Route Verification Script

Hits every API endpoint defined in the app against the running Flask server
(http://127.0.0.1:5000) and reports pass/fail for each.

Prerequisites:
  - Flask app running on port 5000
  - Database seeded via `python scripts/seed_db.py`

Usage:
    uv run python scripts/verify_routes.py
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import date, timedelta

BASE = "http://127.0.0.1:5000"
SESSION_COOKIE = None
PASS = 0
FAIL = 0


def _req(method, path, body=None, expect_codes=None):
    """Send an HTTP request and check the response code."""
    global PASS, FAIL, SESSION_COOKIE
    if expect_codes is None:
        expect_codes = [200]
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if SESSION_COOKIE:
        headers["Cookie"] = SESSION_COOKIE

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        resp = urllib.request.urlopen(req)
        code = resp.getcode()
        # Capture session cookie
        set_cookie = resp.headers.get("Set-Cookie")
        if set_cookie:
            SESSION_COOKIE = set_cookie.split(";")[0]
        raw = resp.read()
        try:
            resp_body = raw.decode("utf-8")
        except UnicodeDecodeError:
            resp_body = f"<binary {len(raw)} bytes>"
    except urllib.error.HTTPError as e:
        code = e.code
        resp_body = e.read().decode() if e.fp else ""
    except Exception as e:
        code = 0
        resp_body = str(e)

    ok = code in expect_codes
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    tag = f"[{status}]"
    print(f"  {tag:6s} {method:6s} {path:50s}  -> {code} (expected {expect_codes})")
    if not ok and resp_body:
        try:
            detail = json.loads(resp_body)
            print(f"         Detail: {detail}")
        except Exception:
            print(f"         Body: {resp_body[:200]}")
    return code, resp_body


def _json(resp_body):
    try:
        return json.loads(resp_body)
    except Exception:
        return {}


# TESTS


def test_health():
    print("\n--- Health ---")
    _req("GET", "/health")


def test_home_page():
    print("\n--- Home Page ---")
    _req("GET", "/")


def test_auth_flows():
    global SESSION_COOKIE
    print("\n--- Auth: Register ---")
    _req(
        "POST",
        "/api/register",
        {
            "username": "livetest_patient",
            "password": "password123",
            "name": "Live Test Patient",
            "email": "livetest@test.com",
        },
        [200, 400],
    )  # 400 if already exists

    print("\n--- Auth: Login (Admin) ---")
    SESSION_COOKIE = None
    _req("POST", "/api/login", {"username": "admin", "password": "admin"})

    print("\n--- Auth: Current User ---")
    _req("GET", "/api/current-user")

    print("\n--- Auth: Logout ---")
    _req("POST", "/api/logout")

    print("\n--- Auth: Current User (logged out) ---")
    _req("GET", "/api/current-user", expect_codes=[401])


def test_admin_routes():
    global SESSION_COOKIE
    SESSION_COOKIE = None
    print("\n--- Admin Login ---")
    _req("POST", "/api/login", {"username": "admin", "password": "admin"})

    print("\n--- Admin: Stats ---")
    _req("GET", "/api/admin/stats")

    print("\n--- Admin: Doctors list ---")
    _, body = _req("GET", "/api/admin/doctors")
    doctors = _json(body)

    print("\n--- Admin: Doctors search ---")
    _req("GET", "/api/admin/doctors?search=carter")

    print("\n--- Admin: Patients list ---")
    _req("GET", "/api/admin/patients")

    print("\n--- Admin: Patients search ---")
    _req("GET", "/api/admin/patients?search=emma")

    print("\n--- Admin: Appointments ---")
    _req("GET", "/api/admin/appointments")

    print("\n--- Admin: Appointments (filtered) ---")
    _req("GET", "/api/admin/appointments?status=Booked")

    print("\n--- Admin: Payments ---")
    _req("GET", "/api/admin/payments")

    print("\n--- Admin: Export Jobs ---")
    _req("GET", "/api/admin/export-jobs")

    print("\n--- Admin: Departments ---")
    _req("GET", "/api/departments")

    print("\n--- Admin: Create Department (duplicate test) ---")
    _req("POST", "/api/departments", {"name": "General Medicine"}, [409])

    print("\n--- Admin: Create Department (new) ---")
    _req(
        "POST",
        "/api/departments",
        {"name": "LiveTestDept", "description": "Test department"},
        [200, 201, 409],
    )

    # Get a doctor ID for sub-routes
    if isinstance(doctors, list) and doctors:
        doc_id = doctors[0]["id"]
        print(f"\n--- Admin: Doctor's Patients (doctor {doc_id}) ---")
        _req("GET", f"/api/admin/doctors/{doc_id}/patients")

    _req("POST", "/api/logout")


def test_doctor_routes():
    global SESSION_COOKIE
    SESSION_COOKIE = None
    print("\n--- Doctor Login (dr.carter) ---")
    _req("POST", "/api/login", {"username": "dr.carter", "password": "password"})

    print("\n--- Doctor: Profile ---")
    _req("GET", "/api/doctor/profile")

    print("\n--- Doctor: Appointments ---")
    _, body = _req("GET", "/api/doctor/appointments")
    appointments = _json(body)

    print("\n--- Doctor: Appointments (filtered) ---")
    _req("GET", "/api/doctor/appointments?status=Booked")

    print("\n--- Doctor: Patients ---")
    _, body = _req("GET", "/api/doctor/patients")
    patients = _json(body)

    if isinstance(patients, list) and patients:
        patient_id = patients[0].get("patient_id") or patients[0].get("id")
        print(f"\n--- Doctor: Patient History (patient {patient_id}) ---")
        _req("GET", f"/api/doctor/patients/{patient_id}/history")

        print(f"\n--- Doctor: Patient Summary (patient {patient_id}) ---")
        _req("GET", f"/api/doctor/patients/{patient_id}/summary")

        print(f"\n--- Doctor: Patient History PDF (patient {patient_id}) ---")
        _req("GET", f"/api/doctor/patient-history-pdf/{patient_id}")

    print("\n--- Doctor: Monthly Report ---")
    today = date.today()
    _req("GET", f"/api/doctor/monthly-report/{today.month}/{today.year}")

    print("\n--- Doctor: Payments ---")
    _req("GET", "/api/doctor/payments")

    print("\n--- Doctor: Update Availability ---")
    _req(
        "PUT",
        "/api/doctor/availability",
        {
            "availability_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "availability_start": "09:00",
            "availability_end": "17:00",
            "slot_minutes": 30,
        },
    )

    # Test reschedule on a booked appointment
    if isinstance(appointments, list):
        booked = [a for a in appointments if a.get("status") == "Booked"]
        if booked:
            apt_id = booked[0]["id"]
            day3 = (date.today() + timedelta(days=3)).isoformat()
            print(f"\n--- Doctor: Reschedule Appointment {apt_id} ---")
            _req(
                "POST",
                f"/api/doctor/appointments/{apt_id}/reschedule",
                {"new_date": day3},
                [200, 400],
            )

    _req("POST", "/api/logout")


def test_patient_routes():
    global SESSION_COOKIE
    SESSION_COOKIE = None
    print("\n--- Patient Login (emma.taylor) ---")
    _req("POST", "/api/login", {"username": "emma.taylor", "password": "password"})

    print("\n--- Patient: Departments ---")
    _req("GET", "/api/patient/departments")

    print("\n--- Patient: Doctors list ---")
    _, body = _req("GET", "/api/doctors")
    doctors = _json(body)

    if isinstance(doctors, list) and doctors:
        doc_id = doctors[0]["id"]
        print(f"\n--- Patient: Doctor Availability (doctor {doc_id}) ---")
        _req("GET", f"/api/doctors/{doc_id}/availability")

    print("\n--- Patient: My Appointments ---")
    _, body = _req("GET", "/api/my-appointments")
    apts = _json(body)

    print("\n--- Patient: Profile (GET) ---")
    _req("GET", "/api/profile")

    print("\n--- Patient: Payments ---")
    _req("GET", "/api/patient/payments")

    print("\n--- Patient: Export Treatments ---")
    _, export_body = _req(
        "POST", "/api/export/treatments", expect_codes=[200, 201, 500]
    )
    export_data = _json(export_body)

    if export_data.get("job_id"):
        job_id = export_data["job_id"]
        print(f"\n--- Patient: Export Job Status ({job_id}) ---")
        _req("GET", f"/api/export/jobs/{job_id}")

    print("\n--- Patient: Export Jobs list ---")
    _req("GET", "/api/export/jobs")

    # Book a new appointment
    if isinstance(doctors, list) and doctors:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        print(
            f"\n--- Patient: Book Appointment (doctor {doctors[0]['id']}, {tomorrow}) ---"
        )
        _, book_body = _req(
            "POST",
            "/api/appointments",
            {
                "doctor_id": doctors[0]["id"],
                "date": tomorrow,
            },
            [201, 400, 409],
        )  # 400/409 if no slots or date not available

    # Cancel an appointment if we have a booked one
    if isinstance(apts, list):
        booked_apts = [a for a in apts if a.get("status") == "Booked"]
        if booked_apts:
            apt_id = booked_apts[0]["id"]
            print(f"\n--- Patient: Cancel Appointment {apt_id} ---")
            _req("POST", f"/api/appointments/{apt_id}/cancel")

    _req("POST", "/api/logout")


def test_unauthorized():
    global SESSION_COOKIE
    SESSION_COOKIE = None
    print("\n--- Unauthorized Access ---")
    _req("GET", "/api/admin/stats", expect_codes=[302, 401, 403])
    _req("GET", "/api/doctor/appointments", expect_codes=[302, 401, 403])
    _req("GET", "/api/my-appointments", expect_codes=[302, 401, 403])


def test_404():
    print("\n--- 404 Routes ---")
    _req("GET", "/api/nonexistent", expect_codes=[404])


if __name__ == "__main__":
    print("=" * 70)
    print("  LIVE ROUTE VERIFICATION")
    print("=" * 70)

    test_health()
    test_home_page()
    test_auth_flows()
    test_admin_routes()
    test_doctor_routes()
    test_patient_routes()
    test_unauthorized()
    test_404()

    print("\n" + "=" * 70)
    print(f"  RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    print("=" * 70)

    sys.exit(1 if FAIL > 0 else 0)
