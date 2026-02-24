"""
Patient Routes Module.

This module contains all routes for patient functionality including:
- Doctor search by name or specialization
- Appointment booking with conflict prevention
- Treatment history viewing
- Async CSV export of treatment history
- Payment processing (dummy portal)
- Profile management

Author: Abdul Ahad
"""

import os
import secrets

from flask import Blueprint, request, jsonify, send_file
from flask_security import login_required, current_user, roles_required
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, date

from backend.extensions import cache
from models.database import (
    db,
    User,
    Doctor,
    Patient,
    Appointment,
    Department,
    ExportJob,
    Payment,
)
from backend.tasks import export_patient_treatments

# Create Blueprint for patient routes
patient_bp = Blueprint("patient", __name__)


# Weekday mappings for deterministic day-name ↔ index conversion.
# Python `date.weekday()` returns Monday=0..Sunday=6, so we mirror that here.
WEEKDAY_TO_INDEX = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}
INDEX_TO_WEEKDAY = {value: key for key, value in WEEKDAY_TO_INDEX.items()}


def _has_active_completed_payment(appointment_id):
    """Return True when appointment has a non-refunded completed payment."""
    completed_count = Payment.query.filter_by(
        appointment_id=appointment_id, status="completed"
    ).count()
    refunded_count = Payment.query.filter_by(
        appointment_id=appointment_id, status="refunded"
    ).count()
    return completed_count > refunded_count


def _latest_payment(appointment_id):
    """Return latest payment record for appointment or None."""
    return (
        Payment.query.filter_by(appointment_id=appointment_id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .first()
    )


def _parse_time_string(time_str, fallback):
    """Parse an HH:MM time string with a safe fallback.

    Args:
        time_str: Candidate time string (possibly invalid or missing).
        fallback: Guaranteed-valid fallback time string in HH:MM format.

    Returns:
        datetime object (date part ignored) representing parsed time.
    """
    value = time_str or fallback
    try:
        return datetime.strptime(value, "%H:%M")
    except ValueError:
        return datetime.strptime(fallback, "%H:%M")


def _doctor_days(doctor):
    """Return normalized availability day set for a doctor."""
    days = (
        doctor.get_availability_days()
        if hasattr(doctor, "get_availability_days")
        else []
    )
    return {day for day in days if day in WEEKDAY_TO_INDEX}


def _available_slots_for_day(doctor, target_date):
    """Return available HH:MM slots for a doctor on a specific date.

    Slot generation rules:
    - If the weekday is outside doctor's allowed days -> no slots.
    - Build slots from `availability_start` to `availability_end`.
    - Use `slot_minutes` granularity (default 30).
    - Remove already-booked slots from the generated list.
    """
    available_days = _doctor_days(doctor)
    if not available_days:
        available_days = {"Mon", "Tue", "Wed", "Thu", "Fri"}

    weekday = INDEX_TO_WEEKDAY[target_date.weekday()]
    if weekday not in available_days:
        return []

    # Parse doctor time window. Fallbacks keep system robust even with legacy rows.
    start = _parse_time_string(getattr(doctor, "availability_start", None), "09:00")
    end = _parse_time_string(getattr(doctor, "availability_end", None), "17:00")
    slot_minutes = int(getattr(doctor, "slot_minutes", 30) or 30)
    if slot_minutes <= 0:
        slot_minutes = 30

    # Generate serial slot times inside [start, end).
    slots = []
    current = start
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=slot_minutes)

    # Collect already-booked times for this doctor and date.
    booked_times = {
        appointment.time
        for appointment in Appointment.query.filter(
            and_(
                Appointment.doctor_id == doctor.id,
                Appointment.date == target_date.strftime("%Y-%m-%d"),
                Appointment.status == "Booked",
            )
        ).all()
    }

    return [slot for slot in slots if slot not in booked_times]


def _doctor_availability_next_7_days(doctor):
    """Build 7-day availability payload for doctor dashboard/booking UI."""
    results = []
    today = date.today()
    for offset in range(7):
        day = today + timedelta(days=offset)
        available_slots = _available_slots_for_day(doctor, day)
        results.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "day": INDEX_TO_WEEKDAY[day.weekday()],
                "available_slots": available_slots,
                "next_available_slot": available_slots[0] if available_slots else None,
                "remaining_slots": len(available_slots),
            }
        )
    return results


def _create_serial_appointment(
    doctor,
    patient_id,
    date_str,
    is_follow_up=False,
    follow_up_source_appointment_id=None,
):
    """Create booked appointment using first available serial slot with retry.

    This helper is shared by patient booking and doctor-scheduled follow-ups.
    It retries slot assignment when a concurrent transaction takes the same slot.

    Returns:
        (Appointment|None, str|None): created appointment and assigned time.
    """
    appointment_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    for _ in range(3):
        available_slots = _available_slots_for_day(doctor, appointment_date)
        if not available_slots:
            return None, None

        assigned_time = None
        for slot in available_slots:
            patient_conflict = Appointment.query.filter(
                and_(
                    Appointment.patient_id == patient_id,
                    Appointment.date == date_str,
                    Appointment.time == slot,
                    Appointment.status == "Booked",
                )
            ).first()
            if not patient_conflict:
                assigned_time = slot
                break

        if not assigned_time:
            return None, None
        new_app = Appointment(
            patient_id=patient_id,
            doctor_id=doctor.id,
            date=date_str,
            time=assigned_time,
            status="Booked",
            is_follow_up=bool(is_follow_up),
            follow_up_source_appointment_id=follow_up_source_appointment_id,
        )
        db.session.add(new_app)
        try:
            db.session.commit()
            return new_app, assigned_time
        except IntegrityError:
            db.session.rollback()

    return None, None


# Doctor Search Routes


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
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    result = []
    for doctor in doctors:
        doctor_data = doctor.to_dict()
        doctor_data["upcoming_availability"] = _doctor_availability_next_7_days(doctor)
        result.append(doctor_data)

    # Cache for 1 minute (60 seconds)
    cache.set(cache_key, result, timeout=60)

    return jsonify(result)


@patient_bp.route("/patient/departments", methods=["GET"])
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
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    depts = Department.query.all()
    result = [d.to_dict() for d in depts]

    # Cache for 5 minutes (300 seconds)
    cache.set(cache_key, result, timeout=300)

    return jsonify(result)


@patient_bp.route("/doctors/<int:doctor_id>/availability", methods=["GET"])
def doctor_availability(doctor_id):
    """Get upcoming 7-day availability for a specific doctor.

    This lightweight endpoint is used for patient-facing doctor profile and
    schedule visibility without requiring appointment creation.
    """
    doctor = Doctor.query.get_or_404(doctor_id)
    return jsonify(
        {
            "doctor_id": doctor.id,
            "doctor_name": doctor.user.name,
            "department": doctor.department.name,
            "availability": _doctor_availability_next_7_days(doctor),
        }
    )


# Appointment Routes


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

    doctor_id = data.get("doctor_id")
    date_str = data.get("date")
    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return jsonify({"message": "Doctor not found"}), 404

    # Validate date is not in the past and within next 7 days.
    # This enforces the product rule that booking window is one week ahead.
    try:
        appointment_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if appointment_date < datetime.now().date():
            return jsonify({"message": "Cannot book appointments in the past"}), 400
        if appointment_date > datetime.now().date() + timedelta(days=6):
            return jsonify(
                {"message": "Appointments can be booked only within next 7 days"}
            ), 400
    except ValueError:
        return jsonify({"message": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Create appointment with retry-safe serial assignment.
    new_app, assigned_time = _create_serial_appointment(
        doctor=doctor,
        patient_id=patient.id,
        date_str=date_str,
    )
    if not new_app:
        return jsonify({"message": "Doctor is not available on this date"}), 409

    # Invalidate relevant caches so stats and appointment lists reflect changes immediately.
    cache.delete("admin_stats")
    cache.delete(f"patient_appointments_{patient.id}_None")
    cache.delete(f"patient_appointments_{patient.id}_Booked")
    cache.delete(f"patient_appointments_{patient.id}_Completed")
    cache.delete(f"patient_appointments_{patient.id}_Cancelled")

    return jsonify(
        {
            "message": "Appointment booked successfully",
            "appointment_id": new_app.id,
            "assigned_time": assigned_time,
            "date": date_str,
        }
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
        cached = cache.get(cache_key)
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
        latest_payment = _latest_payment(app.id)
        d["paid"] = _has_active_completed_payment(app.id)
        d["payment_status"] = latest_payment.status if latest_payment else "unpaid"
        d["payment_amount"] = latest_payment.amount if latest_payment else None
        d["appointment_cost"] = (
            app.doctor.appointment_cost
            if app.doctor and app.doctor.appointment_cost is not None
            else 500.0
        )
        d["payment_date"] = (
            latest_payment.payment_date.isoformat()
            if latest_payment and latest_payment.payment_date
            else None
        )
        d["transaction_id"] = latest_payment.transaction_id if latest_payment else None
        results.append(d)

    # Cache patient results for 30 seconds
    if current_user.has_role("patient"):
        cache_key = f"patient_appointments_{patient.id}_{status_filter}"
        cache.set(cache_key, results, timeout=30)

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

    # Refund policy: if patient cancels a pre-paid appointment, create
    # a refund ledger entry for admin/doctor visibility.
    if current_user.has_role("patient") and _has_active_completed_payment(
        appointment.id
    ):
        latest_completed = (
            Payment.query.filter_by(appointment_id=appointment.id, status="completed")
            .order_by(Payment.payment_date.desc(), Payment.id.desc())
            .first()
        )
        if latest_completed:
            refund = Payment(
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                amount=-abs(latest_completed.amount),
                payment_method=latest_completed.payment_method,
                card_last4=latest_completed.card_last4,
                status="refunded",
                transaction_id=f"RFD-{secrets.token_hex(8).upper()}",
                notes=f"Auto-refund for cancellation. Original transaction: {latest_completed.transaction_id}",
            )
            db.session.add(refund)

    db.session.commit()

    # Invalidate caches
    cache.delete("admin_stats")
    cache.delete(f"patient_appointments_{appointment.patient_id}_None")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Booked")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Completed")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Cancelled")

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
    cache.delete("admin_stats")
    cache.delete(f"patient_appointments_{appointment.patient_id}_None")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Booked")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Completed")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Cancelled")

    return jsonify(
        {
            "message": f"Appointment status updated to {new_status}",
            "appointment": appointment.to_dict(),
        }
    )


# Export Routes


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


# Profile Routes


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

    # Product rule: doctors cannot edit profile fields; only admin can edit doctor data.
    if user.has_role("doctor"):
        return jsonify({"message": "Doctor profile is read-only"}), 403

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
            # Medical history is auto-updated by doctors after each consultation.
            # Patients cannot directly edit their own medical history.
            allowed_prefs = {"email", "sms"}
            if "notification_pref" in data:
                raw_pref = data["notification_pref"] or ""
                # Accept comma-separated string of allowed values only.
                parts = [p.strip().lower() for p in raw_pref.split(",") if p.strip()]
                invalid = [p for p in parts if p not in allowed_prefs]
                if invalid:
                    return jsonify(
                        {
                            "message": f"Invalid notification preference: {invalid}. Use email or sms."
                        }
                    ), 400
                patient.notification_pref = ",".join(parts) if parts else "email"

    db.session.commit()

    # Invalidate user cache
    cache.delete(f"user_{user.id}")

    return jsonify({"message": "Profile updated successfully"})


# Payment Routes (Dummy Portal - No Real Processing)


@patient_bp.route("/patient/payment/appointment/<int:appointment_id>", methods=["POST"])
@roles_required("patient")
def process_payment(appointment_id):
    """
    Process a payment for an appointment (dummy portal - no actual processing).

    This is a demonstration feature that simulates a payment portal
    without actual payment processing. It creates a payment record.

    Request Body:
        amount: Payment amount (float)
        payment_method: 'credit_card', 'debit_card', or 'insurance'
        card_number: Card number (only last 4 digits stored)
        notes: Optional notes

    Returns:
        Payment confirmation with transaction ID
    """
    # Get current patient
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify({"message": "Patient profile not found"}), 404

    # Get appointment
    appointment = Appointment.query.get_or_404(appointment_id)

    # Verify appointment belongs to the patient
    if appointment.patient_id != patient.id:
        return jsonify({"message": "Unauthorized - not your appointment"}), 403

    # Consultation payments must be completed before doctor marks appointment complete.
    if appointment.status != "Booked":
        return jsonify(
            {"message": "Payments are only allowed for booked appointments"}
        ), 400

    # Avoid duplicate active payments for same appointment.
    if _has_active_completed_payment(appointment_id):
        return jsonify({"message": "Appointment already paid"}), 409

    # Get request data
    data = request.json
    if not data:
        return jsonify({"message": "Request body required"}), 400

    # Amount is fixed to the doctor's appointment_cost — patients cannot override it.
    amount = appointment.doctor.appointment_cost or 500.0

    payment_method = data.get("payment_method", "credit_card")
    # Only credit card and debit card are accepted; insurance has been removed.
    if payment_method not in ("credit_card", "debit_card"):
        return jsonify(
            {"message": "Invalid payment method. Use credit_card or debit_card."}
        ), 400

    card_number = data.get("card_number", "")
    notes = data.get("notes", "")

    # Extract last 4 digits of card
    card_last4 = card_number[-4:] if len(card_number) >= 4 else "0000"

    # Generate mock transaction ID
    transaction_id = f"TXN-{secrets.token_hex(8).upper()}"

    # Create payment record
    payment = Payment(
        appointment_id=appointment_id,
        patient_id=patient.id,
        amount=amount,
        payment_method=payment_method,
        card_last4=card_last4,
        status="completed",  # Always successful in dummy portal
        transaction_id=transaction_id,
        notes=notes,
    )

    db.session.add(payment)
    db.session.commit()

    return jsonify(
        {
            "message": "Payment processed successfully",
            "payment": payment.to_dict(),
            "transaction_id": transaction_id,
        }
    ), 201


@patient_bp.route("/patient/payments", methods=["GET"])
@roles_required("patient")
def get_patient_payments():
    """
    Get all payments made by the current patient.

    Returns:
        List of payment dictionaries ordered by date (most recent first)
    """
    # Get current patient
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify({"message": "Patient profile not found"}), 404

    # Get all payments
    payments = (
        Payment.query.filter_by(patient_id=patient.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )

    # Build result with appointment details
    result = []
    for payment in payments:
        payment_dict = payment.to_dict()
        payment_dict["appointment_date"] = (
            payment.appointment.date if payment.appointment.date else None
        )
        payment_dict["doctor_name"] = (
            payment.appointment.doctor.user.name
            if payment.appointment.doctor
            else "Unknown"
        )
        result.append(payment_dict)

    return jsonify(result)


@patient_bp.route(
    "/patient/appointment/<int:appointment_id>/payment-status", methods=["GET"]
)
@roles_required("patient")
def check_payment_status(appointment_id):
    """
    Check if an appointment has been paid for.

    Args:
        appointment_id: Appointment ID

    Returns:
        Payment status and details if paid
    """
    # Get current patient
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    if not patient:
        return jsonify({"message": "Patient profile not found"}), 404

    # Get appointment
    appointment = Appointment.query.get_or_404(appointment_id)

    # Verify appointment belongs to the patient
    if appointment.patient_id != patient.id:
        return jsonify({"message": "Unauthorized - not your appointment"}), 403

    # Find payment for this appointment
    payment = _latest_payment(appointment_id)

    if payment:
        return jsonify(
            {
                "paid": _has_active_completed_payment(appointment_id),
                "payment": payment.to_dict(),
            }
        )
    else:
        return jsonify(
            {"paid": False, "message": "No payment found for this appointment"}
        )
