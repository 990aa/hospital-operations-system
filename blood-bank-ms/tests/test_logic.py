"""
Comprehensive test suite for the Blood Bank Management System.

Covers all 10 enhanced features:
  1. DB Triggers (auto-expire, donation safety, volume guard)
  2. SQL Views (inventory summary, critical pending, expiring soon)
  3. Audit Trail (forensic INSERT/UPDATE logging)
  4. Domain Normalization (FK-enforced lookup tables)
  5. Component Tracking (split whole-blood into RBC/Platelets/Plasma)
  6. Soft Deletes (is_active flag on DONOR and RECIPIENT)
  7. Predictive Shortage Alerts (projected stock days)
  8. Cross-Match Compatibility Scoring (preference-ranked matrix)
  9. Donor Loyalty Module (scoring, eligibility, rare-group bonus)
 10. Partial Fulfillment (incremental allocation with progress)

Also includes:
  - Edge-case tests (zero quantities, boundary values, duplicate ops)
  - Stress tests (high-volume data, concurrent-like sequential access)
  - Flask route integration tests (every GET/POST endpoint)
"""

import os
import sqlite3
import threading
from datetime import date, timedelta

import pytest

import db
from app.logic import (
    _date_str,
    get_dashboard_stats,
    get_donor_scores,
    get_eligible_donors_for_group,
    get_shortage_alerts,
    process_donation,
    smart_allocate_all,
)
from db_init import init_db

TEST_DB = "bloodbank_test_advanced.db"


#  FIXTURES


@pytest.fixture()
def setup_db():
    """Create a fresh test database before each test."""
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
    """Provide a Flask test client wired to the test database."""
    from main import app

    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as client:
        yield client


#  HELPERS


def _add_donor(conn, name="D1", blood_group="A+", phone="555-0001"):
    """Insert an active donor and return the donor_id."""
    conn.execute(
        "INSERT INTO DONOR (name, blood_group, phone) VALUES (?, ?, ?)",
        (name, blood_group, phone),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _add_recipient(conn, name="H1", hospital="City General"):
    """Insert a recipient (hospital) and return the recipient_id."""
    conn.execute(
        "INSERT INTO RECIPIENT (name, hospital_name) VALUES (?, ?)",
        (name, hospital),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _add_request(
    conn,
    recipient_id,
    blood_group="A+",
    quantity=450,
    urgency="Normal",
    component="Whole Blood",
):
    """Insert a transfusion request and return the req_id."""
    conn.execute(
        """INSERT INTO TRANSFUSION_REQ
           (recipient_id, requested_group, requested_component,
            quantity_ml, urgency_level, req_date)
           VALUES (?, ?, ?, ?, ?, DATE('now'))""",
        (recipient_id, blood_group, component, quantity, urgency),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _make_donor_eligible(conn, donor_id):
    """Set a donor's last_donation_date far enough back to pass the 56-day rule."""
    old_date = _date_str(date.today() - timedelta(days=100))
    conn.execute(
        "UPDATE DONOR SET last_donation_date = ? WHERE donor_id = ?",
        (old_date, donor_id),
    )
    conn.commit()


#  FEATURE 1: GRANULAR ALLOCATION


class TestGranularAllocation:
    """Verify ml-level tracking and deduction."""

    def test_basic_allocation(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()

        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        assert bag["initial_volume_ml"] == 450
        assert bag["current_volume_ml"] == 250
        assert bag["status"] == "Available"

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Fulfilled"
        assert req["quantity_allocated_ml"] == 200

    def test_exact_bag_drain(self, setup_db):
        """Requesting exact bag volume should drain to 0 -> status Empty."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 300)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 300)

        smart_allocate_all()

        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        assert bag["current_volume_ml"] == 0
        assert bag["status"] == "Empty"

    def test_multi_bag_single_request(self, setup_db):
        """Two small bags should combine to fill one larger request."""
        conn = setup_db
        d1 = _add_donor(conn)
        d2 = _add_donor(conn, "D2", "A+")
        process_donation(d1, 200)
        process_donation(d2, 200)

        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 350)

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["quantity_allocated_ml"] == 350
        assert req["status"] == "Fulfilled"

        logs = conn.execute("SELECT * FROM FULFILLMENT_LOG").fetchall()
        assert len(logs) == 2

    def test_no_stock_pending(self, setup_db):
        """Request with zero stock stays Pending."""
        conn = setup_db
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Pending"
        assert req["quantity_allocated_ml"] == 0


#  FEATURE 2: PRIORITIZATION (CRITICAL > NORMAL, QTY DESC)


class TestPrioritization:
    def test_critical_before_normal(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)

        req_normal = _add_request(conn, r1, "A+", 100, "Normal")
        req_critical = _add_request(conn, r1, "A+", 400, "Critical")

        smart_allocate_all()

        cs = conn.execute(
            "SELECT status FROM TRANSFUSION_REQ WHERE req_id=?",
            (req_critical,),
        ).fetchone()["status"]
        assert cs == "Fulfilled"

        ns = conn.execute(
            "SELECT status FROM TRANSFUSION_REQ WHERE req_id=?",
            (req_normal,),
        ).fetchone()["status"]
        assert ns in ("Pending", "Partially Fulfilled")

    def test_larger_quantity_first_same_urgency(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 250)
        r1 = _add_recipient(conn)

        req_big = _add_request(conn, r1, "A+", 200)
        req_small = _add_request(conn, r1, "A+", 100)

        smart_allocate_all()

        assert (
            conn.execute(
                "SELECT status FROM TRANSFUSION_REQ WHERE req_id=?",
                (req_big,),
            ).fetchone()["status"]
            == "Fulfilled"
        )
        ss = conn.execute(
            "SELECT status FROM TRANSFUSION_REQ WHERE req_id=?",
            (req_small,),
        ).fetchone()["status"]
        assert ss in ("Pending", "Partially Fulfilled")

    def test_multiple_critical_ordered_by_qty(self, setup_db):
        """Among multiple Critical requests, the larger one gets served first."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 300)
        r1 = _add_recipient(conn)

        req_small_c = _add_request(conn, r1, "A+", 100, "Critical")
        req_big_c = _add_request(conn, r1, "A+", 250, "Critical")

        smart_allocate_all()

        big = conn.execute(
            "SELECT status FROM TRANSFUSION_REQ WHERE req_id=?",
            (req_big_c,),
        ).fetchone()["status"]
        assert big == "Fulfilled"

        small = conn.execute(
            "SELECT * FROM TRANSFUSION_REQ WHERE req_id=?",
            (req_small_c,),
        ).fetchone()
        assert small["quantity_allocated_ml"] == 50
        assert small["status"] == "Partially Fulfilled"


#  FEATURE 3: TRIGGERS


class TestTriggers:
    def test_auto_expire_bag_on_drain(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        assert bag["status"] == "Available"

        conn.execute(
            "UPDATE BLOOD_BAG SET current_volume_ml = 0 WHERE bag_id = ?",
            (bag["bag_id"],),
        )
        conn.commit()

        updated = conn.execute(
            "SELECT status FROM BLOOD_BAG WHERE bag_id = ?",
            (bag["bag_id"],),
        ).fetchone()
        assert updated["status"] == "Empty"

    def test_auto_expire_negative_volume(self, setup_db):
        """Even negative volume triggers Empty status."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        conn.execute(
            "UPDATE BLOOD_BAG SET current_volume_ml = -10 WHERE bag_id = ?",
            (bag["bag_id"],),
        )
        conn.commit()

        assert (
            conn.execute(
                "SELECT status FROM BLOOD_BAG WHERE bag_id = ?",
                (bag["bag_id"],),
            ).fetchone()["status"]
            == "Empty"
        )

    def test_donation_safety_56_day_rule(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        ok, _ = process_donation(d1, 450)
        assert ok

        ok2, msg2 = process_donation(d1, 450)
        assert not ok2
        assert "DONATION_SAFETY" in msg2

    def test_donation_safety_after_56_days(self, setup_db):
        """After 56 days the donor can donate again."""
        conn = setup_db
        d1 = _add_donor(conn)
        ok1, _ = process_donation(d1, 450)
        assert ok1

        _make_donor_eligible(conn, d1)

        ok2, _ = process_donation(d1, 450)
        assert ok2

    def test_volume_guard_rejects_over_allocation(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)
        r1 = _add_recipient(conn)

        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        req_id = _add_request(conn, r1, "A+", 200)

        with pytest.raises(Exception, match="VOLUME_GUARD"):
            conn.execute(
                "INSERT INTO FULFILLMENT_LOG (req_id, bag_id, quantity_allocated_ml) "
                "VALUES (?, ?, 200)",
                (req_id, bag["bag_id"]),
            )

    def test_volume_guard_allows_exact_amount(self, setup_db):
        """Allocating exactly the bag volume should succeed."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)
        r1 = _add_recipient(conn)

        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        req_id = _add_request(conn, r1, "A+", 100)

        # Should NOT raise
        conn.execute(
            "INSERT INTO FULFILLMENT_LOG (req_id, bag_id, quantity_allocated_ml) "
            "VALUES (?, ?, 100)",
            (req_id, bag["bag_id"]),
        )
        conn.commit()

    def test_trg_update_req_allocated_partial(self, setup_db):
        """FULFILLMENT_LOG insert auto-updates TRANSFUSION_REQ allocated + status."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        req_id = _add_request(conn, r1, "A+", 400)

        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        conn.execute(
            "INSERT INTO FULFILLMENT_LOG (req_id, bag_id, quantity_allocated_ml) "
            "VALUES (?, ?, 200)",
            (req_id, bag["bag_id"]),
        )
        conn.commit()

        req = conn.execute(
            "SELECT * FROM TRANSFUSION_REQ WHERE req_id=?", (req_id,)
        ).fetchone()
        assert req["quantity_allocated_ml"] == 200
        assert req["status"] == "Partially Fulfilled"


#  FEATURE 4: SQL VIEWS


class TestViews:
    def test_inventory_summary_with_stock(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)

        inv = conn.execute("SELECT * FROM vw_inventory_summary").fetchall()
        assert len(inv) == 1
        assert inv[0]["total_volume_ml"] == 450
        assert inv[0]["bag_count"] == 1

    def test_inventory_summary_empty(self, setup_db):
        conn = setup_db
        inv = conn.execute("SELECT * FROM vw_inventory_summary").fetchall()
        assert len(inv) == 0

    def test_inventory_summary_excludes_empty_bags(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        conn.execute("UPDATE BLOOD_BAG SET current_volume_ml = 0 WHERE 1=1")
        conn.commit()

        inv = conn.execute("SELECT * FROM vw_inventory_summary").fetchall()
        assert len(inv) == 0

    def test_critical_pending_view(self, setup_db):
        conn = setup_db
        r1 = _add_recipient(conn, "Dr. Smith", "Emergency Hospital")
        _add_request(conn, r1, "O-", 500, "Critical")

        crit = conn.execute("SELECT * FROM vw_critical_pending").fetchall()
        assert len(crit) == 1
        assert crit[0]["requested_group"] == "O-"
        assert crit[0]["remaining_ml"] == 500
        assert crit[0]["hospital_name"] == "Emergency Hospital"

    def test_critical_pending_excludes_normal(self, setup_db):
        conn = setup_db
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200, "Normal")

        crit = conn.execute("SELECT * FROM vw_critical_pending").fetchall()
        assert len(crit) == 0

    def test_critical_pending_excludes_fulfilled(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 500)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200, "Critical")

        smart_allocate_all()

        crit = conn.execute("SELECT * FROM vw_critical_pending").fetchall()
        assert len(crit) == 0

    def test_expiring_soon_view_no_expiring(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)

        exp = conn.execute("SELECT * FROM vw_expiring_soon").fetchall()
        assert len(exp) == 0  # 42-day shelf life

    def test_expiring_soon_view_near_expiry(self, setup_db):
        """Manually set expiry to 3 days -> should appear."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)

        soon = _date_str(date.today() + timedelta(days=3))
        conn.execute("UPDATE BLOOD_BAG SET expiry_date = ?", (soon,))
        conn.commit()

        exp = conn.execute("SELECT * FROM vw_expiring_soon").fetchall()
        assert len(exp) == 1
        assert exp[0]["days_until_expiry"] <= 5

    def test_dashboard_stats_returns_three_lists(self, setup_db):
        alerts, inventory, expiring = get_dashboard_stats()
        assert isinstance(alerts, list)
        assert isinstance(inventory, list)
        assert isinstance(expiring, list)


#  FEATURE 5: AUDIT TRAIL


class TestAuditTrail:
    def test_donation_creates_audit_entries(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)

        logs = conn.execute("SELECT * FROM AUDIT_LOG").fetchall()
        assert len(logs) >= 2
        tables = {log["table_name"] for log in logs}
        assert "BLOOD_BAG" in tables
        assert "DONATION_LOG" in tables

    def test_allocation_creates_audit_entries(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()

        logs = conn.execute("SELECT * FROM AUDIT_LOG").fetchall()
        tables = {log["table_name"] for log in logs}
        assert "FULFILLMENT_LOG" in tables
        assert "TRANSFUSION_REQ" in tables

    def test_audit_records_old_new_values_on_update(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()

        update_logs = conn.execute(
            "SELECT * FROM AUDIT_LOG WHERE action_type='UPDATE'"
        ).fetchall()
        assert len(update_logs) > 0
        for log in update_logs:
            assert log["old_value"] is not None
            assert log["new_value"] is not None

    def test_audit_records_insert_action(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        insert_logs = conn.execute(
            "SELECT * FROM AUDIT_LOG WHERE action_type='INSERT'"
        ).fetchall()
        assert len(insert_logs) >= 2  # donation + bag

    def test_audit_timestamp_populated(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        logs = conn.execute("SELECT * FROM AUDIT_LOG").fetchall()
        for log in logs:
            assert log["timestamp"] is not None

    def test_audit_performed_by_default(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        logs = conn.execute("SELECT * FROM AUDIT_LOG").fetchall()
        for log in logs:
            assert log["performed_by"] == "SYSTEM"


#  FEATURE 6: DOMAIN NORMALIZATION (FK constraints)


class TestDomainNormalization:
    def test_fk_rejects_invalid_blood_group(self, setup_db):
        conn = setup_db
        with pytest.raises(Exception):
            conn.execute("INSERT INTO DONOR (name, blood_group) VALUES ('X', 'Z+')")
            conn.commit()

    def test_fk_rejects_invalid_urgency(self, setup_db):
        conn = setup_db
        r1 = _add_recipient(conn)
        with pytest.raises(Exception):
            conn.execute(
                """INSERT INTO TRANSFUSION_REQ
                   (recipient_id, requested_group, quantity_ml,
                    urgency_level, req_date)
                   VALUES (?, 'A+', 100, 'EMERGENCY', DATE('now'))""",
                (r1,),
            )
            conn.commit()

    def test_fk_rejects_invalid_bag_status(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        with pytest.raises(Exception):
            conn.execute("UPDATE BLOOD_BAG SET status = 'Destroyed' WHERE 1=1")
            conn.commit()

    def test_fk_rejects_invalid_component_type(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 100)

        with pytest.raises(Exception):
            conn.execute("UPDATE BLOOD_BAG SET component_type = 'WholeBlood' WHERE 1=1")
            conn.commit()

    def test_all_valid_blood_groups_accepted(self, setup_db):
        conn = setup_db
        for bg in ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"):
            conn.execute(
                "INSERT INTO DONOR (name, blood_group) VALUES (?, ?)",
                (f"Donor_{bg}", bg),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM DONOR").fetchone()[0]
        assert count == 8

    def test_master_tables_populated(self, setup_db):
        """All lookup/master tables should have data after init."""
        conn = setup_db
        assert (
            conn.execute("SELECT COUNT(*) FROM BLOOD_GROUP_MASTER").fetchone()[0] == 8
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM URGENCY_LEVEL_MASTER").fetchone()[0] == 2
        )
        assert conn.execute("SELECT COUNT(*) FROM BAG_STATUS_MASTER").fetchone()[0] == 4
        assert (
            conn.execute("SELECT COUNT(*) FROM REQUEST_STATUS_MASTER").fetchone()[0]
            == 4
        )
        assert conn.execute("SELECT COUNT(*) FROM COMPONENT_MASTER").fetchone()[0] == 5
        assert (
            conn.execute("SELECT COUNT(*) FROM COMPATIBILITY_MATRIX").fetchone()[0]
            == 27
        )


#  FEATURE 7: COMPONENT TRACKING (Item 5)


class TestComponentTracking:
    def test_split_creates_three_bags(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        ok, _ = process_donation(d1, 450, split_components=True)
        assert ok

        bags = conn.execute(
            "SELECT * FROM BLOOD_BAG ORDER BY component_type"
        ).fetchall()
        types = sorted([b["component_type"] for b in bags])
        assert types == ["Plasma", "Platelets", "Red Blood Cells"]

    def test_split_correct_volumes(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450, split_components=True)

        bags = conn.execute("SELECT * FROM BLOOD_BAG").fetchall()
        volumes = {b["component_type"]: b["current_volume_ml"] for b in bags}
        assert volumes["Red Blood Cells"] == 200
        assert volumes["Platelets"] == 50
        assert volumes["Plasma"] == 200

    def test_split_different_shelf_lives(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450, split_components=True)

        bags = conn.execute("SELECT * FROM BLOOD_BAG").fetchall()
        expiries = {b["component_type"]: b["expiry_date"] for b in bags}
        assert expiries["Platelets"] != expiries["Plasma"]
        assert expiries["Red Blood Cells"] != expiries["Plasma"]

    def test_whole_blood_single_bag(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450, split_components=False)

        bags = conn.execute("SELECT * FROM BLOOD_BAG").fetchall()
        assert len(bags) == 1
        assert bags[0]["component_type"] == "Whole Blood"
        assert bags[0]["current_volume_ml"] == 450

    def test_component_request_allocation(self, setup_db):
        """Request for specific component gets matched correctly."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450, split_components=True)

        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 50, component="Platelets")

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Fulfilled"

    def test_component_mismatch_no_allocation(self, setup_db):
        """Request for Plasma should NOT be fulfilled from Whole Blood bags."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450, split_components=False)  # Whole Blood only

        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 100, component="Plasma")

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Pending"
        assert req["quantity_allocated_ml"] == 0


#  FEATURE 8: SOFT DELETES (Item 6)


class TestSoftDeletes:
    def test_deactivated_donor_rejected(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)

        conn.execute("UPDATE DONOR SET is_active = 0 WHERE donor_id = ?", (d1,))
        conn.commit()

        ok, msg = process_donation(d1, 450)
        assert not ok
        assert "not found or inactive" in msg.lower()

    def test_deactivated_donor_data_preserved(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn, "Alice", "O-")
        process_donation(d1, 300)

        conn.execute("UPDATE DONOR SET is_active = 0 WHERE donor_id = ?", (d1,))
        conn.commit()

        donor = conn.execute("SELECT * FROM DONOR WHERE donor_id = ?", (d1,)).fetchone()
        assert donor is not None
        assert donor["name"] == "Alice"
        assert donor["is_active"] == 0

        bags = conn.execute("SELECT * FROM BLOOD_BAG").fetchall()
        assert len(bags) == 1

    def test_deactivated_recipient_data_preserved(self, setup_db):
        conn = setup_db
        r1 = _add_recipient(conn, "Dr. Patel", "Metro Hospital")
        conn.execute(
            "UPDATE RECIPIENT SET is_active = 0 WHERE recipient_id = ?",
            (r1,),
        )
        conn.commit()

        rec = conn.execute(
            "SELECT * FROM RECIPIENT WHERE recipient_id = ?", (r1,)
        ).fetchone()
        assert rec is not None
        assert rec["is_active"] == 0
        assert rec["hospital_name"] == "Metro Hospital"

    def test_default_is_active(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        donor = conn.execute(
            "SELECT is_active FROM DONOR WHERE donor_id=?", (d1,)
        ).fetchone()
        assert donor["is_active"] == 1


#  FEATURE 9: PREDICTIVE SHORTAGE ALERTS (Item 7)


class TestShortageAlerts:
    def test_empty_stock_zero_consumption(self, setup_db):
        """No stock and no consumption -> alerts with 0 projected days."""
        alerts = get_shortage_alerts()
        for a in alerts:
            assert a["projected_days"] < 3

    def test_sufficient_stock_no_alert(self, setup_db):
        """Large stock with low consumption should not trigger alerts."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)

        alerts = get_shortage_alerts()
        a_plus_alerts = [a for a in alerts if a["blood_group"] == "A+"]
        assert len(a_plus_alerts) == 0

    def test_alert_returns_required_fields(self, setup_db):
        alerts = get_shortage_alerts()
        for a in alerts:
            assert "blood_group" in a
            assert "current_ml" in a
            assert "daily_rate" in a
            assert "projected_days" in a


#  FEATURE 10: CROSS-MATCH COMPATIBILITY (Item 8)


class TestCompatibilityScoring:
    def test_prefers_exact_match_over_universal(self, setup_db):
        """A+ blood should be used for A+ request before O-."""
        conn = setup_db
        d_aplus = _add_donor(conn, "DA+", "A+")
        d_ominus = _add_donor(conn, "DO-", "O-")

        process_donation(d_aplus, 300)
        _make_donor_eligible(conn, d_ominus)
        process_donation(d_ominus, 300)

        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 250)

        smart_allocate_all()

        fl = conn.execute(
            """SELECT bb.blood_group
               FROM FULFILLMENT_LOG fl
               JOIN BLOOD_BAG bb ON fl.bag_id = bb.bag_id"""
        ).fetchone()
        assert fl["blood_group"] == "A+"

    def test_falls_back_to_compatible_when_exact_depleted(self, setup_db):
        """When A+ is exhausted, A+ request should use O- (compatible)."""
        conn = setup_db
        d_ominus = _add_donor(conn, "DO-", "O-")
        process_donation(d_ominus, 300)

        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()

        fl = conn.execute(
            """SELECT bb.blood_group
               FROM FULFILLMENT_LOG fl
               JOIN BLOOD_BAG bb ON fl.bag_id = bb.bag_id"""
        ).fetchone()
        assert fl["blood_group"] == "O-"

    def test_incompatible_group_not_used(self, setup_db):
        """B+ blood should NOT be given to A+ request."""
        conn = setup_db
        d_bplus = _add_donor(conn, "DB+", "B+")
        process_donation(d_bplus, 300)

        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Pending"

    def test_compatibility_matrix_integrity(self, setup_db):
        """O- can only receive O-. AB+ can receive from all 8 groups."""
        conn = setup_db
        o_minus = conn.execute(
            "SELECT COUNT(*) FROM COMPATIBILITY_MATRIX WHERE recipient_group='O-'"
        ).fetchone()[0]
        assert o_minus == 1

        ab_plus = conn.execute(
            "SELECT COUNT(*) FROM COMPATIBILITY_MATRIX WHERE recipient_group='AB+'"
        ).fetchone()[0]
        assert ab_plus == 8


#  FEATURE 11: DONOR LOYALTY MODULE (Item 9)


class TestDonorLoyalty:
    def test_score_rare_group_bonus(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn, "Alice", "O-")
        process_donation(d1, 450)

        scores = get_donor_scores()
        assert len(scores) == 1
        s = scores[0]
        assert s["total_donations"] == 1
        assert s["rare_bonus"] == 10
        assert s["is_eligible"] == 0  # just donated

    def test_score_common_group_no_bonus(self, setup_db):
        conn = setup_db
        _add_donor(conn, "Bob", "A+")

        scores = get_donor_scores()
        assert scores[0]["rare_bonus"] == 0

    def test_score_medium_rare_bonus(self, setup_db):
        conn = setup_db
        _add_donor(conn, "Eve", "A-")

        scores = get_donor_scores()
        assert scores[0]["rare_bonus"] == 5

    def test_eligibility_never_donated(self, setup_db):
        conn = setup_db
        _add_donor(conn, "NewDonor", "B+")

        scores = get_donor_scores()
        assert scores[0]["is_eligible"] == 1

    def test_eligibility_after_56_days(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn, "Bob", "B+")
        process_donation(d1, 450)
        _make_donor_eligible(conn, d1)

        scores = get_donor_scores()
        assert scores[0]["is_eligible"] == 1

    def test_eligible_donors_for_group(self, setup_db):
        conn = setup_db
        _add_donor(conn, "Bob", "B+")
        donors = get_eligible_donors_for_group("B+", limit=5)
        assert len(donors) == 1
        assert donors[0]["name"] == "Bob"

    def test_eligible_donors_excludes_recent(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn, "RecentDonor", "A+")
        process_donation(d1, 450)

        donors = get_eligible_donors_for_group("A+", limit=5)
        assert len(donors) == 0

    def test_eligible_donors_excludes_wrong_group(self, setup_db):
        conn = setup_db
        _add_donor(conn, "WrongGroup", "B+")
        donors = get_eligible_donors_for_group("A+", limit=5)
        assert len(donors) == 0

    def test_eligible_donors_excludes_inactive(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn, "Inactive", "A+")
        conn.execute("UPDATE DONOR SET is_active = 0 WHERE donor_id = ?", (d1,))
        conn.commit()

        donors = get_eligible_donors_for_group("A+", limit=5)
        assert len(donors) == 0

    def test_donor_scores_ordered_by_loyalty(self, setup_db):
        """Donor with more donations ranked higher."""
        conn = setup_db
        d1 = _add_donor(conn, "OneTime", "A+")
        d2 = _add_donor(conn, "Repeat", "A+")

        process_donation(d1, 300)

        process_donation(d2, 300)
        _make_donor_eligible(conn, d2)
        process_donation(d2, 300)

        scores = get_donor_scores()
        assert scores[0]["name"] == "Repeat"
        assert scores[0]["total_donations"] == 2

    def test_deactivated_donor_excluded_from_scores(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn, "Gone", "A+")
        conn.execute("UPDATE DONOR SET is_active = 0 WHERE donor_id = ?", (d1,))
        conn.commit()

        scores = get_donor_scores()
        assert len(scores) == 0


#  FEATURE 12: PARTIAL FULFILLMENT (Item 10)


class TestPartialFulfillment:
    def test_partial_when_insufficient_stock(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 200)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 500)

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["quantity_allocated_ml"] == 200
        assert req["status"] == "Partially Fulfilled"

    def test_incremental_fulfillment(self, setup_db):
        """Two allocation rounds gradually fill a request."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 200)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 400)

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Partially Fulfilled"
        assert req["quantity_allocated_ml"] == 200

        d2 = _add_donor(conn, "D2", "A+")
        process_donation(d2, 300)

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["quantity_allocated_ml"] == 400
        assert req["status"] == "Fulfilled"

    def test_zero_stock_stays_pending(self, setup_db):
        conn = setup_db
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Pending"

    def test_fulfillment_log_tracks_each_allocation(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn, "D1", "A+")
        d2 = _add_donor(conn, "D2", "A+")
        process_donation(d1, 150)
        process_donation(d2, 150)

        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 250)

        smart_allocate_all()

        logs = conn.execute("SELECT * FROM FULFILLMENT_LOG").fetchall()
        assert len(logs) == 2
        total = sum(log["quantity_allocated_ml"] for log in logs)
        assert total == 250


#  EDGE CASES


class TestEdgeCases:
    def test_date_str_helper(self, setup_db):
        """_date_str converts date to ISO string."""
        today = date.today()
        assert _date_str(today) == today.isoformat()
        assert _date_str("2024-01-01") == "2024-01-01"

    def test_donation_very_small_quantity(self, setup_db):
        """Donation of 1 ml should work."""
        conn = setup_db
        d1 = _add_donor(conn)
        ok, _ = process_donation(d1, 1)
        assert ok
        bag = conn.execute("SELECT * FROM BLOOD_BAG").fetchone()
        assert bag["current_volume_ml"] == 1

    def test_donation_large_quantity(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        ok, _ = process_donation(d1, 5000)
        assert ok

    def test_allocation_idempotent_when_fulfilled(self, setup_db):
        """Running allocation twice does not double-allocate."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        smart_allocate_all()
        smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["quantity_allocated_ml"] == 200

        logs = conn.execute("SELECT * FROM FULFILLMENT_LOG").fetchall()
        assert len(logs) == 1

    def test_nonexistent_donor_rejected(self, setup_db):
        ok, msg = process_donation(9999, 100)
        assert not ok
        assert "not found" in msg.lower()

    def test_multiple_blood_groups_simultaneous(self, setup_db):
        """Allocation involving multiple blood groups at once."""
        conn = setup_db
        d_ap = _add_donor(conn, "D_A+", "A+")
        d_bp = _add_donor(conn, "D_B+", "B+")
        process_donation(d_ap, 300)
        process_donation(d_bp, 300)

        r1 = _add_recipient(conn)
        req_ap = _add_request(conn, r1, "A+", 200)
        req_bp = _add_request(conn, r1, "B+", 200)

        smart_allocate_all()

        assert (
            conn.execute(
                "SELECT status FROM TRANSFUSION_REQ WHERE req_id=?",
                (req_ap,),
            ).fetchone()["status"]
            == "Fulfilled"
        )
        assert (
            conn.execute(
                "SELECT status FROM TRANSFUSION_REQ WHERE req_id=?",
                (req_bp,),
            ).fetchone()["status"]
            == "Fulfilled"
        )

    def test_process_donation_returns_message(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        ok, msg = process_donation(d1, 450)
        assert ok
        assert "whole-blood" in msg.lower()

    def test_process_donation_split_returns_message(self, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)
        ok, msg = process_donation(d1, 450, split_components=True)
        assert ok
        assert "component" in msg.lower()

    def test_allocate_all_returns_message(self, setup_db):
        ok, msg = smart_allocate_all()
        assert ok
        assert "allocation" in msg.lower()


#  STRESS TESTS


class TestStress:
    def test_many_donors_and_donations(self, setup_db):
        """Create 50 donors with donations and verify integrity."""
        conn = setup_db
        for i in range(50):
            did = _add_donor(conn, f"Donor_{i}", "A+")
            process_donation(did, 450)

        bags = conn.execute("SELECT COUNT(*) FROM BLOOD_BAG").fetchone()[0]
        assert bags == 50

        donations = conn.execute("SELECT COUNT(*) FROM DONATION_LOG").fetchone()[0]
        assert donations == 50

    def test_many_requests_allocation(self, setup_db):
        """20 donors + 30 requests -> allocation runs without error."""
        conn = setup_db
        groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

        for i in range(20):
            bg = groups[i % len(groups)]
            did = _add_donor(conn, f"Donor_{i}", bg)
            process_donation(did, 450)

        r1 = _add_recipient(conn, "StressHospital", "Stress Gen")
        for i in range(30):
            bg = groups[i % len(groups)]
            urgency = "Critical" if i % 5 == 0 else "Normal"
            _add_request(conn, r1, bg, 100 + i * 10, urgency)

        ok, msg = smart_allocate_all()
        assert ok

        fulfilled = conn.execute(
            "SELECT COUNT(*) FROM TRANSFUSION_REQ WHERE status='Fulfilled'"
        ).fetchone()[0]
        assert fulfilled > 0

    def test_audit_log_grows_under_load(self, setup_db):
        """High volume triggers many audit entries."""
        conn = setup_db
        for i in range(10):
            did = _add_donor(conn, f"D{i}", "A+")
            process_donation(did, 200)

        logs = conn.execute("SELECT COUNT(*) FROM AUDIT_LOG").fetchone()[0]
        assert logs >= 20

    def test_concurrent_like_sequential_access(self, setup_db):
        """Simulate concurrent-like access via threads reading data."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)
        smart_allocate_all()

        results = []
        errors = []

        def read_inventory():
            try:
                c = sqlite3.connect(TEST_DB)
                c.row_factory = sqlite3.Row
                c.execute("PRAGMA foreign_keys = ON;")
                rows = c.execute("SELECT * FROM vw_inventory_summary").fetchall()
                results.append(len(rows))
                c.close()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=read_inventory) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10

    def test_repeated_allocation_no_data_corruption(self, setup_db):
        """Run allocation 10 times -- verify no duplicate fulfillments."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200)

        for _ in range(10):
            smart_allocate_all()

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["quantity_allocated_ml"] == 200
        assert req["status"] == "Fulfilled"

        logs = conn.execute("SELECT * FROM FULFILLMENT_LOG").fetchall()
        assert len(logs) == 1


#  FLASK ROUTE INTEGRATION TESTS


class TestRoutes:
    def test_index_get(self, flask_client):
        resp = flask_client.get("/")
        assert resp.status_code == 200
        assert b"Blood Bank" in resp.data or b"Dashboard" in resp.data

    def test_donor_get(self, flask_client):
        resp = flask_client.get("/donor")
        assert resp.status_code == 200
        assert b"Donor" in resp.data

    def test_hospital_get(self, flask_client):
        resp = flask_client.get("/hospital")
        assert resp.status_code == 200
        assert b"Hospital" in resp.data or b"Request" in resp.data

    def test_audit_get(self, flask_client):
        resp = flask_client.get("/audit")
        assert resp.status_code == 200
        assert b"Audit" in resp.data

    def test_register_donor_post(self, flask_client, setup_db):
        resp = flask_client.post(
            "/donor",
            data={
                "register": "true",
                "name": "TestDonor",
                "blood_group": "A+",
                "phone": "555-9999",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        conn = setup_db
        donor = conn.execute("SELECT * FROM DONOR WHERE name='TestDonor'").fetchone()
        assert donor is not None

    def test_log_donation_post(self, flask_client, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)

        resp = flask_client.post(
            "/donor",
            data={
                "donate": "true",
                "donor_id": str(d1),
                "quantity": "450",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        bags = conn.execute("SELECT * FROM BLOOD_BAG").fetchall()
        assert len(bags) == 1

    def test_log_donation_with_split_post(self, flask_client, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)

        resp = flask_client.post(
            "/donor",
            data={
                "donate": "true",
                "donor_id": str(d1),
                "quantity": "450",
                "split_components": "on",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        bags = conn.execute("SELECT * FROM BLOOD_BAG").fetchall()
        assert len(bags) == 3

    def test_deactivate_donor_post(self, flask_client, setup_db):
        conn = setup_db
        d1 = _add_donor(conn)

        resp = flask_client.post(
            "/donor",
            data={"deactivate": "true", "donor_id": str(d1)},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        donor = conn.execute(
            "SELECT is_active FROM DONOR WHERE donor_id=?", (d1,)
        ).fetchone()
        assert donor["is_active"] == 0

    def test_add_hospital_post(self, flask_client, setup_db):
        resp = flask_client.post(
            "/hospital",
            data={
                "add_hospital": "true",
                "name": "Dr. Test",
                "hospital_name": "Test Hospital",
                "contact": "555-0000",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        conn = setup_db
        rec = conn.execute(
            "SELECT * FROM RECIPIENT WHERE hospital_name='Test Hospital'"
        ).fetchone()
        assert rec is not None

    def test_request_blood_post(self, flask_client, setup_db):
        conn = setup_db
        r1 = _add_recipient(conn)

        resp = flask_client.post(
            "/hospital",
            data={
                "request_blood": "true",
                "recipient_id": str(r1),
                "blood_group": "O-",
                "component": "Whole Blood",
                "quantity": "500",
                "urgency": "Critical",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req is not None
        assert req["urgency_level"] == "Critical"

    def test_allocate_all_post(self, flask_client, setup_db):
        resp = flask_client.post("/allocate_all", follow_redirects=True)
        assert resp.status_code == 200

    def test_allocate_all_with_data(self, flask_client, setup_db):
        """Full flow: donate -> request -> allocate -> verify via routes."""
        conn = setup_db
        d1 = _add_donor(conn)
        process_donation(d1, 450)
        r1 = _add_recipient(conn)
        _add_request(conn, r1, "A+", 200, "Critical")

        resp = flask_client.post("/allocate_all", follow_redirects=True)
        assert resp.status_code == 200

        req = conn.execute("SELECT * FROM TRANSFUSION_REQ").fetchone()
        assert req["status"] == "Fulfilled"

    def test_index_shows_flash_messages(self, flask_client, setup_db):
        """Allocate all triggers a flash that appears on redirect to index."""
        resp = flask_client.post("/allocate_all", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Allocation" in resp.data or b"allocation" in resp.data

    def test_404_nonexistent_route(self, flask_client):
        resp = flask_client.get("/nonexistent")
        assert resp.status_code == 404
