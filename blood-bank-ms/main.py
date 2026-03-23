from flask import Flask, render_template, request, redirect, url_for, flash
from app.logic import (
    process_donation,
    smart_allocate_all,
    get_shortage_alerts,
    get_donor_scores,
    get_eligible_donors_for_group,
    get_db_connection,
)

app = Flask(__name__)
app.secret_key = "super_secret_key"


# ───────────────────────── DASHBOARD ─────────────────────────


@app.route("/")
def index():
    conn = get_db_connection()

    # Critical alerts – aggregated for banner (from view)
    critical_agg = conn.execute("""
        SELECT requested_group, SUM(remaining_ml) AS total_needed
        FROM   vw_critical_pending
        GROUP  BY requested_group
    """).fetchall()

    # Critical details (per-request)
    critical_details = conn.execute("SELECT * FROM vw_critical_pending").fetchall()

    # Inventory ticker (aggregate by blood group only)
    inventory_ticker = conn.execute("""
        SELECT blood_group,
               SUM(bag_count)       AS bag_count,
               SUM(total_volume_ml) AS total_vol
        FROM   vw_inventory_summary
        GROUP  BY blood_group
    """).fetchall()

    # Detailed inventory by group + component
    inventory_detail = conn.execute("SELECT * FROM vw_inventory_summary").fetchall()

    # Expiring soon (from view)
    expiring_soon = conn.execute("SELECT * FROM vw_expiring_soon").fetchall()

    # Predictive shortage alerts (Item 7)
    shortage_alerts = get_shortage_alerts()

    # Shortage donor suggestions (Item 9)
    shortage_donors = {}
    for sa in shortage_alerts:
        bg = sa["blood_group"]
        shortage_donors[bg] = get_eligible_donors_for_group(bg, limit=5)

    # Donation history
    donations = conn.execute("""
        SELECT d.name, dl.donation_date, dl.quantity_ml, dl.donation_id
        FROM   DONATION_LOG dl
        JOIN   DONOR d ON dl.donor_id = d.donor_id
        ORDER  BY dl.donation_date DESC LIMIT 10
    """).fetchall()

    # Fulfilled / partially fulfilled
    fulfilled_history = conn.execute("""
        SELECT r.name AS recipient_name, tr.requested_group,
               tr.requested_component, tr.quantity_ml,
               tr.quantity_allocated_ml, tr.urgency_level,
               fl.quantity_allocated_ml AS fl_allocated,
               fl.fulfillment_date, fl.bag_id
        FROM   FULFILLMENT_LOG fl
        JOIN   TRANSFUSION_REQ tr ON fl.req_id = tr.req_id
        JOIN   RECIPIENT r ON tr.recipient_id = r.recipient_id
        ORDER  BY fl.fulfillment_date DESC LIMIT 10
    """).fetchall()

    # Full inventory detail
    full_inventory = conn.execute("""
        SELECT * FROM BLOOD_BAG
        WHERE  status = 'Available'
        ORDER  BY expiry_date ASC
    """).fetchall()

    # Audit trail (latest 25)
    audit_log = conn.execute(
        "SELECT * FROM AUDIT_LOG ORDER BY timestamp DESC LIMIT 25"
    ).fetchall()

    conn.close()
    return render_template(
        "home.html",
        alerts=critical_agg,
        critical_details=critical_details,
        inventory=inventory_ticker,
        inventory_detail=inventory_detail,
        shortage_alerts=shortage_alerts,
        shortage_donors=shortage_donors,
        expiring_soon=expiring_soon,
        donations=donations,
        fulfilled=fulfilled_history,
        full_inventory=full_inventory,
        audit_log=audit_log,
    )


@app.route("/allocate_all", methods=["POST"])
def allocate_all():
    success, msg = smart_allocate_all()
    flash(msg, "success" if success else "danger")
    return redirect(url_for("index"))


# ───────────────────────── DONOR ─────────────────────────────


@app.route("/donor", methods=["GET", "POST"])
def donor():
    conn = get_db_connection()
    if request.method == "POST":
        if "register" in request.form:
            name = request.form["name"]
            blood_group = request.form["blood_group"]
            phone = request.form["phone"]
            conn.execute(
                "INSERT INTO DONOR (name, blood_group, phone) VALUES (?, ?, ?)",
                (name, blood_group, phone),
            )
            conn.commit()
            flash("Donor Registered Successfully!", "success")

        elif "donate" in request.form:
            donor_id = request.form["donor_id"]
            quantity = float(request.form["quantity"])
            split = "split_components" in request.form
            success, message = process_donation(donor_id, quantity, split)
            flash(message, "success" if success else "danger")

        elif "deactivate" in request.form:
            did = request.form["donor_id"]
            conn.execute("UPDATE DONOR SET is_active = 0 WHERE donor_id = ?", (did,))
            conn.commit()
            flash("Donor deactivated (soft delete).", "warning")

    donors = conn.execute("SELECT * FROM DONOR WHERE is_active = 1").fetchall()
    donor_scores = get_donor_scores()
    conn.close()
    return render_template("donor.html", donors=donors, donor_scores=donor_scores)


# ───────────────────────── HOSPITAL / REQUESTS ───────────────


@app.route("/hospital", methods=["GET", "POST"])
def hospital():
    conn = get_db_connection()
    if request.method == "POST":
        if "add_hospital" in request.form:
            name = request.form["name"]
            hospital_name = request.form["hospital_name"]
            contact = request.form["contact"]
            conn.execute(
                "INSERT INTO RECIPIENT (name, hospital_name, contact_info) "
                "VALUES (?, ?, ?)",
                (name, hospital_name, contact),
            )
            conn.commit()
            flash("Hospital Added Successfully!", "success")

        elif "request_blood" in request.form:
            recipient_id = request.form["recipient_id"]
            blood_group = request.form["blood_group"]
            component = request.form.get("component", "Whole Blood")
            quantity = float(request.form["quantity"])
            urgency = request.form["urgency"]
            conn.execute(
                """
                INSERT INTO TRANSFUSION_REQ
                    (recipient_id, requested_group, requested_component,
                     quantity_ml, urgency_level, req_date)
                VALUES (?, ?, ?, ?, ?, DATE('now'))
            """,
                (recipient_id, blood_group, component, quantity, urgency),
            )
            conn.commit()
            flash("Blood request logged.", "info")

        elif "deactivate_hospital" in request.form:
            rid = request.form["recipient_id"]
            conn.execute(
                "UPDATE RECIPIENT SET is_active = 0 WHERE recipient_id = ?", (rid,)
            )
            conn.commit()
            flash("Hospital deactivated (soft delete).", "warning")

    recipients = conn.execute(
        "SELECT * FROM RECIPIENT WHERE is_active = 1 ORDER BY hospital_name"
    ).fetchall()

    # All non-fulfilled requests (includes Partially Fulfilled – Item 10)
    requests_list = conn.execute("""
        SELECT r.req_id, r.requested_group, r.requested_component,
               r.quantity_ml, r.quantity_allocated_ml,
               r.urgency_level, r.status,
               rec.name AS recipient_name, rec.hospital_name
        FROM   TRANSFUSION_REQ r
        JOIN   RECIPIENT rec ON r.recipient_id = rec.recipient_id
        WHERE  r.status IN ('Pending', 'Partially Fulfilled')
        ORDER  BY
            CASE WHEN r.urgency_level = 'Critical' THEN 1 ELSE 2 END,
            r.quantity_ml DESC
    """).fetchall()

    # Component types for the form
    components = conn.execute("SELECT component_type FROM COMPONENT_MASTER").fetchall()

    conn.close()
    return render_template(
        "hospital.html",
        recipients=recipients,
        requests=requests_list,
        components=components,
    )


# ───────────────────────── AUDIT TRAIL ───────────────────────


@app.route("/audit")
def audit():
    conn = get_db_connection()
    logs = conn.execute("SELECT * FROM AUDIT_LOG ORDER BY timestamp DESC").fetchall()
    conn.close()
    return render_template("audit.html", logs=logs)


if __name__ == "__main__":
    app.run(debug=True)
