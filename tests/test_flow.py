"""
End-to-End Flow Tests.

Tests the complete workflow:
1. Admin creates doctor
2. Patient registers
3. Patient books appointment
4. Doctor views appointment and patient history
5. Doctor completes appointment with treatment
6. Patient views treatment history
7. Patient exports treatment history

Author: Abdul Ahad
"""

from datetime import datetime, timedelta


def test_full_workflow(test_client):
    """
    Test complete patient-doctor workflow.

    Steps:
    1. Admin logs in and creates a doctor
    2. Patient registers
    3. Patient books appointment
    4. Doctor logs in and views appointments
    5. Doctor views patient history
    6. Doctor completes appointment
    7. Patient views completed appointment with treatment
    8. Patient triggers export
    """
    # Step 1: Admin login
    print("\n=== Step 1: Admin Login ===")
    response = test_client.post(
        "/api/login", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 200
    print("✓ Admin logged in")

    # Get departments
    resp = test_client.get("/api/departments")
    assert resp.status_code == 200
    depts = resp.get_json()
    dept_id = depts[0]["id"]
    print(f"✓ Found department: {depts[0]['name']}")

    # Step 2: Admin creates a doctor
    print("\n=== Step 2: Create Doctor ===")
    response = test_client.post(
        "/api/admin/doctors",
        json={
            "name": "Dr. Workflow Test",
            "username": "workflowdoc",
            "password": "password",
            "email": "workflow@test.com",
            "phone": "5559998888",
            "department_id": dept_id,
        },
    )
    assert response.status_code == 201
    print("✓ Doctor created")

    # Get the doctor's ID
    resp = test_client.get("/api/admin/doctors?search=workflowdoc")
    doctor_id = resp.get_json()[0]["id"]
    print(f"✓ Doctor ID: {doctor_id}")

    # Step 3: Patient registers
    print("\n=== Step 3: Patient Registration ===")
    test_client.post("/api/logout")  # Logout admin first

    response = test_client.post(
        "/api/register",
        json={
            "username": "workflowpatient",
            "password": "password",
            "name": "Workflow Patient",
            "email": "wfpatient@test.com",
            "phone": "5557776666",
        },
    )
    assert response.status_code == 200
    print("✓ Patient registered")

    # Step 4: Patient login
    print("\n=== Step 4: Patient Login ===")
    response = test_client.post(
        "/api/login", json={"username": "workflowpatient", "password": "password"}
    )
    assert response.status_code == 200
    assert response.get_json()["role"] == "patient"
    print("✓ Patient logged in")

    # Step 5: Patient books appointment
    print("\n=== Step 5: Book Appointment ===")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    response = test_client.post(
        "/api/appointments",
        json={"doctor_id": doctor_id, "date": tomorrow, "time": "10:00"},
    )
    assert response.status_code == 201
    appointment_id = response.get_json()["appointment_id"]
    print(f"✓ Appointment booked: ID {appointment_id}")

    # Step 6: Patient views their appointments
    print("\n=== Step 6: Patient Views Appointments ===")
    response = test_client.get("/api/my-appointments")
    assert response.status_code == 200
    appointments = response.get_json()
    assert len(appointments) > 0
    assert appointments[0]["status"] == "Booked"
    print(f"✓ Found {len(appointments)} appointment(s)")

    # Step 7: Doctor login
    print("\n=== Step 7: Doctor Login ===")
    test_client.post("/api/logout")

    response = test_client.post(
        "/api/login", json={"username": "workflowdoc", "password": "password"}
    )
    assert response.status_code == 200
    assert response.get_json()["role"] == "doctor"
    print("✓ Doctor logged in")

    # Step 8: Doctor views appointments
    print("\n=== Step 8: Doctor Views Appointments ===")
    response = test_client.get("/api/doctor/appointments")
    assert response.status_code == 200
    doctor_appointments = response.get_json()
    assert len(doctor_appointments) > 0
    patient_id = doctor_appointments[0]["patient_id"]
    print(f"✓ Found {len(doctor_appointments)} appointment(s)")

    # Step 9: Doctor views patient summary
    print("\n=== Step 9: Doctor Views Patient Summary ===")
    response = test_client.get(f"/api/doctor/patients/{patient_id}/summary")
    assert response.status_code == 200
    summary = response.get_json()
    assert "patient" in summary
    assert summary["patient"]["name"] == "Workflow Patient"
    print(f"✓ Patient: {summary['patient']['name']}")

    # Step 10: Doctor completes appointment
    print("\n=== Step 10: Complete Appointment ===")
    response = test_client.post(
        f"/api/appointments/{appointment_id}/complete",
        json={
            "diagnosis": "Test Diagnosis - Workflow",
            "prescription": "Test Prescription - Take twice daily",
            "notes": "Patient responded well to treatment. Follow up in 2 weeks.",
        },
    )
    assert response.status_code == 200
    print("✓ Appointment completed with treatment")

    # Step 11: Patient views completed appointment
    print("\n=== Step 11: Patient Views Treatment ===")
    test_client.post("/api/logout")

    response = test_client.post(
        "/api/login", json={"username": "workflowpatient", "password": "password"}
    )
    assert response.status_code == 200

    response = test_client.get("/api/my-appointments")
    assert response.status_code == 200
    appointments = response.get_json()
    completed = [a for a in appointments if a["status"] == "Completed"]
    assert len(completed) > 0
    assert completed[0]["treatment"] is not None
    assert completed[0]["treatment"]["diagnosis"] == "Test Diagnosis - Workflow"
    print("✓ Patient can see treatment details")

    # Step 12: Patient triggers export
    print("\n=== Step 12: Export Treatment History ===")
    response = test_client.post("/api/export/treatments")
    assert response.status_code in [200, 201]
    export_data = response.get_json()
    assert "job_id" in export_data
    print(f"✓ Export job created: ID {export_data['job_id']}")

    # Step 13: Patient views export jobs
    print("\n=== Step 13: View Export Jobs ===")
    response = test_client.get("/api/export/jobs")
    assert response.status_code == 200
    export_jobs = response.get_json()
    assert len(export_jobs) >= 1
    print(f"✓ Found {len(export_jobs)} export job(s)")

    print("\n=== Workflow Test Complete ===")
