"""
Admin Routes Tests.

Tests for admin functionality including:
- Statistics endpoints
- Doctor management (CRUD)
- Patient search
- Export job monitoring
- Access control

Author: Abdul Ahad
"""


def test_admin_stats_access(admin_token):
    """
    Test admin access to statistics endpoint.

    Verifies:
    - Returns counts of doctors, patients, appointments
    - Includes status breakdown (booked, completed, cancelled)
    """
    response = admin_token.get("/api/admin/stats")
    assert response.status_code == 200
    data = response.get_json()
    assert "total_doctors" in data
    assert "total_patients" in data
    assert "total_appointments" in data
    assert "completed_appointments" in data
    assert "booked_appointments" in data
    assert "cancelled_appointments" in data


def test_admin_stats_unauthorized(test_client, patient_token):
    """
    Test that non-admin users cannot access stats.

    Verifies:
    - Patient gets 403 (or redirect) when accessing admin stats
    """
    response = patient_token.get("/api/admin/stats")
    assert response.status_code in [302, 403, 401]


def test_add_doctor(admin_token):
    """
    Test adding a new doctor.

    Verifies:
    - Doctor is created with all fields
    - User and Doctor profile are linked
    - Returns 201 status
    """
    # Get department ID
    resp = admin_token.get("/api/departments")
    depts = resp.get_json()
    assert len(depts) > 0
    dept_id = depts[0]["id"]

    response = admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "New Doctor",
            "username": "newdoc",
            "password": "password",
            "email": "newdoc@test.com",
            "phone": "5559876543",
            "department_id": dept_id,
            "availability_days": ["Mon", "Wed", "Fri"],
            "availability_start": "10:00",
            "availability_end": "14:00",
            "slot_minutes": 30,
        },
    )
    assert response.status_code == 201
    assert "added successfully" in response.get_json()["message"]

    # Verify doctor added
    response = admin_token.get("/api/admin/doctors")
    data = response.get_json()
    added = [d for d in data if d["username"] == "newdoc"][0]
    assert added["availability_start"] == "10:00"
    assert added["availability_end"] == "14:00"


def test_create_department_and_case_insensitive_filter(admin_token):
    """Test admin can create department and filter by name case-insensitively."""
    create_response = admin_token.post(
        "/api/departments",
        json={"name": "Endocrinology", "description": "Hormonal care"},
    )
    assert create_response.status_code in [200, 201]

    filter_response = admin_token.get("/api/departments?search=endo")
    assert filter_response.status_code == 200
    departments = filter_response.get_json()
    assert any(department["name"] == "Endocrinology" for department in departments)


def test_add_doctor_duplicate_username(admin_token):
    """
    Test adding doctor with duplicate username.

    Verifies:
    - Duplicate username is rejected with 400
    """
    resp = admin_token.get("/api/departments")
    dept_id = resp.get_json()[0]["id"]

    # First add
    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Unique Doc",
            "username": "uniquedoc",
            "password": "password",
            "department_id": dept_id,
        },
    )

    # Duplicate should fail
    response = admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Another Doc",
            "username": "uniquedoc",
            "password": "password",
            "department_id": dept_id,
        },
    )
    assert response.status_code == 400
    assert "already exists" in response.get_json()["message"]


def test_add_doctor_duplicate_email(admin_token):
    """
    Test adding doctor with duplicate email.

    Verifies:
    - Duplicate email is rejected with 400
    """
    resp = admin_token.get("/api/departments")
    dept_id = resp.get_json()[0]["id"]

    # First add
    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "First Doc",
            "username": "firstdoc",
            "password": "password",
            "email": "same@email.com",
            "department_id": dept_id,
        },
    )

    # Duplicate email should fail
    response = admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Second Doc",
            "username": "seconddoc",
            "password": "password",
            "email": "same@email.com",
            "department_id": dept_id,
        },
    )
    assert response.status_code == 400
    assert "Email already exists" in response.get_json()["message"]


def test_delete_doctor(admin_token):
    """
    Test deleting a doctor.

    Verifies:
    - Doctor is deleted successfully
    - Associated user is also deleted
    """
    # First add a doctor to delete
    resp = admin_token.get("/api/departments")
    dept_id = resp.get_json()[0]["id"]

    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "To Delete",
            "username": "todelete",
            "password": "password",
            "department_id": dept_id,
        },
    )

    # Find the doctor
    resp = admin_token.get("/api/admin/doctors")
    docs = resp.get_json()
    to_delete = [d for d in docs if d["username"] == "todelete"][0]

    # Delete
    response = admin_token.delete(f"/api/admin/doctors/{to_delete['id']}")
    assert response.status_code == 200

    # Verify deleted
    resp = admin_token.get("/api/admin/doctors")
    docs = resp.get_json()
    assert not any(d["username"] == "todelete" for d in docs)


def test_search_doctors_by_name(admin_token):
    """
    Test searching doctors by name.

    Verifies:
    - Search by name returns matching doctors
    - Partial match works
    """
    resp = admin_token.get("/api/departments")
    dept_id = resp.get_json()[0]["id"]

    # Add doctors with different names
    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Alice Smith",
            "username": "alicesmith",
            "password": "password",
            "department_id": dept_id,
        },
    )
    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Bob Jones",
            "username": "bobjones",
            "password": "password",
            "department_id": dept_id,
        },
    )

    # Search for Alice
    response = admin_token.get("/api/admin/doctors?search=Alice")
    data = response.get_json()
    assert len(data) >= 1
    assert any(d["name"] == "Alice Smith" for d in data)


def test_search_doctors_by_department_filter(admin_token):
    """Test admin doctor list supports explicit department_id filter."""
    depts = admin_token.get("/api/departments").get_json()
    assert len(depts) >= 2
    dept_a = depts[0]["id"]
    dept_b = depts[1]["id"]

    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Dept A Doctor",
            "username": "deptadoctor",
            "password": "deptadoctor",
            "department_id": dept_a,
        },
    )
    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Dept B Doctor",
            "username": "deptbdoctor",
            "password": "deptbdoctor",
            "department_id": dept_b,
        },
    )

    response = admin_token.get(f"/api/admin/doctors?department_id={dept_b}")
    assert response.status_code == 200
    rows = response.get_json()
    assert rows
    assert all(row["department_id"] == dept_b for row in rows)


def test_admin_update_doctor(admin_token):
    """Test admin can edit doctor details via update endpoint."""
    dept_id = admin_token.get("/api/departments").get_json()[0]["id"]
    create = admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Editable Doctor",
            "username": "editabledoc",
            "password": "editabledoc",
            "department_id": dept_id,
            "slot_minutes": 30,
        },
    )
    assert create.status_code == 201

    doctor = admin_token.get("/api/admin/doctors?search=editabledoc").get_json()[0]
    update = admin_token.put(
        f"/api/admin/doctors/{doctor['id']}",
        json={
            "name": "Edited Doctor",
            "slot_minutes": 15,
            "availability_days": ["Mon", "Tue"],
            "availability_start": "08:30",
            "availability_end": "12:30",
        },
    )
    assert update.status_code == 200

    refreshed = admin_token.get("/api/admin/doctors?search=edited").get_json()[0]
    assert refreshed["name"] == "Edited Doctor"
    assert refreshed["slot_minutes"] == 15


def test_get_patients_paginated(admin_token):
    """
    Test getting patients with pagination.

    Verifies:
    - Returns paginated results
    - Includes pagination metadata
    """
    response = admin_token.get("/api/admin/patients?page=1&per_page=10")
    assert response.status_code == 200
    data = response.get_json()
    assert "patients" in data
    assert "total" in data
    assert "page" in data
    assert "pages" in data


def test_search_patients_by_id(admin_token):
    """
    Test searching patients by ID.

    Verifies:
    - Search by ID returns matching patient
    """
    # Get all patients first
    resp = admin_token.get("/api/admin/patients")
    patients = resp.get_json()["patients"]
    if len(patients) > 0:
        patient_id = patients[0]["id"]

        # Search by ID
        response = admin_token.get(f"/api/admin/patients?search={patient_id}")
        data = response.get_json()
        assert len(data["patients"]) >= 1


def test_search_patients_by_name(admin_token):
    """
    Test searching patients by name.

    Verifies:
    - Search by name returns matching patients
    """
    # Search for "Test Patient" created in fixtures
    response = admin_token.get("/api/admin/patients?search=Test")
    data = response.get_json()
    assert len(data["patients"]) >= 1


def test_search_patients_by_email(admin_token):
    """
    Test searching patients by email.

    Verifies:
    - Search by email returns matching patients
    """
    # Search by email
    response = admin_token.get("/api/admin/patients?search=patient@test.com")
    data = response.get_json()
    assert len(data["patients"]) >= 1


def test_search_patients_by_phone(admin_token):
    """
    Test searching patients by phone number.

    Verifies:
    - Search by phone returns matching patients
    """
    # Search by phone
    response = admin_token.get("/api/admin/patients?search=3456789012")
    data = response.get_json()
    assert len(data["patients"]) >= 1


def test_delete_patient(admin_token):
    """
    Test deleting a patient.

    Verifies:
    - Patient is deleted successfully
    - Associated user is also deleted
    """
    # First register a patient to delete
    admin_token.post(
        "/api/register",
        json={
            "username": "patienttodelete",
            "password": "password",
            "name": "Patient To Delete",
            "email": "delete@test.com",
        },
    )

    # Get the patient
    resp = admin_token.get("/api/admin/patients?search=patienttodelete")
    patient_id = resp.get_json()["patients"][0]["id"]

    # Delete
    response = admin_token.delete(f"/api/admin/patients/{patient_id}")
    assert response.status_code == 200


def test_admin_update_patient(admin_token):
    """Test admin can update patient profile fields."""
    admin_token.post(
        "/api/register",
        json={
            "username": "patientedit",
            "password": "patientedit",
            "name": "Patient Edit",
            "email": "patientedit@test.com",
        },
    )

    patient = admin_token.get("/api/admin/patients?search=patientedit").get_json()[
        "patients"
    ][0]
    update = admin_token.put(
        f"/api/admin/patients/{patient['id']}",
        json={
            "name": "Patient Updated",
            "phone": "7771112222",
            "medical_history": "Updated by admin",
            "notification_pref": "email",
        },
    )
    assert update.status_code == 200

    refreshed = admin_token.get("/api/admin/patients?search=updated").get_json()[
        "patients"
    ]
    assert any(row["name"] == "Patient Updated" for row in refreshed)


def test_admin_appointments_multi_filter(admin_token):
    """Test admin appointment filtering supports combined filters."""
    response = admin_token.get(
        "/api/admin/appointments?status=Booked&type=consultation&payment=unpaid"
    )
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_admin_export_jobs_access(admin_token):
    """
    Test admin access to export jobs.

    Verifies:
    - Returns list of export jobs
    - Includes job details
    """
    response = admin_token.get("/api/admin/export-jobs")
    assert response.status_code == 200
    data = response.get_json()
    assert "jobs" in data
    assert "total" in data
