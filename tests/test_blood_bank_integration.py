import os
import sqlite3
import tempfile
from contextlib import contextmanager

import pytest


def _login(client, username, password):
    return client.post(
        "/api/login",
        json={"username": username, "password": password},
    )


def _logout_if_needed(client):
    client.post("/api/logout")


@contextmanager
def _temp_bloodbank_db_env():
    previous_path = os.environ.get("BLOODBANK_DB_PATH")
    fd, path = tempfile.mkstemp(prefix="bbms_test_", suffix=".db")
    os.close(fd)
    os.unlink(path)
    os.environ["BLOODBANK_DB_PATH"] = path
    try:
        yield path
    finally:
        if previous_path is None:
            os.environ.pop("BLOODBANK_DB_PATH", None)
        else:
            os.environ["BLOODBANK_DB_PATH"] = previous_path
        if os.path.exists(path):
            os.remove(path)


def _assert_blood_bank_nav_links(response_bytes: bytes) -> None:
    assert b'href="/blood-bank/"' in response_bytes
    assert b'href="/blood-bank/donor"' in response_bytes
    assert b'href="/blood-bank/hospital"' in response_bytes
    assert b'href="/blood-bank/audit"' in response_bytes
    assert b'action="/blood-bank/allocate_all"' in response_bytes


def test_blood_bank_requires_authentication(test_client):
    with _temp_bloodbank_db_env():
        response = test_client.get("/blood-bank/", follow_redirects=False)
        assert response.status_code in (302, 401)


def test_blood_bank_forbidden_for_patient(test_client):
    with _temp_bloodbank_db_env():
        _login(test_client, "patient", "patient")
        response = test_client.get("/blood-bank/", follow_redirects=False)
        assert response.status_code in (302, 403)
        _logout_if_needed(test_client)


def test_blood_bank_forbidden_for_doctor(test_client):
    with _temp_bloodbank_db_env():
        _login(test_client, "doctor", "doctor")
        response = test_client.get("/blood-bank/", follow_redirects=False)
        assert response.status_code in (302, 403)
        _logout_if_needed(test_client)


def test_blood_bank_access_for_admin(test_client):
    with _temp_bloodbank_db_env():
        _login(test_client, "admin", "admin")
        response = test_client.get("/blood-bank/", follow_redirects=True)
        assert response.status_code == 200
        assert (
            b"Blood Bank Dashboard" in response.data
            or b"CRITICAL SHORTAGES" in response.data
        )
        _assert_blood_bank_nav_links(response.data)
        _logout_if_needed(test_client)


def test_blood_bank_seeded_staff_can_access(test_client):
    with _temp_bloodbank_db_env():
        login_resp = _login(test_client, "bbstaff", "bbstaff")
        assert login_resp.status_code == 200
        response = test_client.get("/blood-bank/", follow_redirects=True)
        assert response.status_code == 200
        _assert_blood_bank_nav_links(response.data)
        _logout_if_needed(test_client)


def test_blood_bank_db_bootstraps_to_env_path(test_client):
    with _temp_bloodbank_db_env() as db_path:
        _login(test_client, "admin", "admin")

        response = test_client.get("/blood-bank/", follow_redirects=True)
        assert response.status_code == 200
        assert os.path.exists(db_path)

        conn = sqlite3.connect(db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()

        expected_tables = {
            "DONOR",
            "RECIPIENT",
            "BLOOD_BAG",
            "TRANSFUSION_REQ",
            "FULFILLMENT_LOG",
            "AUDIT_LOG",
        }
        assert expected_tables.issubset(tables)
        _logout_if_needed(test_client)


def test_blood_bank_donor_create_and_allocate(test_client):
    with _temp_bloodbank_db_env() as db_path:
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

        audit_resp = test_client.get("/blood-bank/audit", follow_redirects=True)
        assert audit_resp.status_code == 200
        assert b"System Audit Trail" in audit_resp.data

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            latest_req = conn.execute(
                """
                SELECT status, quantity_ml, quantity_allocated_ml
                FROM TRANSFUSION_REQ
                ORDER BY req_id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_bag = conn.execute(
                """
                SELECT initial_volume_ml, current_volume_ml
                FROM BLOOD_BAG
                ORDER BY bag_id ASC
                LIMIT 1
                """
            ).fetchone()
        finally:
            conn.close()

        assert latest_req is not None
        assert latest_req["status"] == "Fulfilled"
        assert latest_req["quantity_allocated_ml"] == pytest.approx(200.0)
        assert latest_bag is not None
        assert latest_bag["initial_volume_ml"] == pytest.approx(450.0)
        assert latest_bag["current_volume_ml"] == pytest.approx(250.0)

        _logout_if_needed(test_client)
