import os
import tempfile


def _login(client, username, password):
    return client.post(
        "/api/login",
        json={"username": username, "password": password},
    )


def _logout_if_needed(client):
    client.post("/api/logout")


def _with_temp_bloodbank_db(test_client):
    fd, path = tempfile.mkstemp(prefix="bbms_test_", suffix=".db")
    os.close(fd)
    os.unlink(path)
    os.environ["BLOODBANK_DB_PATH"] = path
    return path


def test_blood_bank_forbidden_for_patient(test_client):
    db_path = _with_temp_bloodbank_db(test_client)
    try:
        _login(test_client, "patient", "patient")
        response = test_client.get("/blood-bank/", follow_redirects=False)
        assert response.status_code in (302, 403)
    finally:
        _logout_if_needed(test_client)
        if os.path.exists(db_path):
            os.remove(db_path)


def test_blood_bank_access_for_admin(test_client):
    db_path = _with_temp_bloodbank_db(test_client)
    try:
        _login(test_client, "admin", "admin")
        response = test_client.get("/blood-bank/", follow_redirects=True)
        assert response.status_code == 200
        assert b"Blood Bank Dashboard" in response.data or b"CRITICAL SHORTAGES" in response.data
    finally:
        _logout_if_needed(test_client)
        if os.path.exists(db_path):
            os.remove(db_path)


def test_blood_bank_seeded_staff_can_access(test_client):
    client = test_client
    db_path = _with_temp_bloodbank_db(client)
    try:
        login_resp = _login(client, "bbstaff", "bbstaff")
        assert login_resp.status_code == 200
        response = client.get("/blood-bank/", follow_redirects=True)
        assert response.status_code == 200
    finally:
        _logout_if_needed(client)
        if os.path.exists(db_path):
            os.remove(db_path)


def test_blood_bank_donor_create_and_allocate(test_client):
    db_path = _with_temp_bloodbank_db(test_client)
    try:
        _login(test_client, "admin", "admin")

        donor_resp = test_client.post(
            "/blood-bank/donor",
            data={
                "register": "true",
                "name": "Integration Donor",
                "blood_group": "A+",
                "phone": "5551234567",
            },
            follow_redirects=True,
        )
        assert donor_resp.status_code == 200

        donate_resp = test_client.post(
            "/blood-bank/donor",
            data={
                "donate": "true",
                "donor_id": "1",
                "quantity": "450",
            },
            follow_redirects=True,
        )
        assert donate_resp.status_code == 200

        hospital_resp = test_client.post(
            "/blood-bank/hospital",
            data={
                "add_hospital": "true",
                "name": "Dr Admin",
                "hospital_name": "General Test Hospital",
                "contact": "5550001",
            },
            follow_redirects=True,
        )
        assert hospital_resp.status_code == 200

        request_resp = test_client.post(
            "/blood-bank/hospital",
            data={
                "request_blood": "true",
                "recipient_id": "1",
                "blood_group": "A+",
                "component": "Whole Blood",
                "quantity": "200",
                "urgency": "Normal",
            },
            follow_redirects=True,
        )
        assert request_resp.status_code == 200

        alloc_resp = test_client.post("/blood-bank/allocate_all", follow_redirects=True)
        assert alloc_resp.status_code == 200
    finally:
        _logout_if_needed(test_client)
        if os.path.exists(db_path):
            os.remove(db_path)
