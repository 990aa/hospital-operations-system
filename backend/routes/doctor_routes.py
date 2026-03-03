"""
Doctor Routes Module.

This module contains all routes for doctor functionality including:
- Viewing assigned appointments
- Completing appointments with treatment records
- Viewing patient full treatment history
- Updating patient medical notes
- Generating PDF reports

All routes require doctor role authentication.

Author: Abdul Ahad
"""

from flask import Blueprint, request, jsonify, send_file
from flask_security import current_user, roles_required
from sqlalchemy import and_
from datetime import datetime, timedelta

from backend.extensions import cache
from models.database import db, Doctor, Patient, Appointment, Treatment, Payment
from backend.pdf_reports import (
    generate_monthly_report_pdf,
    generate_patient_history_pdf,
)
from backend.routes.patient_routes import _create_serial_appointment

# Create Blueprint for doctor routes
doctor_bp = Blueprint("doctor", __name__)

WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _normalize_date_str(value):
    """Return YYYY-MM-DD string for either date-like object or existing string."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _has_active_completed_payment(appointment_id):
    """Return True when appointment has completed payment not offset by refund."""
    completed_count = Payment.query.filter_by(
        appointment_id=appointment_id, status="completed"
    ).count()
    refunded_count = Payment.query.filter_by(
        appointment_id=appointment_id, status="refunded"
    ).count()
    return completed_count > refunded_count


def _normalize_availability_payload(data, doctor):
    """Validate/normalize doctor availability payload from doctor settings."""
    days = data.get("availability_days", doctor.get_availability_days())
    if not isinstance(days, list):
        return None, "availability_days must be a list"

    normalized_days = [day for day in WEEKDAY_ORDER if day in set(days)]
    if not normalized_days:
        return None, "At least one availability day is required"

    availability_start = (
        data.get("availability_start") or doctor.availability_start or "09:00"
    ).strip()
    availability_end = (
        data.get("availability_end") or doctor.availability_end or "17:00"
    ).strip()
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

    slot_minutes = int(data.get("slot_minutes", doctor.slot_minutes or 30) or 30)
    if slot_minutes < 10 or slot_minutes > 60:
        return None, "slot_minutes must be between 10 and 60"

    return {
        "availability_days": normalized_days,
        "availability_start": availability_start,
        "availability_end": availability_end,
        "slot_minutes": slot_minutes,
    }, None


@doctor_bp.route("/doctor/profile", methods=["GET"])
@roles_required("doctor")
def doctor_profile():
    """Return read-only doctor profile details for tabular frontend rendering."""
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    return jsonify(
        {
            "doctor_id": doctor.id,
            "user_id": doctor.user_id,
            "username": doctor.user.username,
            "name": doctor.user.name,
            "email": doctor.user.email,
            "phone": doctor.user.phone,
            "department_id": doctor.department_id,
            "department": doctor.department.name,
            "availability": doctor.availability,
            "availability_days": doctor.get_availability_days(),
            "availability_start": doctor.availability_start,
            "availability_end": doctor.availability_end,
            "slot_minutes": doctor.slot_minutes,
            "bio": doctor.bio or "",
            "email_notifications": bool(doctor.email_notifications),
        }
    )


@doctor_bp.route("/doctor/availability", methods=["PUT"])
@roles_required("doctor")
def update_doctor_availability():
    """Allow doctors to update their upcoming schedule configuration."""
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    data = request.json or {}
    payload, error = _normalize_availability_payload(data, doctor)
    if error:
        return jsonify({"message": error}), 400

    doctor.availability_days = ",".join(payload["availability_days"])
    doctor.availability_start = payload["availability_start"]
    doctor.availability_end = payload["availability_end"]
    doctor.slot_minutes = payload["slot_minutes"]
    doctor.availability = (
        f"{doctor.availability_days} "
        f"{doctor.availability_start}-{doctor.availability_end}"
    )
    db.session.commit()

    cache.delete("all_doctors")
    return jsonify({"message": "Availability updated", "doctor": doctor.to_dict()})


# Appointment Routes


@doctor_bp.route("/doctor/appointments", methods=["GET"])
@roles_required("doctor")
def doctor_appointments():
    """
    Get all appointments assigned to the current doctor.

    Returns appointments ordered by date (upcoming first).
    Results include patient details and any existing treatment records.

    Query Parameters:
        status: Filter by status (Booked, Completed, Cancelled)
        date_from: Filter appointments from this date (YYYY-MM-DD)
        date_to: Filter appointments to this date (YYYY-MM-DD)

    Returns:
        List of appointment dictionaries with patient details
    """
    # Get current doctor
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    # Get query parameters
    status_filter = request.args.get("status")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    # Skip caching for doctor appointments to ensure real-time data
    # after mutations (complete, reschedule, cancel, etc.).

    # Build query
    query = Appointment.query.filter_by(doctor_id=doctor.id)

    if status_filter:
        query = query.filter_by(status=status_filter)

    if date_from:
        query = query.filter(Appointment.date >= date_from)

    if date_to:
        query = query.filter(Appointment.date <= date_to)

    # Order by date and time (upcoming first)
    appointments = query.order_by(Appointment.date.asc(), Appointment.time.asc()).all()

    # Build results with treatment details
    results = []
    for app in appointments:
        d = app.to_dict()
        if app.treatment:
            d["treatment"] = app.treatment.to_dict()
        # Include patient's medical history for context
        d["patient_medical_history"] = app.patient.medical_history
        latest_payment = (
            Payment.query.filter_by(appointment_id=app.id)
            .order_by(Payment.payment_date.desc(), Payment.id.desc())
            .first()
        )
        d["paid"] = _has_active_completed_payment(app.id)
        d["payment_status"] = latest_payment.status if latest_payment else "unpaid"
        d["payment_amount"] = latest_payment.amount if latest_payment else None
        d["payment_transaction_id"] = (
            latest_payment.transaction_id if latest_payment else None
        )
        results.append(d)

    return jsonify(results)


@doctor_bp.route("/appointments/<int:id>/complete", methods=["POST"])
@roles_required("doctor")
def complete_appointment(id):
    """
    Complete an appointment and add treatment record.

    Only the doctor assigned to the appointment can complete it.
    This creates a Treatment record with diagnosis, prescription, and notes.

    Args:
        id: Appointment ID to complete

    Request Body:
        diagnosis: Medical diagnosis
        prescription: Prescribed treatment/medications
        notes: Additional notes (optional)
        next_visit_suggested: Suggested next visit date (optional)

    Returns:
        Success message or error if unauthorized
    """
    data = request.json
    appointment = Appointment.query.get_or_404(id)

    # Check if this appointment belongs to the current doctor
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    if appointment.doctor_id != doctor.id:
        return jsonify({"message": "Unauthorized - not your appointment"}), 403

    # Check if appointment is already completed or cancelled
    if appointment.status == "Completed":
        return jsonify({"message": "Appointment already completed"}), 400

    if appointment.status == "Cancelled":
        return jsonify({"message": "Cannot complete cancelled appointment"}), 400

    if not _has_active_completed_payment(appointment.id):
        return (
            jsonify({"message": "Payment required before consultation completion"}),
            400,
        )

    # Optional doctor-scheduled follow-up date. Uses the same booking policy
    # as patient booking: date format validation + within upcoming 7 days.
    follow_up_date = data.get("next_visit_date")
    follow_up_result = None
    if follow_up_date:
        try:
            follow_up_dt = datetime.strptime(follow_up_date, "%Y-%m-%d").date()
            if follow_up_dt < datetime.now().date():
                return jsonify({"message": "Follow-up date cannot be in the past"}), 400
            if follow_up_dt > datetime.now().date() + timedelta(days=6):
                return (
                    jsonify(
                        {
                            "message": "Follow-up must be scheduled within the next 7 days"
                        }
                    ),
                    400,
                )
        except ValueError:
            return jsonify({"message": "Invalid next_visit_date. Use YYYY-MM-DD"}), 400

    if follow_up_date:
        follow_up_appointment, follow_up_time = _create_serial_appointment(
            doctor=doctor,
            patient_id=appointment.patient_id,
            date_str=follow_up_date,
            is_follow_up=True,
            follow_up_source_appointment_id=appointment.id,
        )
        if not follow_up_appointment:
            return (
                jsonify(
                    {
                        "message": "Could not auto-schedule follow-up appointment for selected date",
                    }
                ),
                409,
            )
        follow_up_result = {
            "appointment_id": follow_up_appointment.id,
            "date": follow_up_date,
            "time": follow_up_time,
        }

    # Update appointment status
    appointment.status = "Completed"

    # Create treatment record
    treatment = Treatment(
        appointment_id=id,
        diagnosis=data["diagnosis"],
        prescription=data["prescription"],
        notes=data.get("notes", ""),
    )
    db.session.add(treatment)

    # Update patient's medical history with summary
    patient = appointment.patient
    if data.get("diagnosis"):
        new_entry = (
            f"\n[{appointment.date}] Dr. {doctor.user.name}: {data['diagnosis']}"
        )
        patient.medical_history = (patient.medical_history or "") + new_entry

    db.session.commit()

    # Invalidate caches
    cache.delete("admin_stats")
    cache.delete(f"doctor_appointments_{doctor.id}")
    # Clear all variations of patient appointment cache
    cache.delete(f"patient_appointments_{appointment.patient_id}_None")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Booked")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Completed")
    cache.delete(f"patient_appointments_{appointment.patient_id}_Cancelled")
    cache.delete(f"patient_history_{appointment.patient_id}")

    return jsonify(
        {
            "message": "Appointment completed and treatment recorded successfully",
            "appointment_id": appointment.id,
            "treatment_id": treatment.id,
            "follow_up": follow_up_result,
        }
    )


@doctor_bp.route("/doctor/appointments/<int:id>/treatment", methods=["PUT"])
@roles_required("doctor")
def update_treatment(id):
    """Update treatment details for a completed appointment."""
    appointment = Appointment.query.get_or_404(id)
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404
    if appointment.doctor_id != doctor.id:
        return jsonify({"message": "Unauthorized - not your appointment"}), 403
    if appointment.status != "Completed":
        return (
            jsonify(
                {"message": "Treatment can be updated only for completed appointments"}
            ),
            400,
        )

    treatment = Treatment.query.filter_by(appointment_id=appointment.id).first()
    if not treatment:
        return jsonify({"message": "Treatment record not found"}), 404

    data = request.json or {}
    if "diagnosis" in data:
        treatment.diagnosis = data["diagnosis"]
    if "prescription" in data:
        treatment.prescription = data["prescription"]
    if "notes" in data:
        treatment.notes = data.get("notes", "")

    db.session.commit()

    cache.delete(f"patient_history_{appointment.patient_id}")
    return jsonify(
        {"message": "Treatment updated successfully", "treatment": treatment.to_dict()}
    )


@doctor_bp.route("/doctor/appointments/<int:id>/reschedule", methods=["POST"])
@roles_required("doctor")
def reschedule_appointment(id):
    """Reschedule an upcoming appointment to a new date.

    Only the doctor assigned to the appointment can reschedule.
    The new date must be within the next 7 days and on a day
    the doctor is available.

    Request Body:
        new_date: Target date in YYYY-MM-DD format

    Returns:
        Success message with new appointment details.
    """
    appointment = Appointment.query.get_or_404(id)
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404
    if appointment.doctor_id != doctor.id:
        return jsonify({"message": "Unauthorized – not your appointment"}), 403
    if appointment.status != "Booked":
        return jsonify({"message": "Only booked appointments can be rescheduled"}), 400

    data = request.json or {}
    new_date_str = data.get("new_date")
    if not new_date_str:
        return jsonify({"message": "new_date is required"}), 400

    try:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"message": "Invalid date format. Use YYYY-MM-DD"}), 400

    today = datetime.now().date()
    if new_date < today:
        return jsonify({"message": "Cannot reschedule to a past date"}), 400
    if new_date > today + timedelta(days=6):
        return jsonify({"message": "Can only reschedule within the next 7 days"}), 400

    # Cancel the old appointment and create a new one at the first available slot
    appointment.status = "Cancelled"
    db.session.flush()

    new_app, assigned_time = _create_serial_appointment(
        doctor=doctor,
        patient_id=appointment.patient_id,
        date_str=new_date_str,
        is_follow_up=appointment.is_follow_up,
        follow_up_source_appointment_id=appointment.follow_up_source_appointment_id,
    )
    if not new_app:
        # Rollback cancellation
        appointment.status = "Booked"
        db.session.commit()
        return jsonify({"message": "No available slots on the selected date"}), 409

    # --- Refund old payment & auto-pay new appointment ---
    # When doctor reschedules, if the old appointment was already paid,
    # refund the old payment and create a new completed payment for the
    # rescheduled appointment so the patient doesn't have to pay again
    # and the doctor's total earnings remain unchanged.
    if _has_active_completed_payment(appointment.id):
        old_payment = (
            Payment.query.filter_by(appointment_id=appointment.id, status="completed")
            .order_by(Payment.payment_date.desc(), Payment.id.desc())
            .first()
        )
        if old_payment:
            import secrets as _secrets

            # Create refund entry for the cancelled appointment
            refund = Payment(
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                amount=-abs(old_payment.amount),
                payment_method=old_payment.payment_method,
                card_last4=old_payment.card_last4,
                status="refunded",
                transaction_id=f"RFD-{_secrets.token_hex(8).upper()}",
                notes=(
                    f"Auto-refund for doctor reschedule. "
                    f"Original transaction: {old_payment.transaction_id}"
                ),
            )
            db.session.add(refund)

            # Create matching completed payment for the new appointment
            new_payment = Payment(
                appointment_id=new_app.id,
                patient_id=appointment.patient_id,
                amount=abs(old_payment.amount),
                payment_method=old_payment.payment_method,
                card_last4=old_payment.card_last4,
                status="completed",
                transaction_id=f"TXN-{_secrets.token_hex(8).upper()}",
                notes=(
                    f"Auto-payment transferred from rescheduled appointment #{appointment.id}. "
                    f"Original transaction: {old_payment.transaction_id}"
                ),
            )
            db.session.add(new_payment)

    db.session.commit()

    # Invalidate caches
    cache.delete("admin_stats")
    cache.delete(f"doctor_appointments_{doctor.id}")
    for suffix in [None, "Booked", "Completed", "Cancelled"]:
        cache.delete(f"patient_appointments_{appointment.patient_id}_{suffix}")

    return jsonify(
        {
            "message": "Appointment rescheduled successfully",
            "old_appointment_id": appointment.id,
            "new_appointment_id": new_app.id,
            "new_date": new_date_str,
            "new_time": assigned_time,
        }
    )


# Patient History Routes


@doctor_bp.route("/doctor/patients/<int:patient_id>/history", methods=["GET"])
@roles_required("doctor")
def get_patient_full_history(patient_id):
    """
    Get full treatment history for a patient.

    This endpoint allows doctors to view complete medical history
    of their patients for informed consultation.

    Args:
        patient_id: Patient ID to get history for

    Query Parameters:
        limit: Maximum number of records to return (default: 50)

    Returns:
        Patient profile and complete appointment/treatment history
    """
    # Get current doctor
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    # Get patient
    patient = Patient.query.get_or_404(patient_id)

    # Security check: Doctor should only see history if they've treated this patient
    # OR if it's their current appointment
    has_treated = Appointment.query.filter(
        and_(Appointment.patient_id == patient_id, Appointment.doctor_id == doctor.id)
    ).first()

    if not has_treated:
        return (
            jsonify(
                {
                    "message": "Unauthorized - no treatment relationship with this patient"
                }
            ),
            403,
        )

    # Try cache
    cache_key = f"patient_history_{patient_id}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    # Get limit
    limit = request.args.get("limit", 50, type=int)

    # Get all completed appointments for this patient
    appointments = (
        Appointment.query.filter(
            and_(
                Appointment.patient_id == patient_id, Appointment.status == "Completed"
            )
        )
        .order_by(Appointment.date.desc(), Appointment.time.desc())
        .limit(limit)
        .all()
    )

    # Build full history
    history = []
    for app in appointments:
        record = {
            "appointment_id": app.id,
            "date": app.date,
            "time": app.time,
            "doctor": app.doctor.to_dict(),
            "treatment": app.treatment.to_dict() if app.treatment else None,
        }
        history.append(record)

    result = {
        "patient": patient.to_dict(),
        "medical_history": patient.medical_history,
        "total_appointments": len(appointments),
        "appointments": history,
    }

    # Cache for 1 minute
    cache.set(cache_key, result, timeout=60)

    return jsonify(result)


@doctor_bp.route("/doctor/patients/<int:patient_id>/summary", methods=["GET"])
@roles_required("doctor")
def get_patient_summary(patient_id):
    """
    Get a quick summary of a patient for the doctor.

    This is a lightweight endpoint for quickly viewing patient info
    before or during a consultation.

    Args:
        patient_id: Patient ID

    Returns:
        Patient summary including basic info and recent visits
    """
    # Get current doctor
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    # Get patient
    patient = Patient.query.get_or_404(patient_id)

    # Check if doctor has treated this patient
    has_treated = Appointment.query.filter(
        and_(Appointment.patient_id == patient_id, Appointment.doctor_id == doctor.id)
    ).first()

    if not has_treated:
        return (
            jsonify(
                {
                    "message": "Unauthorized - no treatment relationship with this patient"
                }
            ),
            403,
        )

    # Get recent appointments (last 5)
    recent_appointments = (
        Appointment.query.filter(Appointment.patient_id == patient_id)
        .order_by(Appointment.date.desc())
        .limit(5)
        .all()
    )

    result = {
        "patient": {
            "id": patient.id,
            "name": patient.user.name,
            "email": patient.user.email,
            "phone": patient.user.phone,
        },
        "medical_history_summary": (
            patient.medical_history[:500] + "..."
            if patient.medical_history and len(patient.medical_history) > 500
            else patient.medical_history
        ),
        "total_visits": Appointment.query.filter_by(
            patient_id=patient_id, status="Completed"
        ).count(),
        "recent_appointments": [
            {
                "id": a.id,
                "date": a.date,
                "time": a.time,
                "status": a.status,
                "doctor_name": a.doctor.user.name,
                "has_treatment": a.treatment is not None,
            }
            for a in recent_appointments
        ],
    }

    return jsonify(result)


# PDF Report Routes


@doctor_bp.route("/doctor/monthly-report/<int:month>/<int:year>", methods=["GET"])
@roles_required("doctor")
def download_monthly_report(month, year):
    """
    Generate and download a PDF monthly activity report for the doctor.

    Args:
        month: Month number (1-12)
        year: Year (e.g., 2025)

    Returns:
        PDF file download
    """
    # Get current doctor
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    # Validate month and year
    if not (1 <= month <= 12) or year < 2000:
        return jsonify({"message": "Invalid month or year"}), 400

    # Query appointments for the specified month
    from datetime import date

    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    appointments = (
        Appointment.query.filter(
            and_(
                Appointment.doctor_id == doctor.id,
                Appointment.date >= start_date_str,
                Appointment.date < end_date_str,
            )
        )
        .order_by(Appointment.date.desc())
        .all()
    )

    # Build appointments data
    appointments_data = []
    for apt in appointments:
        data = {
            "appointment_date": _normalize_date_str(apt.date),
            "patient_name": apt.patient.user.name if apt.patient else "Unknown",
            "status": apt.status,
            "diagnosis": "",
        }
        if apt.treatment:
            data["diagnosis"] = apt.treatment.diagnosis
        appointments_data.append(data)

    # Calculate statistics
    stats = {
        "total_appointments": len(appointments),
        "completed": sum(1 for a in appointments if a.status == "Completed"),
        "cancelled": sum(1 for a in appointments if a.status == "Cancelled"),
        "unique_patients": len(set(a.patient_id for a in appointments)),
    }

    # Generate PDF
    pdf_bytes = generate_monthly_report_pdf(
        doctor_name=doctor.user.name,
        month=month,
        year=year,
        appointments_data=appointments_data,
        stats=stats,
    )

    # Send file
    return send_file(
        pdf_bytes,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"monthly_report_{month}_{year}_{doctor.user.name}.pdf",
    )


@doctor_bp.route("/doctor/patient-history-pdf/<int:patient_id>", methods=["GET"])
@roles_required("doctor")
def download_patient_history_pdf(patient_id):
    """
    Generate and download a PDF patient history report.

    Args:
        patient_id: Patient ID

    Returns:
        PDF file download
    """
    # Get current doctor
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    # Get patient
    patient = Patient.query.get_or_404(patient_id)

    # Check if doctor has treated this patient
    has_treated = Appointment.query.filter(
        and_(Appointment.patient_id == patient_id, Appointment.doctor_id == doctor.id)
    ).first()

    if not has_treated:
        return (
            jsonify(
                {
                    "message": "Unauthorized - no treatment relationship with this patient"
                }
            ),
            403,
        )

    # Get all completed appointments with treatments
    appointments = (
        Appointment.query.filter(
            and_(
                Appointment.patient_id == patient_id, Appointment.status == "Completed"
            )
        )
        .order_by(Appointment.date.desc())
        .all()
    )

    # Build appointments data
    appointments_data = []
    for apt in appointments:
        data = {
            "appointment_date": _normalize_date_str(apt.date),
            "doctor_name": apt.doctor.user.name if apt.doctor else "Unknown",
            "diagnosis": "",
            "treatment_description": "",
        }
        if apt.treatment:
            data["diagnosis"] = apt.treatment.diagnosis
            data["treatment_description"] = apt.treatment.prescription
        appointments_data.append(data)

    # Generate PDF
    pdf_bytes = generate_patient_history_pdf(
        patient_name=patient.user.name,
        patient_id=patient.id,
        appointments_data=appointments_data,
    )

    # Send file
    return send_file(
        pdf_bytes,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"patient_history_{patient.id}_{patient.user.name}.pdf",
    )


@doctor_bp.route("/doctor/patients", methods=["GET"])
@roles_required("doctor")
def list_doctor_patients():
    """
    List all unique patients ever assigned to the current doctor.

    Scans all appointments belonging to this doctor and returns a deduplicated
    list of patients along with appointment statistics. This powers the
    "My Patients" tab on the doctor dashboard so doctors can see who they
    have treated or are treating.

    Returns:
        JSON array of patient summaries sorted by most-recent visit descending.
        Each item includes:
            - patient_id, user_id, name, email, phone
            - medical_history
            - total_appointments, completed_appointments
            - booked_appointments, cancelled_appointments
            - last_visit (YYYY-MM-DD or null)
    """
    # Resolve doctor profile for current user
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    # Fetch all appointments for this doctor in one query to avoid N+1 DB hits
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()

    # Accumulate per-patient stats using a dict keyed by patient_id
    seen = {}
    for apt in appointments:
        pid = apt.patient_id
        if pid not in seen:
            seen[pid] = {
                "patient": apt.patient,
                "total": 0,
                "completed": 0,
                "booked": 0,
                "cancelled": 0,
                "last_visit": None,
            }
        seen[pid]["total"] += 1

        if apt.status == "Completed":
            seen[pid]["completed"] += 1
            # Track the most-recent completed visit date
            if seen[pid]["last_visit"] is None or apt.date > seen[pid]["last_visit"]:
                seen[pid]["last_visit"] = apt.date
        elif apt.status == "Booked":
            seen[pid]["booked"] += 1
        elif apt.status == "Cancelled":
            seen[pid]["cancelled"] += 1

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
                "cancelled_appointments": info["cancelled"],
                "last_visit": info["last_visit"],
            }
        )

    # Sort so most-recently-visited patients appear first
    result.sort(key=lambda x: x["last_visit"] or "", reverse=True)

    return jsonify(result)


@doctor_bp.route("/doctor/payments", methods=["GET"])
@roles_required("doctor")
def doctor_payment_details():
    """Return doctor-facing payment/refund ledger with earnings summary."""
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify({"message": "Doctor profile not found"}), 404

    payments = (
        Payment.query.join(Appointment, Payment.appointment_id == Appointment.id)
        .filter(Appointment.doctor_id == doctor.id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .all()
    )

    items = []
    total_earned = 0.0
    total_refunded = 0.0
    for payment in payments:
        row = payment.to_dict()
        row["appointment_date"] = (
            payment.appointment.date if payment.appointment else None
        )
        row["appointment_time"] = (
            payment.appointment.time if payment.appointment else None
        )
        row["patient_name"] = payment.patient.user.name if payment.patient else None
        items.append(row)

        if payment.status == "completed":
            total_earned += float(payment.amount)
        elif payment.status == "refunded":
            total_refunded += abs(float(payment.amount))

    return jsonify(
        {
            "payments": items,
            "summary": {
                "total_earned": round(total_earned, 2),
                "total_refunded": round(total_refunded, 2),
                "net_earned": round(total_earned - total_refunded, 2),
            },
        }
    )
