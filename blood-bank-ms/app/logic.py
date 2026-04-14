"""Business logic for donation processing, allocation, forecasting, and donor analytics."""

from datetime import date, datetime, timedelta, timezone
import sqlite3
from typing import TypedDict

from app.settings import (
    COMPONENT_SPLIT_RATIO,
    DONATION_SAFETY_DAYS,
    SHORTAGE_ALERT_DAYS_THRESHOLD,
)
from db import get_db_connection


class ShortageAlert(TypedDict):
    """Structured payload returned by ``get_shortage_alerts``."""

    blood_group: str
    current_ml: float
    daily_rate: float
    projected_days: float


def _date_str(d: date | str) -> str:
    """Return an ISO-8601 date string.

    SQLite stores DATE columns as text in this project, so all write paths
    normalize dates to the same format to keep comparisons and ordering stable.
    """
    return d.isoformat() if isinstance(d, date) else str(d)


def _utc_today() -> date:
    """Return today's date in UTC.

    Using UTC here keeps Python-side date arithmetic aligned with SQLite
    expressions that use DATE('now').
    """
    return datetime.now(timezone.utc).date()


def _utc_today_str() -> str:
    """Return today's UTC date in ISO-8601 string form."""
    return _date_str(_utc_today())


def process_donation(
    donor_id: int,
    quantity_ml: float,
    split_components: bool = False,
) -> tuple[bool, str]:
    """Record a donation and create one or more inventory bags.

    The function performs three layers of safety checks:
    1. Donor existence/activity validation
    2. Positive-volume validation
    3. 56-day eligibility validation

    If ``split_components`` is enabled, the donated quantity is distributed by
    configured component percentages and each component receives its own shelf-life
    derived expiry date.
    """
    conn = get_db_connection()
    try:
        # Read the donor once to obtain eligibility and blood group context.
        donor = conn.execute(
            """
            SELECT blood_group, last_donation_date
            FROM   DONOR
            WHERE  donor_id = ?
              AND  is_active = 1
            """,
            (donor_id,),
        ).fetchone()
        if not donor:
            raise ValueError("Donor not found or inactive")

        # Volume must be strictly positive to prevent negative/zero stock artifacts.
        quantity_ml = float(quantity_ml)
        if quantity_ml <= 0:
            raise ValueError("Quantity must be greater than zero.")

        today = _utc_today()
        today_str = _date_str(today)

        # Application-layer eligibility check provides a clear user-facing message.
        # The database trigger still enforces the same rule as the final guardrail.
        if donor["last_donation_date"]:
            days_since_last = (
                today - date.fromisoformat(str(donor["last_donation_date"]))
            ).days
            if days_since_last < DONATION_SAFETY_DAYS:
                wait_days = DONATION_SAFETY_DAYS - days_since_last
                raise ValueError(
                    f"DONATION_SAFETY: Donor must wait {wait_days} more days before donating again"
                )

        # Insert the donation event first so bag rows can reference donation_id.
        donation_cursor = conn.execute(
            """
            INSERT INTO DONATION_LOG (donor_id, donation_date, quantity_ml)
            VALUES (?, ?, ?)
            """,
            (donor_id, today_str, quantity_ml),
        )
        donation_id = donation_cursor.lastrowid

        # Build the component list for bag creation.
        if split_components:
            red_cells_ml = round(
                quantity_ml * COMPONENT_SPLIT_RATIO["Red Blood Cells"], 2
            )
            platelets_ml = round(quantity_ml * COMPONENT_SPLIT_RATIO["Platelets"], 2)

            # Use residual assignment on plasma so component totals always sum exactly.
            plasma_ml = round(quantity_ml - red_cells_ml - platelets_ml, 2)
            component_allocations: list[tuple[str, float]] = [
                ("Red Blood Cells", red_cells_ml),
                ("Platelets", platelets_ml),
                ("Plasma", plasma_ml),
            ]
        else:
            component_allocations = [("Whole Blood", quantity_ml)]

        # Create one BLOOD_BAG row per component allocation.
        for component_type, volume_ml in component_allocations:
            shelf_life_row = conn.execute(
                """
                SELECT shelf_life_days
                FROM   COMPONENT_MASTER
                WHERE  component_type = ?
                """,
                (component_type,),
            ).fetchone()
            if not shelf_life_row:
                raise ValueError(f"Unknown component: {component_type}")

            expiry_date = today + timedelta(days=shelf_life_row["shelf_life_days"])
            conn.execute(
                """
                INSERT INTO BLOOD_BAG (
                    donation_id,
                    blood_group,
                    component_type,
                    collection_date,
                    expiry_date,
                    initial_volume_ml,
                    current_volume_ml,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Available')
                """,
                (
                    donation_id,
                    donor["blood_group"],
                    component_type,
                    today_str,
                    _date_str(expiry_date),
                    volume_ml,
                    volume_ml,
                ),
            )

        # Persist donor's new last donation timestamp.
        conn.execute(
            "UPDATE DONOR SET last_donation_date = ? WHERE donor_id = ?",
            (today_str, donor_id),
        )

        conn.commit()
        bag_mode = "component" if split_components else "whole-blood"
        return True, f"Donation processed – {bag_mode} bag(s) created"
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def smart_allocate_all() -> tuple[bool, str]:
    """Allocate available blood to pending requests in priority order.

    Prioritization rules:
    1. Critical requests before Normal requests
    2. Higher requested volume first within the same urgency

    Compatibility and bag ordering rules:
    1. Use COMPATIBILITY_MATRIX preference rank (closest match first)
    2. Within the same compatibility rank, consume earliest-expiring bags first
    """
    conn = get_db_connection()
    allocations_made = 0
    try:
        # Select only actionable requests for active hospitals.
        requests = conn.execute(
            """
            SELECT tr.*
            FROM   TRANSFUSION_REQ tr
            JOIN   RECIPIENT r ON tr.recipient_id = r.recipient_id
            WHERE  tr.status IN ('Pending', 'Partially Fulfilled')
              AND  r.is_active = 1
            ORDER  BY
                CASE WHEN tr.urgency_level = 'Critical' THEN 1 ELSE 2 END,
                tr.quantity_ml DESC
            """
        ).fetchall()

        for request_row in requests:
            req_id = request_row["req_id"]
            remaining_ml = (
                request_row["quantity_ml"] - request_row["quantity_allocated_ml"]
            )
            if remaining_ml <= 0:
                continue

            # Retrieve compatible, unexpired, non-empty bags for the requested component.
            bags = conn.execute(
                """
                SELECT bb.bag_id, bb.current_volume_ml, bb.expiry_date, cm.preference_rank
                FROM   BLOOD_BAG bb
                JOIN   COMPATIBILITY_MATRIX cm ON cm.donor_group = bb.blood_group
                WHERE  cm.recipient_group = ?
                  AND  bb.status = 'Available'
                  AND  bb.current_volume_ml > 0
                  AND  bb.component_type = ?
                  AND  bb.expiry_date >= DATE('now')
                ORDER  BY cm.preference_rank ASC, bb.expiry_date ASC
                """,
                (request_row["requested_group"], request_row["requested_component"]),
            ).fetchall()

            allocated_ml = 0.0
            for bag in bags:
                if allocated_ml >= remaining_ml:
                    break

                take_ml = min(bag["current_volume_ml"], remaining_ml - allocated_ml)

                # Insert fulfillment first so triggers can enforce and update request totals.
                conn.execute(
                    """
                    INSERT INTO FULFILLMENT_LOG (req_id, bag_id, quantity_allocated_ml)
                    VALUES (?, ?, ?)
                    """,
                    (req_id, bag["bag_id"], take_ml),
                )

                # Deduct consumed volume from the source bag.
                new_volume_ml = bag["current_volume_ml"] - take_ml
                conn.execute(
                    "UPDATE BLOOD_BAG SET current_volume_ml = ? WHERE bag_id = ?",
                    (new_volume_ml, bag["bag_id"]),
                )

                allocated_ml += take_ml

            if allocated_ml > 0:
                allocations_made += 1

        conn.commit()
        return True, f"Allocation complete – processed {allocations_made} request(s)."
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def get_shortage_alerts() -> list[ShortageAlert]:
    """Return shortage alerts derived from projected days of stock coverage.

    Daily consumption uses a dynamic denominator:
    - If the system is new, divide by active days since first fulfillment.
    - If older than 30 days, cap the denominator at 30.
    - Always divide by at least 1 day.
    """
    conn = get_db_connection()

    # Determine the effective analysis window length in days.
    first_fulfillment_row = conn.execute(
        "SELECT MIN(fulfillment_date) AS first_fulfillment_date FROM FULFILLMENT_LOG"
    ).fetchone()

    days_window = 1
    if first_fulfillment_row and first_fulfillment_row["first_fulfillment_date"]:
        first_fulfillment_date = date.fromisoformat(
            str(first_fulfillment_row["first_fulfillment_date"])
        )
        days_active = (_utc_today() - first_fulfillment_date).days + 1
        days_window = min(max(days_active, 1), 30)

    # DATE('now', '-N days') syntax used in the SQL filter.
    window_offset = f"-{days_window - 1} days"

    # Aggregate currently usable stock (exclude already-expired bags).
    stock_rows = conn.execute(
        """
        SELECT blood_group, SUM(current_volume_ml) AS total_ml
        FROM   BLOOD_BAG
        WHERE  status = 'Available'
          AND  expiry_date >= DATE('now')
        GROUP  BY blood_group
        """
    ).fetchall()
    stock_by_group = {row["blood_group"]: row["total_ml"] for row in stock_rows}

    # Compute average daily consumption over the active window.
    consumption_rows = conn.execute(
        """
        SELECT bgm.blood_group,
               COALESCE(SUM(fl.quantity_allocated_ml), 0) / ? AS avg_daily
        FROM   BLOOD_GROUP_MASTER bgm
        LEFT JOIN BLOOD_BAG bb ON bgm.blood_group = bb.blood_group
        LEFT JOIN FULFILLMENT_LOG fl
               ON fl.bag_id = bb.bag_id
              AND fl.fulfillment_date >= DATE('now', ?)
        GROUP  BY bgm.blood_group
        """,
        (float(days_window), window_offset),
    ).fetchall()

    alerts: list[ShortageAlert] = []
    for row in consumption_rows:
        blood_group = str(row["blood_group"])
        avg_daily = float(row["avg_daily"])
        current_ml = float(stock_by_group.get(blood_group, 0) or 0)

        if avg_daily > 0:
            projected_days = current_ml / avg_daily
        else:
            projected_days = float("inf") if current_ml > 0 else 0.0

        if projected_days < SHORTAGE_ALERT_DAYS_THRESHOLD:
            alerts.append(
                {
                    "blood_group": blood_group,
                    "current_ml": current_ml,
                    "daily_rate": round(avg_daily, 1),
                    "projected_days": round(projected_days, 1),
                }
            )

    conn.close()
    return alerts


def get_donor_scores() -> list[sqlite3.Row]:
    """Return loyalty and eligibility metrics for active donors.

    Score formula:
    ``total_donations * 10 + rare_group_bonus``
    """
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT d.donor_id,
               d.name,
               d.blood_group,
               d.phone,
               d.last_donation_date,
               COUNT(dl.donation_id)            AS total_donations,
               COALESCE(SUM(dl.quantity_ml), 0) AS total_volume_ml,
               CASE
                   WHEN d.last_donation_date IS NULL THEN 1
                   WHEN julianday('now') - julianday(d.last_donation_date) >= ? THEN 1
                   ELSE 0
               END AS is_eligible,
               CASE
                   WHEN d.blood_group IN ('O-', 'AB-') THEN 10
                   WHEN d.blood_group IN ('A-', 'B-')  THEN 5
                   ELSE 0
               END AS rare_bonus
        FROM   DONOR d
        LEFT JOIN DONATION_LOG dl ON d.donor_id = dl.donor_id
        WHERE  d.is_active = 1
        GROUP  BY d.donor_id
        ORDER  BY (
            COUNT(dl.donation_id) * 10 +
            CASE
                WHEN d.blood_group IN ('O-', 'AB-') THEN 10
                WHEN d.blood_group IN ('A-', 'B-')  THEN 5
                ELSE 0
            END
        ) DESC
        """,
        (DONATION_SAFETY_DAYS,),
    ).fetchall()
    conn.close()
    return rows


def get_eligible_donors_for_group(
    blood_group: str,
    limit: int = 5,
) -> list[sqlite3.Row]:
    """Return top eligible donors for a specific blood group.

    Ranking order:
    1. Higher donation count
    2. Longer interval since last donation
    """
    conn = get_db_connection()
    donors = conn.execute(
        """
        SELECT d.donor_id,
               d.name,
               d.blood_group,
               d.phone,
               d.last_donation_date,
               COUNT(dl.donation_id) AS total_donations,
               CASE
                   WHEN d.last_donation_date IS NULL THEN 999
                   ELSE CAST(julianday('now') - julianday(d.last_donation_date) AS INTEGER)
               END AS days_since_last
        FROM   DONOR d
        LEFT JOIN DONATION_LOG dl ON d.donor_id = dl.donor_id
        WHERE  d.blood_group = ?
          AND  d.is_active = 1
        GROUP  BY d.donor_id
        HAVING days_since_last >= ? OR d.last_donation_date IS NULL
        ORDER  BY total_donations DESC, days_since_last DESC
        LIMIT  ?
        """,
        (blood_group, DONATION_SAFETY_DAYS, limit),
    ).fetchall()
    conn.close()
    return donors


def get_dashboard_stats() -> tuple[
    list[sqlite3.Row], list[sqlite3.Row], list[sqlite3.Row]
]:
    """Fetch view-backed dashboard sections in one helper.

    Returns:
        A tuple of ``(critical_alerts, inventory_summary, expiring_soon)``.
    """
    conn = get_db_connection()
    critical_alerts = conn.execute("SELECT * FROM vw_critical_pending").fetchall()
    inventory_summary = conn.execute("SELECT * FROM vw_inventory_summary").fetchall()
    expiring_soon = conn.execute("SELECT * FROM vw_expiring_soon").fetchall()
    conn.close()
    return critical_alerts, inventory_summary, expiring_soon
