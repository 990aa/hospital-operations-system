"""Additional integration tests to exercise admin/doctor/patient branches."""

from datetime import datetime, timedelta

from models.database import ExportJob, Patient, User, db


def _login(client, username, password):
    response = client.post(
        "/api/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200


def _book_for_patient(client):
    _login(client, "patient", "patient")
    doctor_id = client.get("/api/doctors").get_json()[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    response = client.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )
    assert response.status_code == 201
    appointment = client.get("/api/my-appointments").get_json()[0]
    return appointment


def test_admin_doctor_patients_and_appointments_filters(test_client):
    appointment = _book_for_patient(test_client)

    _login(test_client, "admin", "admin")
    doctor_patients = test_client.get(
        f"/api/admin/doctors/{appointment['doctor_id']}/patients"
    )
    assert doctor_patients.status_code == 200
    assert len(doctor_patients.get_json()) >= 1

    filtered = test_client.get(
        "/api/admin/appointments?doctor=doctor&status=Booked&type=consultation&payment=unpaid"
    )
    assert filtered.status_code == 200
    assert isinstance(filtered.get_json(), list)


def test_admin_export_jobs_listing_and_detail(test_client):
    _login(test_client, "patient", "patient")
    export_response = test_client.post("/api/export/treatments")
    assert export_response.status_code in (200, 201)
    job_id = export_response.get_json()["job_id"]

    _login(test_client, "admin", "admin")
    jobs_response = test_client.get("/api/admin/export-jobs")
    assert jobs_response.status_code == 200
    jobs_payload = jobs_response.get_json()
    assert "jobs" in jobs_payload

    detail_response = test_client.get(f"/api/admin/export-jobs/{job_id}")
    assert detail_response.status_code == 200
    assert detail_response.get_json()["id"] == job_id


def test_admin_payments_filters_and_summary(test_client):
    appointment = _book_for_patient(test_client)
    pay_response = test_client.post(
        f"/api/patient/payment/appointment/{appointment['id']}",
        json={
            "payment_method": "credit_card",
            "card_number": "1234567812345678",
            "notes": "coverage payment",
        },
    )
    assert pay_response.status_code == 201

    _login(test_client, "admin", "admin")
    response = test_client.get(
        "/api/admin/payments?status=completed&method=credit_card"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert "payments" in payload
    assert "summary" in payload


def test_doctor_profile_patients_and_payment_endpoints(test_client):
    appointment = _book_for_patient(test_client)
    pay_response = test_client.post(
        f"/api/patient/payment/appointment/{appointment['id']}",
        json={
            "payment_method": "debit_card",
            "card_number": "9999888877776666",
            "notes": "doctor ledger payment",
        },
    )
    assert pay_response.status_code == 201

    _login(test_client, "doctor", "doctor")
    profile_response = test_client.get("/api/doctor/profile")
    assert profile_response.status_code == 200

    patients_response = test_client.get("/api/doctor/patients")
    assert patients_response.status_code == 200
    assert isinstance(patients_response.get_json(), list)

    payments_response = test_client.get("/api/doctor/payments")
    assert payments_response.status_code == 200
    payments_payload = payments_response.get_json()
    assert "payments" in payments_payload
    assert "summary" in payments_payload


def test_patient_status_and_payment_status_endpoints(test_client):
    appointment = _book_for_patient(test_client)

    payment_status_response = test_client.get(
        f"/api/patient/appointment/{appointment['id']}/payment-status"
    )
    assert payment_status_response.status_code == 200
    assert payment_status_response.get_json()["paid"] is False

    status_response = test_client.put(
        f"/api/appointments/{appointment['id']}/status", json={"status": "Cancelled"}
    )
    assert status_response.status_code == 200

    invalid_status_response = test_client.put(
        f"/api/appointments/{appointment['id']}/status", json={"status": "Unknown"}
    )
    assert invalid_status_response.status_code == 422


def test_export_download_not_ready_and_missing_file_branches(test_client):
    _login(test_client, "patient", "patient")
    with test_client.application.app_context():
        patient = Patient.query.filter_by(
            user_id=User.query.filter_by(username="patient").first().id
        ).first()
        assert patient is not None
        patient_id = patient.id

        job = ExportJob(patient_id=patient_id, status="processing")
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    with test_client.application.app_context():
        job = ExportJob.query.filter_by(id=job_id, patient_id=patient_id).first()
        assert job is not None

        # Not-ready branch
        job.status = "processing"
        db.session.commit()

    not_ready_response = test_client.get(f"/api/export/download/{job_id}")
    assert not_ready_response.status_code == 400

    with test_client.application.app_context():
        job = ExportJob.query.get(job_id)
        assert job is not None
        # Missing-file branch
        job.status = "completed"
        job.file_path = "does/not/exist.csv"
        db.session.commit()

    missing_file_response = test_client.get(f"/api/export/download/{job_id}")
    assert missing_file_response.status_code == 404
