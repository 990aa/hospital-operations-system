"""
Patient Routes Module.

This module contains all routes for patient functionality including:
- Doctor search by name or specialization
- Appointment booking with conflict prevention
- Treatment history viewing
- Async CSV export of treatment history
- Profile management

Author: Abdul Ahad
"""

import os

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_security import login_required, current_user, roles_required
from sqlalchemy import or_, and_
from datetime import datetime

from models.database import (
    db,
    User,
    Doctor,
    Patient,
    Appointment,
    Department,
    ExportJob,
)
from backend.tasks import export_patient_treatments

# Create Blueprint for patient routes
patient_bp = Blueprint("patient", __name__)


# ============================================================
# Doctor Search Routes
# ============================================================


@patient_bp.route("/doctors", methods=["GET"])
def search_doctors():
    """
    Search doctors by department, name, or specialization.

    Query Parameters:
        department_id: Filter by department ID
        search: Search by doctor name (case-insensitive partial match)

    Returns:
        List of doctor dictionaries matching the criteria
    """
    department_id = request.args.get("department_id")
    search = request.args.get("search", "").strip()

    # Build base query with joins for search
    query = Doctor.query.join(User).join(Department)

    # Apply department filter
    if department_id:
        query = query.filter(Doctor.department_id == department_id)

    # Apply name search filter
    if search:
        query = query.filter(
            or_(
                User.name.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                Department.name.ilike(f"%{search}%"),
            )
        )

    doctors = query.all()

    # Try to get from cache for common queries (1 minute cache)
    cache_key = f"doctors_{department_id}_{search}"
    cached = current_app.cache.get(cache_key)
    if cached:
        return jsonify(cached)

    result = [d.to_dict() for d in doctors]

    # Cache for 1 minute (60 seconds)
    current_app.cache.set(cache_key, result, timeout=60)

    return jsonify(result)


@patient_bp.route("/departments", methods=["GET"])
@login_required
def get_departments():
    """
    Get list of all departments.

    Results are cached for 5 minutes as departments rarely change.

    Returns:
        List of department dictionaries
    """
    # Try cache first
    cache_key = "all_departments"
    cached = current_app.cache.get(cache_key)
    if cached:
        return jsonify(cached)

    depts = Department.query.all()
    result = [d.to_dict() for d in depts]

    # Cache for 5 minutes (300 seconds)
    current_app.cache.set(cache_key, result, timeout=300)

    return jsonify(result)


# ============================================================
# Appointment Routes
# ============================================================


@patient_bp.route("/appointments", methods=["POST"])
@roles_required("patient")
def book_appointment():
    """
    Book a new appointment with conflict prevention.

    This endpoint prevents double-booking by checking if the doctor
    already has an appointment at the requested date and time.

    Request Body:
        doctor_id: ID of the doctor to book with
        date: Appointment date (YYYY-MM-DD format)
        time: Appointment time (HH:MM format)

    Returns:
        Success message or error if time slot unavailable
    """
    data = request.json

    # Get current patient's profile
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify({"message": "Patient profile not found"}), 404

    # Validate date is not in the past
    try:
        appointment_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
        if appointment_date < datetime.now().date():
            return jsonify({"message": "Cannot book appointments in the past"}), 400
    except ValueError:
        return jsonify({"message": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Check for booking conflicts
    # Prevent multiple appointments at same date/time for same doctor
    existing = Appointment.query.filter(
        and_(
            Appointment.doctor_id == data["doctor_id"],
            Appointment.date == data["date"],
            Appointment.time == data["time"],
            Appointment.status.in_(["Booked"]),  # Only check booked appointments
        )
    ).first()

    if existing:
        return jsonify(
            {"message": "This time slot is already booked. Please select another time."}
        ), 409  # HTTP 409 Conflict

    # Check if patient already has appointment at same time
    patient_conflict = Appointment.query.filter(
        and_(
            Appointment.patient_id == patient.id,
            Appointment.date == data["date"],
            Appointment.time == data["time"],
            Appointment.status == "Booked",
        )
    ).first()

    if patient_conflict:
        return jsonify(
            {"message": "You already have an appointment at this time."}
        ), 409

    # Create new appointment
    new_app = Appointment(
        patient_id=patient.id,
        doctor_id=data["doctor_id"],
        date=data["date"],
        time=data["time"],
        status="Booked",
    )
    db.session.add(new_app)
    db.session.commit()

    # Invalidate relevant caches
    current_app.cache.delete("admin_stats")
    current_app.cache.delete(f"patient_appointments_{patient.id}_None")
    current_app.cache.delete(f"patient_appointments_{patient.id}_Booked")
    current_app.cache.delete(f"patient_appointments_{patient.id}_Completed")
    current_app.cache.delete(f"patient_appointments_{patient.id}_Cancelled")

    return jsonify(
        {"message": "Appointment booked successfully", "appointment_id": new_app.id}
    ), 201


@patient_bp.route("/my-appointments", methods=["GET"])
@login_required
def my_appointments():
    """
    Get appointments for current user based on role.

    - Patients: See their own appointments with treatment details
    - Doctors: See appointments assigned to them
    - Admins: See all appointments

    Query Parameters:
        status: Filter by status (Booked, Completed, Cancelled)

    Returns:
        List of appointment dictionaries with treatment details if available
    """
    # Get optional status filter
    status_filter = request.args.get("status")

    appointments = []

    if current_user.has_role("patient"):
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        if not patient:
            return jsonify([])

        # Try cache for patient's appointments (30 second cache)
        cache_key = f"patient_appointments_{patient.id}_{status_filter}"
        cached = current_app.cache.get(cache_key)
        if cached:
            return jsonify(cached)

        query = Appointment.query.filter_by(patient_id=patient.id)
        if status_filter:
            query = query.filter_by(status=status_filter)
        appointments = query.order_by(
            Appointment.date.desc(), Appointment.time.desc()
        ).all()

    elif current_user.has_role("doctor"):
        doctor = Doctor.query.filter_by(user_id=current_user.id).first()
        if not doctor:
            return jsonify([])

        query = Appointment.query.filter_by(doctor_id=doctor.id)
        if status_filter:
            query = query.filter_by(status=status_filter)
        appointments = query.order_by(
            Appointment.date.asc(), Appointment.time.asc()
        ).all()

    elif current_user.has_role("admin"):
        query = Appointment.query
        if status_filter:
            query = query.filter_by(status=status_filter)
        appointments = query.order_by(Appointment.date.desc()).all()

    # Build results with treatment details
    results = []
    for app in appointments:
        d = app.to_dict()
        if app.treatment:
            d["treatment"] = app.treatment.to_dict()
        results.append(d)

    # Cache patient results for 30 seconds
    if current_user.has_role("patient"):
        cache_key = f"patient_appointments_{patient.id}_{status_filter}"
        current_app.cache.set(cache_key, results, timeout=30)

    return jsonify(results)


@patient_bp.route("/appointments/<int:id>/cancel", methods=["POST"])
@login_required
def cancel_appointment(id):
    """
    Cancel an appointment.

    Permission check:
    - Patients can cancel their own appointments
    - Doctors can cancel appointments assigned to them
    - Admins can cancel any appointment

    Args:
        id: Appointment ID to cancel

    Returns:
        Success message or error if unauthorized
    """
    appointment = Appointment.query.get_or_404(id)

    # Check permissions
    can_cancel = False

    if current_user.has_role("admin"):
        can_cancel = True
    elif current_user.has_role("doctor"):
        doctor = Doctor.query.filter_by(user_id=current_user.id).first()
        if doctor and appointment.doctor_id == doctor.id:
            can_cancel = True
    elif current_user.has_role("patient"):
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        if patient and appointment.patient_id == patient.id:
            can_cancel = True

    if not can_cancel:
        return jsonify({"message": "Unauthorized to cancel this appointment"}), 403

    # Check if appointment is already completed or cancelled
    if appointment.status in ["Completed", "Cancelled"]:
        return jsonify(
            {"message": f"Cannot cancel appointment with status: {appointment.status}"}
        ), 400

    # Update status
    appointment.status = "Cancelled"
    db.session.commit()

    # Invalidate caches
    current_app.cache.delete("admin_stats")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_None")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Booked")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Completed")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Cancelled")

    return jsonify({"message": "Appointment cancelled successfully"})


@patient_bp.route("/appointments/<int:id>/status", methods=["PUT"])
@login_required
def update_appointment_status(id):
    """
    Update appointment status dynamically.

    Allowed transitions:
    - Booked → Completed (by doctor who owns the appointment)
    - Booked → Cancelled (by patient, doctor, or admin)

    Args:
        id: Appointment ID

    Request Body:
        status: New status ('Completed' or 'Cancelled')

    Returns:
        Updated appointment details
    """
    appointment = Appointment.query.get_or_404(id)
    data = request.json
    new_status = data.get("status")

    # Validate status
    if new_status not in ["Completed", "Cancelled"]:
        return jsonify(
            {"message": "Invalid status. Must be 'Completed' or 'Cancelled'"}
        ), 400

    # Check permissions
    can_update = False

    if current_user.has_role("admin"):
        can_update = True
    elif current_user.has_role("doctor"):
        doctor = Doctor.query.filter_by(user_id=current_user.id).first()
        if doctor and appointment.doctor_id == doctor.id:
            can_update = True
    elif current_user.has_role("patient"):
        # Patients can only cancel
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        if (
            patient
            and appointment.patient_id == patient.id
            and new_status == "Cancelled"
        ):
            can_update = True

    if not can_update:
        return jsonify({"message": "Unauthorized to update this appointment"}), 403

    # Check current status
    if appointment.status == "Completed":
        return jsonify(
            {"message": "Cannot change status of completed appointment"}
        ), 400
    if appointment.status == "Cancelled":
        return jsonify(
            {"message": "Cannot change status of cancelled appointment"}
        ), 400

    # Update status
    appointment.status = new_status
    db.session.commit()

    # Invalidate caches
    current_app.cache.delete("admin_stats")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_None")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Booked")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Completed")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Cancelled")

    return jsonify(
        {
            "message": f"Appointment status updated to {new_status}",
            "appointment": appointment.to_dict(),
        }
    )


# ============================================================
# Export Routes
# ============================================================


@patient_bp.route("/export/treatments", methods=["POST"])
@roles_required("patient")
def trigger_export():
    """
    Trigger async CSV export of patient's treatment history.

    This creates an export job and queues it for processing via Celery.
    The patient will receive an email notification when complete.

    Returns:
        Export job ID and initial status
    """
    # Get current patient
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify({"message": "Patient profile not found"}), 404

    # Check if there's already a pending export for this patient
    existing = ExportJob.query.filter_by(
        patient_id=patient.id, status="pending"
    ).first()

    if existing:
        return jsonify(
            {
                "message": "Export already in progress",
                "job_id": existing.id,
                "status": existing.status,
            }
        ), 200

    # Create export job
    export_job = ExportJob(patient_id=patient.id, status="pending")
    db.session.add(export_job)
    db.session.commit()

    # Queue the export task
    task = export_patient_treatments.delay(patient.id, export_job.id)

    return jsonify(
        {
            "message": "Export job created successfully",
            "job_id": export_job.id,
            "task_id": task.id,
            "status": "pending",
        }
    ), 201


@patient_bp.route("/export/jobs", methods=["GET"])
@roles_required("patient")
def get_export_jobs():
    """
    Get list of export jobs for current patient.

    Returns:
        List of export job dictionaries with status and file info
    """
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify([])

    jobs = (
        ExportJob.query.filter_by(patient_id=patient.id)
        .order_by(ExportJob.created_at.desc())
        .all()
    )

    return jsonify([j.to_dict() for j in jobs])


@patient_bp.route("/export/jobs/<int:job_id>", methods=["GET"])
@roles_required("patient")
def get_export_job(job_id):
    """
    Get details of a specific export job.

    Args:
        job_id: Export job ID

    Returns:
        Export job details or 404 if not found/not owned by patient
    """
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify({"message": "Patient profile not found"}), 404

    job = ExportJob.query.filter_by(id=job_id, patient_id=patient.id).first()
    if not job:
        return jsonify({"message": "Export job not found"}), 404

    return jsonify(job.to_dict())


@patient_bp.route("/export/download/<int:job_id>", methods=["GET"])
@roles_required("patient")
def download_export(job_id):
    """
    Download a completed export file.

    Args:
        job_id: Export job ID

    Returns:
        CSV file download or error if not ready
    """
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify({"message": "Patient profile not found"}), 404

    job = ExportJob.query.filter_by(id=job_id, patient_id=patient.id).first()
    if not job:
        return jsonify({"message": "Export job not found"}), 404

    if job.status != "completed":
        return jsonify(
            {"message": f"Export not ready. Current status: {job.status}"}
        ), 400

    if not job.file_path or not os.path.exists(job.file_path):
        return jsonify({"message": "Export file not found"}), 404

    return send_file(
        job.file_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"treatments_{patient.user.username}.csv",
    )


# ============================================================
# Profile Routes
# ============================================================


@patient_bp.route("/profile", methods=["POST", "GET"])
@login_required
def update_profile():
    """
    Get or update user profile.

    GET: Returns current user profile
    POST: Updates profile fields

    Request Body (POST):
        name: New display name
        email: Email address
        phone: Phone number
        history: Medical history (patients only)
        notification_pref: Notification preference (email, sms, chat, none)

    Returns:
        Updated profile or success message
    """
    user = User.query.get(current_user.id)

    if request.method == "GET":
        profile_data = user.to_dict()
        if user.has_role("patient"):
            patient = Patient.query.filter_by(user_id=user.id).first()
            if patient:
                profile_data["medical_history"] = patient.medical_history
                profile_data["notification_pref"] = patient.notification_pref
        return jsonify(profile_data)

    # POST - Update profile
    data = request.json

    if "name" in data:
        user.name = data["name"]

    if "email" in data:
        # Check if email is already taken
        existing = User.query.filter(
            User.email == data["email"], User.id != user.id
        ).first()
        if existing:
            return jsonify({"message": "Email already in use"}), 400
        user.email = data["email"]

    if "phone" in data:
        user.phone = data["phone"]

    if user.has_role("patient"):
        patient = Patient.query.filter_by(user_id=user.id).first()
        if patient:
            if "history" in data:
                patient.medical_history = data["history"]
            if "notification_pref" in data:
                patient.notification_pref = data["notification_pref"]

    db.session.commit()

    # Invalidate user cache
    current_app.cache.delete(f"user_{user.id}")

    return jsonify({"message": "Profile updated successfully"})
