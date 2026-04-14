"""
Admin Routes Module.

This module contains all routes for admin functionality including:
- Dashboard statistics
- Doctor management (CRUD)
- Patient management with search (by name, ID, contact)
- Export job status monitoring

All routes require admin role authentication.

Author: Abdul Ahad
"""

from flask import Blueprint, request, jsonify, current_app
from flask_security import roles_required, current_user
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from pydantic import ValidationError

from backend.errors import problem
from backend.extensions import cache
from backend.schemas import (
    CreateDepartmentRequest,
    CreateDoctorRequest,
    UpdateDoctorRequest,
    UpdatePatientRequest,
)
from models.database import (
    db,
    User,
    Doctor,
    Patient,
    Appointment,
    ExportJob,
    Department,
    Payment,
    Treatment,
    AuditLog,
)

# Create Blueprint for admin routes
admin_bp = Blueprint("admin", __name__)


# Canonical weekday order used to normalize admin-submitted availability.
# This guarantees consistent storage order regardless of checkbox click order.
WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _normalize_availability_payload(data):
    """Validate and normalize doctor availability payload.

    Returns:
        tuple(dict|None, str|None): normalized payload and error message.
    """
    days = data.get("availability_days") or ["Mon", "Tue", "Wed", "Thu", "Fri"]
    if not isinstance(days, list):
        return None, "availability_days must be a list"

    normalized_days = [day for day in WEEKDAY_ORDER if day in set(days)]
    if not normalized_days:
        return None, "At least one availability day is required"

    availability_start = (data.get("availability_start") or "09:00").strip()
    availability_end = (data.get("availability_end") or "17:00").strip()

    try:
        start_hour, start_minute = [
            int(part) for part in availability_start.split(":", 1)
        ]
        end_hour, end_minute = [int(part) for part in availability_end.split(":", 1)]
    except Exception:
        return None, "availability_start and availability_end must be in HH:MM format"

    start_minutes = (start_hour * 60) + start_minute
    end_minutes = (end_hour * 60) + end_minute
    if end_minutes <= start_minutes:
        return None, "availability_end must be later than availability_start"

    slot_minutes = int(data.get("slot_minutes", 30) or 30)
    if slot_minutes < 10 or slot_minutes > 60:
        return None, "slot_minutes must be between 10 and 60"

    return {
        "availability_days": normalized_days,
        "availability_start": availability_start,
        "availability_end": availability_end,
        "slot_minutes": slot_minutes,
    }, None


# Statistics Routes


@admin_bp.route("/admin/stats", methods=["GET"])
@roles_required("admin")
def admin_stats():
    """
    Get dashboard statistics for admin.

    Returns counts of doctors, patients, and appointments.
    Results are cached for 5 minutes to improve performance.

    Returns:
        JSON object with total_doctors, total_patients, total_appointments
    """
    # Try to get from cache first (5 minute expiry)
    cache_key = "admin_stats"
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    # Calculate statistics
    stats = {
        "total_doctors": Doctor.query.count(),
        "total_patients": Patient.query.count(),
        "total_appointments": Appointment.query.count(),
        "completed_appointments": Appointment.query.filter_by(
            status="Completed"
        ).count(),
        "booked_appointments": Appointment.query.filter_by(status="Booked").count(),
        "cancelled_appointments": Appointment.query.filter_by(
            status="Cancelled"
        ).count(),
    }

    # Cache the results for 5 minutes (300 seconds)
    cache.set(cache_key, stats, timeout=300)

    return jsonify(stats)


# Doctor Management Routes


@admin_bp.route("/admin/doctors", methods=["GET", "POST"])
@roles_required("admin")
def manage_doctors():
    """
    Manage doctors - GET list or POST create new doctor.

    GET: Returns list of all doctors with optional search by name or specialization.
    POST: Creates a new doctor user with profile.

    Query Parameters (GET):
        search: Search string for doctor name or department

    Request Body (POST):
        username: Doctor's login username
        password: Doctor's password
        name: Doctor's full name
        department_id: ID of the department
        availability: Optional availability schedule
        email: Optional email address
        phone: Optional phone number

    Returns:
        GET: List of doctor dictionaries
        POST: Success message
    """
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            data = CreateDoctorRequest(**payload).model_dump(exclude_unset=True)
        except ValidationError as exc:
            return problem(
                422,
                "Validation Error",
                "Request validation failed",
                errors=exc.errors(),
            )

        user_datastore = current_app.extensions["security"].datastore

        availability_payload, availability_error = _normalize_availability_payload(data)
        if availability_error:
            return jsonify({"message": availability_error}), 400

        # Check for duplicate username
        if User.query.filter_by(username=data["username"]).first():
            return jsonify({"message": "Username already exists"}), 400

        # Check for duplicate email if provided
        if data.get("email") and User.query.filter_by(email=data["email"]).first():
            return jsonify({"message": "Email already exists"}), 400

        # Create new user with doctor role
        new_user = user_datastore.create_user(
            username=data["username"],
            email=data.get("email"),
            phone=data.get("phone"),
            password=data["password"],
            name=data["name"],
            active=True,
        )
        new_user.set_password(data["password"])
        user_datastore.add_role_to_user(new_user, "doctor")
        db.session.commit()  # Commit to get user ID

        # Create Doctor Profile.
        # `availability` remains as a human-readable summary for backwards compatibility,
        # while structured fields drive slot calculations in patient booking APIs.
        new_doctor = Doctor(
            user_id=new_user.id,
            department_id=data["department_id"],
            availability=(
                f"{','.join(availability_payload['availability_days'])} "
                f"{availability_payload['availability_start']}-{availability_payload['availability_end']}"
            ),
            availability_days=",".join(availability_payload["availability_days"]),
            availability_start=availability_payload["availability_start"],
            availability_end=availability_payload["availability_end"],
            slot_minutes=availability_payload["slot_minutes"],
            bio=data.get("bio", ""),
            email_notifications=data.get("email_notifications", True),
            appointment_cost=float(data.get("appointment_cost") or 500.0),
        )
        db.session.add(new_doctor)
        db.session.commit()

        # Invalidate cache after adding doctor
        cache.delete("admin_stats")
        cache.delete("all_doctors")

        return jsonify({"message": "Doctor added successfully"}), 201

    # GET - with optional search
    search = request.args.get("search", "").strip()
    department_id = request.args.get("department_id", type=int)

    # Build query with search
    query = Doctor.query.join(User).join(Doctor.department)

    if search:
        # Search by doctor name, username, email, or department name
        from models.database import Department

        query = query.filter(
            or_(
                User.name.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                Department.name.ilike(f"%{search}%"),
            )
        )

    if department_id:
        query = query.filter(Doctor.department_id == department_id)

    doctors = query.all()
    return jsonify([d.to_dict() for d in doctors])


@admin_bp.route("/admin/doctors/<int:id>", methods=["PUT"])
@roles_required("admin")
def update_doctor(id):
    """Update doctor and linked user profile information."""
    doctor = Doctor.query.get_or_404(id)
    user = User.query.get_or_404(doctor.user_id)
    payload = request.get_json(silent=True) or {}
    try:
        data = UpdateDoctorRequest(**payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        return problem(
            422,
            "Validation Error",
            "Request validation failed",
            errors=exc.errors(),
        )

    if "username" in data and data["username"] != user.username:
        if User.query.filter(
            User.username == data["username"], User.id != user.id
        ).first():
            return jsonify({"message": "Username already exists"}), 400
        user.username = data["username"]

    if "email" in data:
        email = data.get("email") or None
        if email and User.query.filter(User.email == email, User.id != user.id).first():
            return jsonify({"message": "Email already exists"}), 400
        user.email = email

    if "name" in data:
        user.name = data.get("name") or user.name
    if "phone" in data:
        user.phone = data.get("phone")
    if data.get("password"):
        user.set_password(data["password"])

    if "department_id" in data:
        doctor.department_id = int(data["department_id"])
    if "bio" in data:
        doctor.bio = data.get("bio") or ""
    if "email_notifications" in data:
        doctor.email_notifications = bool(data.get("email_notifications"))
    if "appointment_cost" in data:
        try:
            cost = float(data["appointment_cost"])
            if cost < 0:
                return jsonify(
                    {"message": "appointment_cost must be non-negative"}
                ), 400
            doctor.appointment_cost = cost
        except TypeError, ValueError:
            return jsonify({"message": "appointment_cost must be a number"}), 400

    availability_payload, availability_error = _normalize_availability_payload(
        {
            "availability_days": data.get(
                "availability_days", doctor.get_availability_days()
            ),
            "availability_start": data.get(
                "availability_start", doctor.availability_start
            ),
            "availability_end": data.get("availability_end", doctor.availability_end),
            "slot_minutes": data.get("slot_minutes", doctor.slot_minutes),
        }
    )
    if availability_error:
        return jsonify({"message": availability_error}), 400

    doctor.availability_days = ",".join(availability_payload["availability_days"])
    doctor.availability_start = availability_payload["availability_start"]
    doctor.availability_end = availability_payload["availability_end"]
    doctor.slot_minutes = availability_payload["slot_minutes"]
    doctor.availability = (
        f"{doctor.availability_days} "
        f"{doctor.availability_start}-{doctor.availability_end}"
    )

    db.session.commit()
    cache.delete("all_doctors")
    return jsonify(
        {"message": "Doctor updated successfully", "doctor": doctor.to_dict()}
    )


@admin_bp.route("/departments", methods=["GET", "POST"])
def manage_departments():
    """List departments or create a new department.

    GET:
        Returns all departments, optionally filtered by `search` substring.
        Filtering is case-insensitive via SQL ILIKE.

    POST:
        Admin-only route used by the department picker flow. Accepts
        a new department name and optional description and returns the
        created (or existing) department object for immediate UI selection.
    """
    if request.method == "POST":
        if not current_user.is_authenticated or not current_user.has_role("admin"):
            return jsonify({"message": "Unauthorized"}), 403

        payload = request.get_json(silent=True) or {}
        try:
            data = CreateDepartmentRequest(**payload)
        except ValidationError as exc:
            return problem(
                422,
                "Validation Error",
                "Request validation failed",
                errors=exc.errors(),
            )

        name = (data.name or "").strip()
        description = (data.description or "").strip()

        if not name:
            return jsonify({"message": "Department name is required"}), 400

        # Case-insensitive duplicate protection prevents near-identical entries
        # like "Cardiology" and "cardiology".
        existing = Department.query.filter(Department.name.ilike(name)).first()
        if existing:
            return jsonify(
                {
                    "message": "A department with this name already exists",
                    "department": existing.to_dict(),
                }
            ), 409

        department = Department(name=name, description=description)
        db.session.add(department)
        db.session.commit()

        cache.delete("all_departments")
        return jsonify(
            {"message": "Department created", "department": department.to_dict()}
        ), 201

    search = request.args.get("search", "").strip()
    query = Department.query
    if search:
        query = query.filter(Department.name.ilike(f"%{search}%"))
    departments = query.order_by(Department.name.asc()).all()
    return jsonify([department.to_dict() for department in departments])


@admin_bp.route("/departments/<int:id>", methods=["DELETE"])
@roles_required("admin")
def delete_department(id):
    """Delete a department by ID.

    Prevents deletion if doctors are still assigned to this department.
    Admin must reassign or delete those doctors first.

    Returns:
        Success message, 400 if doctors still assigned, or 404 if not found.
    """
    dept = Department.query.get_or_404(id)
    # Check if any doctors are assigned
    assigned_count = Doctor.query.filter_by(department_id=id).count()
    if assigned_count > 0:
        return jsonify(
            {
                "message": f"Cannot delete department: {assigned_count} doctor(s) still assigned. Reassign or delete those doctors first."
            }
        ), 400
    db.session.delete(dept)
    db.session.commit()
    cache.delete("all_departments")
    return jsonify({"message": "Department deleted"})


@admin_bp.route("/admin/doctors/<int:id>", methods=["DELETE"])
@roles_required("admin")
def delete_doctor(id):
    """
    Delete a doctor by ID.

    Also deletes the associated user account.

    Args:
        id: Doctor ID to delete

    Returns:
        Success message or 404 if doctor not found
    """
    doctor = Doctor.query.get_or_404(id)
    user = User.query.get(doctor.user_id)

    # Delete all doctor-linked appointment children first to satisfy FK constraints.
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    appointment_ids = [appointment.id for appointment in appointments]
    if appointment_ids:
        Payment.query.filter(Payment.appointment_id.in_(appointment_ids)).delete(
            synchronize_session=False
        )
        Treatment.query.filter(Treatment.appointment_id.in_(appointment_ids)).delete(
            synchronize_session=False
        )
        Appointment.query.filter(Appointment.id.in_(appointment_ids)).delete(
            synchronize_session=False
        )

    # Delete doctor profile first
    db.session.delete(doctor)
    # Then delete user account
    db.session.delete(user)
    db.session.commit()

    # Invalidate cache
    cache.delete("admin_stats")
    cache.delete("all_doctors")

    return jsonify({"message": "Doctor deleted"})


@admin_bp.route("/admin/doctors/<int:doctor_id>/patients", methods=["GET"])
@roles_required("admin")
def admin_doctor_patients(doctor_id):
    """
    List all unique patients assigned to a specific doctor.

    Allows admin to inspect and then edit (via the patient update endpoint)
    any patient who has had at least one appointment with the given doctor.

    Args:
        doctor_id: Doctor record ID to look up patients for.

    Returns:
        JSON array of patient summaries with appointment statistics.
    """
    doctor = Doctor.query.get_or_404(doctor_id)

    # Fetch all appointments for this doctor to build unique patient set
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()

    seen = {}
    for apt in appointments:
        pid = apt.patient_id
        if pid not in seen:
            seen[pid] = {
                "patient": apt.patient,
                "total": 0,
                "completed": 0,
                "booked": 0,
                "last_visit": None,
            }
        seen[pid]["total"] += 1
        if apt.status == "Completed":
            seen[pid]["completed"] += 1
            if seen[pid]["last_visit"] is None or apt.date > seen[pid]["last_visit"]:
                seen[pid]["last_visit"] = apt.date
        elif apt.status == "Booked":
            seen[pid]["booked"] += 1

    result = []
    for pid, info in seen.items():
        patient = info["patient"]
        result.append(
            {
                "patient_id": patient.id,
                "user_id": patient.user_id,
                "name": patient.user.name,
                "email": patient.user.email,
                "phone": patient.user.phone,
                "medical_history": patient.medical_history or "",
                "notification_pref": patient.notification_pref or "email",
                "total_appointments": info["total"],
                "completed_appointments": info["completed"],
                "booked_appointments": info["booked"],
                "last_visit": info["last_visit"],
            }
        )

    result.sort(key=lambda x: x["last_visit"] or "", reverse=True)
    return jsonify(result)


# Patient Management Routes


@admin_bp.route("/admin/patients", methods=["GET"])
@roles_required("admin")
def get_patients():
    """
    Get list of patients with optional search.

    Supports searching by:
    - Patient name
    - Patient ID
    - Contact information (email or phone)

    Query Parameters:
        search: Search string
        page: Page number for pagination (default: 1)
        per_page: Items per page (default: 50)

    Returns:
        JSON with patients list and pagination info
    """
    # Get query parameters
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    # Build base query
    query = Patient.query.join(User)

    # Apply search filter if provided
    if search:
        # Try to parse as ID first
        try:
            patient_id = int(search)
            # Search by ID, name, or contact info
            query = query.filter(
                or_(
                    Patient.id == patient_id,
                    User.name.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.phone.ilike(f"%{search}%"),
                )
            )
        except ValueError:
            # Not a number, search by text fields only
            query = query.filter(
                or_(
                    User.name.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.phone.ilike(f"%{search}%"),
                )
            )

    # Get total count for pagination
    total = query.count()

    # Apply pagination
    patients = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        {
            "patients": [p.to_dict() for p in patients],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }
    )


@admin_bp.route("/admin/patients/<int:id>", methods=["DELETE"])
@roles_required("admin")
def delete_patient(id):
    """
    Delete a patient by ID.

    Also deletes the associated user account.

    Args:
        id: Patient ID to delete

    Returns:
        Success message or 404 if patient not found
    """
    patient = Patient.query.get_or_404(id)
    user = User.query.get(patient.user_id)

    # Delete patient-linked appointment children before parent profile.
    appointments = Appointment.query.filter_by(patient_id=patient.id).all()
    appointment_ids = [appointment.id for appointment in appointments]
    if appointment_ids:
        Payment.query.filter(Payment.appointment_id.in_(appointment_ids)).delete(
            synchronize_session=False
        )
        Treatment.query.filter(Treatment.appointment_id.in_(appointment_ids)).delete(
            synchronize_session=False
        )
        Appointment.query.filter(Appointment.id.in_(appointment_ids)).delete(
            synchronize_session=False
        )

    ExportJob.query.filter_by(patient_id=patient.id).delete(synchronize_session=False)
    Payment.query.filter_by(patient_id=patient.id).delete(synchronize_session=False)

    # Delete patient profile first
    db.session.delete(patient)
    # Then delete user account
    db.session.delete(user)
    db.session.commit()

    # Invalidate cache
    cache.delete("admin_stats")

    return jsonify({"message": "Patient deleted"})


@admin_bp.route("/admin/patients/<int:id>", methods=["PUT"])
@roles_required("admin")
def update_patient(id):
    """Update patient profile and linked user details."""
    patient = Patient.query.get_or_404(id)
    user = User.query.get_or_404(patient.user_id)
    payload = request.get_json(silent=True) or {}
    try:
        data = UpdatePatientRequest(**payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        return problem(
            422,
            "Validation Error",
            "Request validation failed",
            errors=exc.errors(),
        )

    if "name" in data:
        user.name = data.get("name") or user.name
    if "email" in data:
        email = data.get("email") or None
        if email and User.query.filter(User.email == email, User.id != user.id).first():
            return jsonify({"message": "Email already in use"}), 400
        user.email = email
    if "phone" in data:
        user.phone = data.get("phone")
    if data.get("password"):
        user.set_password(data["password"])

    if "medical_history" in data:
        patient.medical_history = data.get("medical_history") or ""
    if "notification_pref" in data:
        patient.notification_pref = data.get("notification_pref") or "email"

    db.session.commit()
    return jsonify(
        {"message": "Patient updated successfully", "patient": patient.to_dict()}
    )


@admin_bp.route("/admin/appointments", methods=["GET"])
@roles_required("admin")
def admin_appointments():
    """Return admin appointment list with multi-filter support.

    Filters (any combination):
    - date (YYYY-MM-DD exact)
    - patient (id or partial name/email/username)
    - doctor (id or partial name/email/username)
    - status (Booked/Completed/Cancelled)
    - payment (paid/unpaid/completed/refunded)
    - type (consultation/follow-up)
    """
    patient_user = aliased(User)
    doctor_user = aliased(User)

    query = (
        Appointment.query.join(Patient, Appointment.patient_id == Patient.id)
        .join(patient_user, Patient.user_id == patient_user.id)
        .join(Doctor, Appointment.doctor_id == Doctor.id)
        .join(doctor_user, Doctor.user_id == doctor_user.id)
    )

    date_filter = (request.args.get("date") or "").strip()
    patient_filter = (request.args.get("patient") or "").strip()
    doctor_filter = (request.args.get("doctor") or "").strip()
    status_filter = (request.args.get("status") or "").strip()
    payment_filter = (request.args.get("payment") or "").strip().lower()
    type_filter = (request.args.get("type") or "").strip().lower()

    if date_filter:
        query = query.filter(Appointment.date == date_filter)

    if patient_filter:
        if patient_filter.isdigit():
            query = query.filter(
                or_(
                    Patient.id == int(patient_filter),
                    patient_user.name.ilike(f"%{patient_filter}%"),
                    patient_user.username.ilike(f"%{patient_filter}%"),
                    patient_user.email.ilike(f"%{patient_filter}%"),
                    patient_user.phone.ilike(f"%{patient_filter}%"),
                )
            )
        else:
            query = query.filter(
                or_(
                    patient_user.name.ilike(f"%{patient_filter}%"),
                    patient_user.username.ilike(f"%{patient_filter}%"),
                    patient_user.email.ilike(f"%{patient_filter}%"),
                    patient_user.phone.ilike(f"%{patient_filter}%"),
                )
            )

    if doctor_filter:
        if doctor_filter.isdigit():
            query = query.filter(
                or_(
                    Doctor.id == int(doctor_filter),
                    doctor_user.name.ilike(f"%{doctor_filter}%"),
                    doctor_user.username.ilike(f"%{doctor_filter}%"),
                    doctor_user.email.ilike(f"%{doctor_filter}%"),
                )
            )
        else:
            query = query.filter(
                or_(
                    doctor_user.name.ilike(f"%{doctor_filter}%"),
                    doctor_user.username.ilike(f"%{doctor_filter}%"),
                    doctor_user.email.ilike(f"%{doctor_filter}%"),
                )
            )

    if status_filter:
        query = query.filter(Appointment.status == status_filter)

    if type_filter in {"follow-up", "follow_up", "followup"}:
        query = query.filter(Appointment.is_follow_up.is_(True))
    elif type_filter in {"consultation", "normal"}:
        query = query.filter(Appointment.is_follow_up.is_(False))

    appointments = query.order_by(
        Appointment.date.desc(), Appointment.time.desc()
    ).all()

    results = []
    for appointment in appointments:
        row = appointment.to_dict()
        if appointment.treatment:
            row["treatment"] = appointment.treatment.to_dict()

        latest_payment = (
            Payment.query.filter_by(appointment_id=appointment.id)
            .order_by(Payment.payment_date.desc(), Payment.id.desc())
            .first()
        )
        row["paid"] = bool(
            Payment.query.filter_by(
                appointment_id=appointment.id, status="completed"
            ).count()
            > Payment.query.filter_by(
                appointment_id=appointment.id, status="refunded"
            ).count()
        )
        row["payment_status"] = latest_payment.status if latest_payment else "unpaid"

        if payment_filter:
            if payment_filter == "paid" and not row["paid"]:
                continue
            if payment_filter == "unpaid" and row["paid"]:
                continue
            if payment_filter in {"completed", "refunded", "failed", "pending"}:
                if row["payment_status"] != payment_filter:
                    continue

        results.append(row)

    return jsonify(results)


# Export Job Monitoring Routes


@admin_bp.route("/admin/audit-logs", methods=["GET"])
@roles_required("admin")
def get_audit_logs():
    """Return recent audit entries for admin forensic and compliance review."""
    action = (request.args.get("action") or "").strip().lower()
    entity_type = (request.args.get("entity_type") or "").strip()
    actor_user_id = request.args.get("actor_user_id", type=int)
    limit = request.args.get("limit", 100, type=int) or 100
    limit = max(1, min(limit, 500))

    query = AuditLog.query
    if action in {"create", "update", "delete"}:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)

    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return jsonify(
        {
            "entries": [row.to_dict() for row in rows],
            "count": len(rows),
            "limit": limit,
        }
    )


@admin_bp.route("/admin/export-jobs", methods=["GET"])
@roles_required("admin")
def get_export_jobs():
    """
    Get list of all export jobs (for admin monitoring).

    Query Parameters:
        status: Filter by status (pending, processing, completed, failed)
        page: Page number
        per_page: Items per page

    Returns:
        JSON with export jobs list
    """
    status_filter = request.args.get("status")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = ExportJob.query.join(Patient).join(User)

    if status_filter:
        query = query.filter(ExportJob.status == status_filter)

    # Order by newest first
    query = query.order_by(ExportJob.created_at.desc())

    total = query.count()
    jobs = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        {
            "jobs": [j.to_dict() for j in jobs],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    )


@admin_bp.route("/admin/export-jobs/<int:id>", methods=["GET"])
@roles_required("admin")
def get_export_job(id):
    """
    Get details of a specific export job.

    Args:
        id: Export job ID

    Returns:
        Export job details or 404 if not found
    """
    job = ExportJob.query.get_or_404(id)
    return jsonify(job.to_dict())


@admin_bp.route("/admin/payments", methods=["GET"])
@roles_required("admin")
def admin_payments():
    """Return payment and refund details for admin auditing.

    Filters (any combination):
    - date: payment date (YYYY-MM-DD)
    - status: pending/completed/failed/refunded
    - patient: partial name/email/username
    - doctor: partial name/email/username
    - method: credit_card/debit_card/insurance
    """
    status_filter = (request.args.get("status") or "").strip()
    doctor_filter = (request.args.get("doctor") or "").strip()
    patient_filter = (request.args.get("patient") or "").strip()
    date_filter = (request.args.get("date") or "").strip()
    method_filter = (request.args.get("method") or "").strip()

    patient_user = aliased(User, name="pat_user")
    doctor_user = aliased(User, name="doc_user")

    query = (
        Payment.query.join(Appointment, Payment.appointment_id == Appointment.id)
        .join(Patient, Payment.patient_id == Patient.id)
        .join(patient_user, Patient.user_id == patient_user.id)
        .join(Doctor, Appointment.doctor_id == Doctor.id)
        .join(doctor_user, Doctor.user_id == doctor_user.id)
    )

    if status_filter:
        query = query.filter(Payment.status == status_filter)
    if method_filter:
        query = query.filter(Payment.payment_method == method_filter)
    if patient_filter:
        query = query.filter(
            or_(
                patient_user.name.ilike(f"%{patient_filter}%"),
                patient_user.username.ilike(f"%{patient_filter}%"),
                patient_user.email.ilike(f"%{patient_filter}%"),
            )
        )
    if doctor_filter:
        query = query.filter(
            or_(
                doctor_user.name.ilike(f"%{doctor_filter}%"),
                doctor_user.username.ilike(f"%{doctor_filter}%"),
            )
        )
    if date_filter:
        query = query.filter(
            Payment.payment_date >= date_filter,
            Payment.payment_date < date_filter + "T23:59:59",
        )

    payments = query.order_by(Payment.payment_date.desc(), Payment.id.desc()).all()

    result = []
    total_collected = 0.0
    total_refunded = 0.0

    for payment in payments:
        row = payment.to_dict()
        if payment.appointment:
            row["appointment_date"] = payment.appointment.date
            row["appointment_time"] = payment.appointment.time
            row["doctor_name"] = payment.appointment.doctor.user.name
            row["doctor_id"] = payment.appointment.doctor_id
        result.append(row)

        if payment.status == "completed":
            total_collected += float(payment.amount)
        elif payment.status == "refunded":
            total_refunded += abs(float(payment.amount))

    return jsonify(
        {
            "payments": result,
            "summary": {
                "total_collected": round(total_collected, 2),
                "total_refunded": round(total_refunded, 2),
                "net": round(total_collected - total_refunded, 2),
            },
        }
    )
