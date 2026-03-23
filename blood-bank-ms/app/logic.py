from datetime import date, timedelta
from db import get_db_connection


def _date_str(d):
    """Convert a date to ISO-8601 string for SQLite (avoids deprecated adapter)."""
    return d.isoformat() if isinstance(d, date) else str(d)


# ────────────────────────────────────────────────────────────────────
# Standard component volumes (ml) derived from a single whole-blood
# donation of ≈ 450 ml.
# ────────────────────────────────────────────────────────────────────
COMPONENT_SPLIT = {
    "Red Blood Cells": 200,
    "Platelets": 50,
    "Plasma": 200,
}


# ────────────────────────────────────────────────────────────────────
# 1. DONATION  (Trigger 1-b enforces 56-day rule at DB level)
# ────────────────────────────────────────────────────────────────────


def process_donation(donor_id, quantity_ml, split_components=False):
    """
    Log a donation and create inventory bag(s).

    Parameters
    ----------
    donor_id : int
    quantity_ml : float
    split_components : bool
        If True the donation is separated into RBC, Platelets and Plasma
        bags with individual shelf lives (Item 5). Otherwise a single
        'Whole Blood' bag is created.
    """
    conn = get_db_connection()
    try:
        donor = conn.execute(
            "SELECT blood_group, last_donation_date FROM DONOR "
            "WHERE donor_id = ? AND is_active = 1",
            (donor_id,),
        ).fetchone()
        if not donor:
            raise ValueError("Donor not found or inactive")

        blood_group = donor["blood_group"]
        today = date.today()

        # Application-level safety check (nice error message).
        # DB trigger trg_donation_safety_lock is the hard enforcement.
        if donor["last_donation_date"]:
            days_since = (
                today - date.fromisoformat(str(donor["last_donation_date"]))
            ).days
            if days_since < 56:
                raise ValueError(
                    f"DONATION_SAFETY: Donor must wait {56 - days_since} "
                    "more days before donating again"
                )

        # Insert donation log (trigger fires here)
        today_str = _date_str(today)
        cursor = conn.execute(
            "INSERT INTO DONATION_LOG (donor_id, donation_date, quantity_ml) "
            "VALUES (?, ?, ?)",
            (donor_id, today_str, quantity_ml),
        )
        donation_id = cursor.lastrowid

        # Determine bags to create
        if split_components:
            components = list(COMPONENT_SPLIT.items())
        else:
            components = [("Whole Blood", quantity_ml)]

        for comp_type, vol in components:
            shelf = conn.execute(
                "SELECT shelf_life_days FROM COMPONENT_MASTER WHERE component_type = ?",
                (comp_type,),
            ).fetchone()
            if not shelf:
                raise ValueError(f"Unknown component: {comp_type}")
            expiry = today + timedelta(days=shelf["shelf_life_days"])
            conn.execute(
                "INSERT INTO BLOOD_BAG "
                "(donation_id, blood_group, component_type, collection_date, "
                " expiry_date, initial_volume_ml, current_volume_ml, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'Available')",
                (
                    donation_id,
                    blood_group,
                    comp_type,
                    today_str,
                    _date_str(expiry),
                    vol,
                    vol,
                ),
            )

        # Update donor record
        conn.execute(
            "UPDATE DONOR SET last_donation_date = ? WHERE donor_id = ?",
            (today_str, donor_id),
        )

        conn.commit()
        kind = "component" if split_components else "whole-blood"
        return True, f"Donation processed – {kind} bag(s) created"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────────
# 2. SMART ALLOCATION  (Items 8  & 10 – compatibility scoring,
#                        partial fulfillment)
# ────────────────────────────────────────────────────────────────────


def smart_allocate_all():
    """
    Global allocation algorithm.

    Priority order:
      1. Critical urgency first
      2. Higher quantity needed (descending)

    Within each request the engine uses the COMPATIBILITY_MATRIX table
    so that the closest-match blood group is consumed first and precious
    O− universal-donor blood is conserved (Item 8).

    Supports partial fulfillment: allocates whatever is available and
    lets the DB trigger set 'Partially Fulfilled' or 'Fulfilled' (Item 10).
    """
    conn = get_db_connection()
    allocations_made = 0
    try:
        requests = conn.execute("""
            SELECT * FROM TRANSFUSION_REQ
            WHERE status IN ('Pending', 'Partially Fulfilled')
            ORDER BY
                CASE WHEN urgency_level = 'Critical' THEN 1 ELSE 2 END,
                quantity_ml DESC
        """).fetchall()

        for req in requests:
            req_id = req["req_id"]
            needed = req["quantity_ml"] - req["quantity_allocated_ml"]
            if needed <= 0:
                continue

            # Bags sorted by compatibility preference then FIFO expiry
            bags = conn.execute(
                """
                SELECT bb.bag_id, bb.current_volume_ml, bb.expiry_date,
                       cm.preference_rank
                FROM   BLOOD_BAG bb
                JOIN   COMPATIBILITY_MATRIX cm
                       ON cm.donor_group = bb.blood_group
                WHERE  cm.recipient_group = ?
                  AND  bb.status = 'Available'
                  AND  bb.current_volume_ml > 0
                  AND  bb.component_type = ?
                ORDER  BY cm.preference_rank ASC, bb.expiry_date ASC
            """,
                (req["requested_group"], req["requested_component"]),
            ).fetchall()

            allocated = 0.0
            for bag in bags:
                if allocated >= needed:
                    break
                take = min(bag["current_volume_ml"], needed - allocated)

                # Fulfillment log FIRST  (triggers: volume guard checks
                #   pre-deduction volume, then req allocated update, audit)
                conn.execute(
                    "INSERT INTO FULFILLMENT_LOG "
                    "(req_id, bag_id, quantity_allocated_ml) "
                    "VALUES (?, ?, ?)",
                    (req_id, bag["bag_id"], take),
                )

                # THEN deduct from bag (trigger trg_auto_expire_bag handles
                # setting status = 'Empty' when volume reaches 0)
                new_vol = bag["current_volume_ml"] - take
                conn.execute(
                    "UPDATE BLOOD_BAG SET current_volume_ml = ? WHERE bag_id = ?",
                    (new_vol, bag["bag_id"]),
                )

                allocated += take

            if allocated > 0:
                allocations_made += 1

        conn.commit()
        return True, (f"Allocation complete – processed {allocations_made} request(s).")
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────────
# 3. PREDICTIVE SHORTAGE ALERT ENGINE  (Item 7)
# ────────────────────────────────────────────────────────────────────


def get_shortage_alerts():
    """
    For each blood group calculate *projected stock days* =
      current_volume / avg_daily_consumption (last 30 days).

    Returns a list of dicts for groups with < 3 days supply remaining.
    """
    conn = get_db_connection()

    # Current available stock per blood group
    stock_rows = conn.execute("""
        SELECT blood_group, SUM(current_volume_ml) AS total_ml
        FROM   BLOOD_BAG
        WHERE  status = 'Available'
        GROUP  BY blood_group
    """).fetchall()
    stock = {r["blood_group"]: r["total_ml"] for r in stock_rows}

    # Average daily consumption per group (last 30 days)
    consumption_rows = conn.execute("""
        SELECT bgm.blood_group,
               COALESCE(SUM(fl.quantity_allocated_ml), 0) / 30.0 AS avg_daily
        FROM   BLOOD_GROUP_MASTER bgm
        LEFT JOIN BLOOD_BAG bb
               ON bgm.blood_group = bb.blood_group
        LEFT JOIN FULFILLMENT_LOG fl
               ON fl.bag_id = bb.bag_id
              AND fl.fulfillment_date >= DATE('now', '-30 days')
        GROUP  BY bgm.blood_group
    """).fetchall()

    alerts = []
    for row in consumption_rows:
        bg = row["blood_group"]
        daily = row["avg_daily"]
        current = stock.get(bg, 0)
        if daily > 0:
            proj_days = current / daily
        else:
            proj_days = float("inf") if current > 0 else 0
        if proj_days < 3:
            alerts.append(
                {
                    "blood_group": bg,
                    "current_ml": current,
                    "daily_rate": round(daily, 1),
                    "projected_days": round(proj_days, 1),
                }
            )

    conn.close()
    return alerts


# ────────────────────────────────────────────────────────────────────
# 4. DONOR LOYALTY & ELIGIBILITY MODULE  (Item 9)
# ────────────────────────────────────────────────────────────────────


def get_donor_scores():
    """
    Return all active donors with loyalty metrics.

    Loyalty score = total_donations × 10 + rare_group_bonus
    (O−/AB− → 10,  A−/B− → 5)
    """
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT d.donor_id,
               d.name,
               d.blood_group,
               d.phone,
               d.last_donation_date,
               COUNT(dl.donation_id)            AS total_donations,
               COALESCE(SUM(dl.quantity_ml), 0) AS total_volume_ml,
               CASE
                   WHEN d.last_donation_date IS NULL THEN 1
                   WHEN julianday('now')
                      - julianday(d.last_donation_date) >= 56 THEN 1
                   ELSE 0
               END AS is_eligible,
               CASE
                   WHEN d.blood_group IN ('O-', 'AB-') THEN 10
                   WHEN d.blood_group IN ('A-', 'B-')  THEN 5
                   ELSE 0
               END AS rare_bonus
        FROM   DONOR d
        LEFT   JOIN DONATION_LOG dl ON d.donor_id = dl.donor_id
        WHERE  d.is_active = 1
        GROUP  BY d.donor_id
        ORDER  BY (COUNT(dl.donation_id) * 10
                   + CASE
                       WHEN d.blood_group IN ('O-','AB-') THEN 10
                       WHEN d.blood_group IN ('A-','B-')  THEN 5
                       ELSE 0
                     END) DESC
    """).fetchall()
    conn.close()
    return rows


def get_eligible_donors_for_group(blood_group, limit=5):
    """
    Top *limit* eligible donors of a specific blood group, ordered by
    loyalty (total donations DESC) then days-since-last DESC.

    Used when a shortage alert fires to surface donors to contact.
    """
    conn = get_db_connection()
    donors = conn.execute(
        """
        SELECT d.donor_id, d.name, d.blood_group, d.phone,
               d.last_donation_date,
               COUNT(dl.donation_id) AS total_donations,
               CASE
                   WHEN d.last_donation_date IS NULL THEN 999
                   ELSE CAST(julianday('now')
                           - julianday(d.last_donation_date) AS INTEGER)
               END AS days_since_last
        FROM   DONOR d
        LEFT   JOIN DONATION_LOG dl ON d.donor_id = dl.donor_id
        WHERE  d.blood_group = ? AND d.is_active = 1
        GROUP  BY d.donor_id
        HAVING days_since_last >= 56 OR d.last_donation_date IS NULL
        ORDER  BY total_donations DESC, days_since_last DESC
        LIMIT  ?
    """,
        (blood_group, limit),
    ).fetchall()
    conn.close()
    return donors


# ────────────────────────────────────────────────────────────────────
# 5. DASHBOARD HELPERS  (use SQL Views)
# ────────────────────────────────────────────────────────────────────


def get_dashboard_stats():
    """Aggregate stats consumed by the dashboard route."""
    conn = get_db_connection()
    alerts = conn.execute("SELECT * FROM vw_critical_pending").fetchall()
    inventory = conn.execute("SELECT * FROM vw_inventory_summary").fetchall()
    expiring = conn.execute("SELECT * FROM vw_expiring_soon").fetchall()
    conn.close()
    return alerts, inventory, expiring
