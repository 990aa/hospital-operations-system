import os
import sqlite3
from datetime import date, timedelta

import pytest

import db
from app.logic import get_shortage_alerts, process_donation, smart_allocate_all
from db_init import init_db

TEST_DB = "bloodbank_test_regression.db"


@pytest.fixture()
def setup_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    original_db_name = db.DB_NAME
    db.DB_NAME = TEST_DB

    init_db()

    conn = db.get_db_connection()
    yield conn

    conn.close()
    db.DB_NAME = original_db_name
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture()
def flask_client(setup_db):
    from main import app

    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as client:
        yield client


def _add_donor(conn, name="D1", blood_group="A+"):
    conn.execute(
        "INSERT INTO DONOR (name, blood_group, phone) VALUES (?, ?, ?)",
        (name, blood_group, "555-0101"),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _add_recipient(conn, name="R1", hospital="City Hospital"):
    conn.execute(
        "INSERT INTO RECIPIENT (name, hospital_name, contact_info) VALUES (?, ?, ?)",
        (name, hospital, "555-0202"),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _add_request(
    conn,
    recipient_id,
    blood_group="A+",
    quantity=100,
    urgency="Normal",
    component="Whole Blood",
):
    conn.execute(
        """INSERT INTO TRANSFUSION_REQ
           (recipient_id, requested_group, requested_component,
            quantity_ml, urgency_level, req_date)
           VALUES (?, ?, ?, ?, ?, DATE('now'))""",
        (recipient_id, blood_group, component, quantity, urgency),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


class TestRouteCrashHandling:
    def test_donor_route_handles_non_numeric_donation_quantity(
        self, flask_client, setup_db
    ):
        donor_id = _add_donor(setup_db, "Crash Guard Donor", "A+")

        resp = flask_client.post(
            "/donor",
            data={
                "donate": "true",
                "donor_id": str(donor_id),
                "quantity": "not-a-number",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"Donation quantity must be numeric" in resp.data

    def test_donor_route_rolls_back_on_insert_failure(
        self, flask_client, setup_db, monkeypatch
    ):
        import main as main_module

        class FailingDonorInsertConnection:
            def __init__(self, real_conn):
                self.real_conn = real_conn
                self.rollback_called = False

            def execute(self, sql, params=()):
                if sql.strip().upper().startswith("INSERT INTO DONOR"):
                    raise sqlite3.OperationalError("database is locked")
                return self.real_conn.execute(sql, params)

            def commit(self):
                return self.real_conn.commit()

            def rollback(self):
                self.rollback_called = True
                return self.real_conn.rollback()

            def close(self):
                return None

        failing_conn = FailingDonorInsertConnection(setup_db)
        monkeypatch.setattr(main_module, "get_db_connection", lambda: failing_conn)

        resp = flask_client.post(
            "/donor",
            data={
                "register": "true",
                "name": "Insert Failure Donor",
                "blood_group": "A+",
                "phone": "555-9999",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"database is locked" in resp.data
        assert failing_conn.rollback_called

    def test_hospital_route_rolls_back_on_insert_failure(
        self, flask_client, setup_db, monkeypatch
    ):
        import main as main_module

        class FailingRecipientInsertConnection:
            def __init__(self, real_conn):
                self.real_conn = real_conn
                self.rollback_called = False

            def execute(self, sql, params=()):
                if sql.strip().upper().startswith("INSERT INTO RECIPIENT"):
                    raise sqlite3.OperationalError("database is locked")
                return self.real_conn.execute(sql, params)

            def commit(self):
                return self.real_conn.commit()

            def rollback(self):
                self.rollback_called = True
                return self.real_conn.rollback()

            def close(self):
                return None

        failing_conn = FailingRecipientInsertConnection(setup_db)
        monkeypatch.setattr(main_module, "get_db_connection", lambda: failing_conn)

        resp = flask_client.post(
            "/hospital",
            data={
                "add_hospital": "true",
                "name": "Dr. Locked",
                "hospital_name": "Locked Hospital",
                "contact": "555-4040",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"database is locked" in resp.data
        assert failing_conn.rollback_called


class TestNonPositiveValidation:
    def test_process_donation_rejects_zero_and_negative(self, setup_db):
        donor_id = _add_donor(setup_db, "Negative Guard", "A+")

        ok_zero, msg_zero = process_donation(donor_id, 0)
        ok_negative, msg_negative = process_donation(donor_id, -450)

        assert not ok_zero
        assert "greater than zero" in msg_zero.lower()
        assert not ok_negative
        assert "greater than zero" in msg_negative.lower()

    def test_hospital_request_rejects_non_positive_quantity(
        self, flask_client, setup_db
    ):
        recipient_id = _add_recipient(setup_db, "Dr. Zero", "Zero Hospital")

        resp = flask_client.post(
            "/hospital",
            data={
                "request_blood": "true",
                "recipient_id": str(recipient_id),
                "blood_group": "A+",
                "component": "Whole Blood",
                "quantity": "-50",
                "urgency": "Normal",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"Quantity must be greater than zero" in resp.data

        req_count = setup_db.execute("SELECT COUNT(*) FROM TRANSFUSION_REQ").fetchone()[
            0
        ]
        assert req_count == 0


class TestReactivationFlows:
    def test_donor_inactive_filter_and_reactivate(self, flask_client, setup_db):
        donor_id = _add_donor(setup_db, "Dormant Donor", "B+")
        setup_db.execute(
            "UPDATE DONOR SET is_active = 0 WHERE donor_id = ?", (donor_id,)
        )
        setup_db.commit()

        page = flask_client.get("/donor?status=inactive")
        assert page.status_code == 200
        assert b"Dormant Donor" in page.data
        assert b"Reactivate" in page.data

        resp = flask_client.post(
            "/donor",
            data={
                "reactivate": "true",
                "donor_id": str(donor_id),
                "status": "inactive",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        donor = setup_db.execute(
            "SELECT is_active FROM DONOR WHERE donor_id = ?", (donor_id,)
        ).fetchone()
        assert donor["is_active"] == 1

    def test_hospital_inactive_filter_and_reactivate(self, flask_client, setup_db):
        recipient_id = _add_recipient(setup_db, "Dr. Dormant", "Dormant Hospital")
        setup_db.execute(
            "UPDATE RECIPIENT SET is_active = 0 WHERE recipient_id = ?",
            (recipient_id,),
        )
        setup_db.commit()

        page = flask_client.get("/hospital?status=inactive")
        assert page.status_code == 200
        assert b"Dormant Hospital" in page.data
        assert b"Reactivate" in page.data

        resp = flask_client.post(
            "/hospital",
            data={
                "reactivate_hospital": "true",
                "recipient_id": str(recipient_id),
                "status": "inactive",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        recipient = setup_db.execute(
            "SELECT is_active FROM RECIPIENT WHERE recipient_id = ?",
            (recipient_id,),
        ).fetchone()
        assert recipient["is_active"] == 1


class TestShortageMathAndIndexes:
    def test_shortage_math_uses_actual_active_days(self, setup_db):
        donor_id = _add_donor(setup_db, "Forecast Donor", "A+")
        ok, _ = process_donation(donor_id, 150)
        assert ok

        recipient_id = _add_recipient(setup_db, "Dr. Forecast", "Forecast Hospital")
        _add_request(setup_db, recipient_id, "A+", 90, "Critical")
        smart_allocate_all()

        three_days_ago = (date.today() - timedelta(days=2)).isoformat()
        setup_db.execute(
            "UPDATE FULFILLMENT_LOG SET fulfillment_date = ?",
            (three_days_ago,),
        )
        setup_db.commit()

        alerts = get_shortage_alerts()
        a_plus_alert = next((a for a in alerts if a["blood_group"] == "A+"), None)

        assert a_plus_alert is not None
        assert a_plus_alert["daily_rate"] >= 20
        assert a_plus_alert["projected_days"] <= 3

    def test_required_indexes_exist(self, setup_db):
        bag_indexes = {
            row["name"]
            for row in setup_db.execute("PRAGMA index_list('BLOOD_BAG')").fetchall()
        }
        req_indexes = {
            row["name"]
            for row in setup_db.execute(
                "PRAGMA index_list('TRANSFUSION_REQ')"
            ).fetchall()
        }
        donor_indexes = {
            row["name"]
            for row in setup_db.execute("PRAGMA index_list('DONOR')").fetchall()
        }

        assert "idx_bag_status_expiry" in bag_indexes
        assert "idx_req_status_urgency" in req_indexes
        assert "idx_donor_active" in donor_indexes


class TestDashboardOrdering:
    def test_donation_history_orders_same_day_by_latest_insert(
        self, flask_client, setup_db
    ):
        donor_older = _add_donor(setup_db, "Older Donation Donor", "A+")
        donor_newer = _add_donor(setup_db, "Newer Donation Donor", "A+")

        ok1, _ = process_donation(donor_older, 100)
        ok2, _ = process_donation(donor_newer, 110)
        assert ok1 and ok2

        resp = flask_client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert html.index("Newer Donation Donor") < html.index("Older Donation Donor")

    def test_fulfilled_history_orders_same_day_by_latest_insert(
        self, flask_client, setup_db
    ):
        donor_id = _add_donor(setup_db, "Bag Source", "A+")
        ok, _ = process_donation(donor_id, 400)
        assert ok

        bag_id = setup_db.execute("SELECT bag_id FROM BLOOD_BAG LIMIT 1").fetchone()[0]
        rec_old = _add_recipient(setup_db, "Recipient Old", "Old Hosp")
        rec_new = _add_recipient(setup_db, "Recipient New", "New Hosp")

        req_old = _add_request(setup_db, rec_old, "A+", 100, "Normal")
        req_new = _add_request(setup_db, rec_new, "A+", 100, "Normal")

        setup_db.execute(
            "INSERT INTO FULFILLMENT_LOG (req_id, bag_id, quantity_allocated_ml) VALUES (?, ?, ?)",
            (req_old, bag_id, 100),
        )
        setup_db.execute(
            "UPDATE BLOOD_BAG SET current_volume_ml = current_volume_ml - 100 WHERE bag_id = ?",
            (bag_id,),
        )
        setup_db.execute(
            "INSERT INTO FULFILLMENT_LOG (req_id, bag_id, quantity_allocated_ml) VALUES (?, ?, ?)",
            (req_new, bag_id, 100),
        )
        setup_db.execute(
            "UPDATE BLOOD_BAG SET current_volume_ml = current_volume_ml - 100 WHERE bag_id = ?",
            (bag_id,),
        )
        setup_db.commit()

        resp = flask_client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert html.index("Recipient New") < html.index("Recipient Old")
