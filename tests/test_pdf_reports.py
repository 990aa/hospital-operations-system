"""PDF report generation integration tests."""

from datetime import datetime, timedelta

from models.database import Patient, User


def test_monthly_report_route_returns_pdf_binary(doctor_token):
    now = datetime.now()
    response = doctor_token.get(f"/api/doctor/monthly-report/{now.month}/{now.year}")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_patient_history_pdf_works_for_zero_treatments(patient_token, doctor_token):
    doctors = patient_token.get("/api/doctors").get_json()
    doctor_id = doctors[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    book_response = patient_token.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )
    assert book_response.status_code == 201

    my_appointments = patient_token.get("/api/my-appointments").get_json()
    patient_id = my_appointments[0]["patient_id"]

    response = doctor_token.get(f"/api/doctor/patient-history-pdf/{patient_id}")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_patient_history_pdf_does_not_leak_other_patient_data(
    test_client, patient_token, doctor_token
):
    doctors = patient_token.get("/api/doctors").get_json()
    doctor_id = doctors[0]["id"]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    book_response = patient_token.post(
        "/api/appointments", json={"doctor_id": doctor_id, "date": tomorrow}
    )
    assert book_response.status_code == 201

    appointment = patient_token.get("/api/my-appointments").get_json()[0]
    appointment_id = appointment["id"]
    patient_id = appointment["patient_id"]

    pay_response = patient_token.post(
        f"/api/patient/payment/appointment/{appointment_id}",
        json={
            "payment_method": "credit_card",
            "card_number": "1111222233334444",
            "notes": "PDF report payment",
        },
    )
    assert pay_response.status_code == 201

    complete_response = doctor_token.post(
        f"/api/appointments/{appointment_id}/complete",
        json={"diagnosis": "Flu", "prescription": "Rest and hydration"},
    )
    assert complete_response.status_code == 200

    with test_client.application.app_context():
        patient_one = Patient.query.get(patient_id)
        patient_two_user = User.query.filter_by(username="patient2").first()
        assert patient_one is not None
        assert patient_two_user is not None
        patient_two_name = patient_two_user.name

    pdf_response = doctor_token.get(f"/api/doctor/patient-history-pdf/{patient_id}")
    assert pdf_response.status_code == 200
    assert pdf_response.data.startswith(b"%PDF")

    decoded_pdf = pdf_response.data.decode("latin-1", errors="ignore")
    assert patient_two_name not in decoded_pdf
