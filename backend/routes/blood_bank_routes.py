import os
import sys
import threading
import importlib.util
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_security import current_user, login_required

# The blood-bank app lives in a sibling folder with a hyphenated name.
# We add that directory to sys.path and import its modules directly.
_BLOOD_BANK_ROOT = Path(__file__).resolve().parents[2] / "blood-bank-ms"
if str(_BLOOD_BANK_ROOT) not in sys.path:
    sys.path.insert(0, str(_BLOOD_BANK_ROOT))

import db as bb_db
import db_init as bb_db_init

_LOGIC_MODULE_PATH = _BLOOD_BANK_ROOT / "app" / "logic.py"
_LOGIC_SPEC = importlib.util.spec_from_file_location(
    "blood_bank_logic", _LOGIC_MODULE_PATH
)
if _LOGIC_SPEC is None or _LOGIC_SPEC.loader is None:
    raise RuntimeError(f"Unable to load blood-bank logic module: {_LOGIC_MODULE_PATH}")
_LOGIC_MODULE = importlib.util.module_from_spec(_LOGIC_SPEC)
_LOGIC_SPEC.loader.exec_module(_LOGIC_MODULE)

get_donor_scores = _LOGIC_MODULE.get_donor_scores
get_eligible_donors_for_group = _LOGIC_MODULE.get_eligible_donors_for_group
get_shortage_alerts = _LOGIC_MODULE.get_shortage_alerts
get_db_connection = _LOGIC_MODULE.get_db_connection
process_donation = _LOGIC_MODULE.process_donation
smart_allocate_all = _LOGIC_MODULE.smart_allocate_all

blood_bank_bp = Blueprint(
    "blood_bank",
    __name__,
    url_prefix="/blood-bank",
    template_folder="../../blood-bank-ms/templates",
)

_init_lock = threading.Lock()


def _is_blood_bank_authorized() -> bool:
    return bool(
        current_user.is_authenticated
        and (
            current_user.has_role("admin") or current_user.has_role("blood_bank_staff")
        )
    )


def blood_bank_role_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _is_blood_bank_authorized():
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def _configure_blood_bank_db_path() -> str:
    configured_path = os.environ.get("BLOODBANK_DB_PATH", "").strip()
    if configured_path:
        db_path = configured_path
    else:
        db_path = os.path.join(current_app.instance_path, "bloodbank.db")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    bb_db.DB_NAME = db_path
    return db_path


def _ensure_blood_bank_db_initialized() -> None:
    with _init_lock:
        db_path = _configure_blood_bank_db_path()
        if not os.path.exists(db_path):
            bb_db_init.init_db()


@blood_bank_bp.before_request
def _bootstrap_blood_bank_db():
    _ensure_blood_bank_db_initialized()


@blood_bank_bp.app_errorhandler(403)
def _blood_bank_forbidden(error):
    if request.path.startswith("/blood-bank"):
        flash(
            "You are not authorized to access the Blood Bank Management System.",
            "danger",
        )
        return redirect(url_for("index"))
    return error


@blood_bank_bp.route("/")
@login_required
@blood_bank_role_required
def index():
    conn = get_db_connection()

    critical_agg = conn.execute(
        """
        SELECT requested_group, SUM(remaining_ml) AS total_needed
        FROM   vw_critical_pending
        GROUP  BY requested_group
        """
    ).fetchall()

    critical_details = conn.execute("SELECT * FROM vw_critical_pending").fetchall()

    inventory_ticker = conn.execute(
        """
        SELECT blood_group,
               SUM(bag_count)       AS bag_count,
               SUM(total_volume_ml) AS total_vol
        FROM   vw_inventory_summary
        GROUP  BY blood_group
        """
    ).fetchall()

    inventory_detail = conn.execute("SELECT * FROM vw_inventory_summary").fetchall()
    expiring_soon = conn.execute("SELECT * FROM vw_expiring_soon").fetchall()

    shortage_alerts = get_shortage_alerts()
    shortage_donors = {}
    for shortage_alert in shortage_alerts:
        blood_group = shortage_alert["blood_group"]
        shortage_donors[blood_group] = get_eligible_donors_for_group(
            blood_group, limit=5
        )

    donations = conn.execute(
        """
        SELECT d.name, dl.donation_date, dl.quantity_ml, dl.donation_id
        FROM   DONATION_LOG dl
        JOIN   DONOR d ON dl.donor_id = d.donor_id
        ORDER  BY dl.donation_date DESC LIMIT 10
        """
    ).fetchall()

    fulfilled_history = conn.execute(
        """
        SELECT r.name AS recipient_name, tr.requested_group,
               tr.requested_component, tr.quantity_ml,
               tr.quantity_allocated_ml, tr.urgency_level,
               fl.quantity_allocated_ml AS fl_allocated,
               fl.fulfillment_date, fl.bag_id
        FROM   FULFILLMENT_LOG fl
        JOIN   TRANSFUSION_REQ tr ON fl.req_id = tr.req_id
        JOIN   RECIPIENT r ON tr.recipient_id = r.recipient_id
        ORDER  BY fl.fulfillment_date DESC LIMIT 10
        """
    ).fetchall()

    full_inventory = conn.execute(
        """
        SELECT * FROM BLOOD_BAG
        WHERE  status = 'Available'
        ORDER  BY expiry_date ASC
        """
    ).fetchall()

    audit_log = conn.execute(
        "SELECT * FROM AUDIT_LOG ORDER BY timestamp DESC LIMIT 25"
    ).fetchall()

    conn.close()

    return render_template(
        "home.html",
        endpoint_prefix="blood_bank.",
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


@blood_bank_bp.route("/allocate_all", methods=["POST"])
@login_required
@blood_bank_role_required
def allocate_all():
    success, message = smart_allocate_all()
    flash(message, "success" if success else "danger")
    return redirect(url_for("blood_bank.index"))


@blood_bank_bp.route("/donor", methods=["GET", "POST"])
@login_required
@blood_bank_role_required
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
            split_components = "split_components" in request.form
            success, message = process_donation(donor_id, quantity, split_components)
            flash(message, "success" if success else "danger")

        elif "deactivate" in request.form:
            donor_id = request.form["donor_id"]
            conn.execute(
                "UPDATE DONOR SET is_active = 0 WHERE donor_id = ?", (donor_id,)
            )
            conn.commit()
            flash("Donor deactivated (soft delete).", "warning")

    donors = conn.execute("SELECT * FROM DONOR WHERE is_active = 1").fetchall()
    donor_scores = get_donor_scores()

    conn.close()
    return render_template(
        "donor.html",
        endpoint_prefix="blood_bank.",
        donors=donors,
        donor_scores=donor_scores,
    )


@blood_bank_bp.route("/hospital", methods=["GET", "POST"])
@login_required
@blood_bank_role_required
def hospital():
    conn = get_db_connection()

    if request.method == "POST":
        if "add_hospital" in request.form:
            name = request.form["name"]
            hospital_name = request.form["hospital_name"]
            contact = request.form["contact"]
            conn.execute(
                "INSERT INTO RECIPIENT (name, hospital_name, contact_info) VALUES (?, ?, ?)",
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
            recipient_id = request.form["recipient_id"]
            conn.execute(
                "UPDATE RECIPIENT SET is_active = 0 WHERE recipient_id = ?",
                (recipient_id,),
            )
            conn.commit()
            flash("Hospital deactivated (soft delete).", "warning")

    recipients = conn.execute(
        "SELECT * FROM RECIPIENT WHERE is_active = 1 ORDER BY hospital_name"
    ).fetchall()

    requests_list = conn.execute(
        """
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
        """
    ).fetchall()

    components = conn.execute("SELECT component_type FROM COMPONENT_MASTER").fetchall()

    conn.close()
    return render_template(
        "hospital.html",
        endpoint_prefix="blood_bank.",
        recipients=recipients,
        requests=requests_list,
        components=components,
    )


@blood_bank_bp.route("/audit")
@login_required
@blood_bank_role_required
def audit():
    conn = get_db_connection()
    logs = conn.execute("SELECT * FROM AUDIT_LOG ORDER BY timestamp DESC").fetchall()
    conn.close()
    return render_template("audit.html", endpoint_prefix="blood_bank.", logs=logs)
