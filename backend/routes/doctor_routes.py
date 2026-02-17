"""
Doctor Routes Module.

This module contains all routes for doctor functionality including:
- Viewing assigned appointments
- Completing appointments with treatment records
- Viewing patient full treatment history
- Updating patient medical notes

All routes require doctor role authentication.

Author: Abdul Ahad
"""

from flask import Blueprint, request, jsonify, current_app
from flask_security import current_user, roles_required
from sqlalchemy import and_

from models.database import db, Doctor, Patient, Appointment, Treatment

# Create Blueprint for doctor routes
doctor_bp = Blueprint("doctor", __name__)


# ============================================================
# Appointment Routes
# ============================================================


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

    # Try cache for common queries
    cache_key = f"doctor_appointments_{doctor.id}_{status_filter}_{date_from}_{date_to}"
    cached = current_app.cache.get(cache_key)
    if cached:
        return jsonify(cached)

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
        results.append(d)

    # Cache for 30 seconds
    current_app.cache.set(cache_key, results, timeout=30)

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
    current_app.cache.delete("admin_stats")
    current_app.cache.delete(f"doctor_appointments_{doctor.id}")
    # Clear all variations of patient appointment cache
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_None")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Booked")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Completed")
    current_app.cache.delete(f"patient_appointments_{appointment.patient_id}_Cancelled")
    current_app.cache.delete(f"patient_history_{appointment.patient_id}")

    return jsonify(
        {
            "message": "Appointment completed and treatment recorded successfully",
            "appointment_id": appointment.id,
            "treatment_id": treatment.id,
        }
    )


# ============================================================
# Patient History Routes
# ============================================================


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
        return jsonify(
            {"message": "Unauthorized - no treatment relationship with this patient"}
        ), 403

    # Try cache
    cache_key = f"patient_history_{patient_id}"
    cached = current_app.cache.get(cache_key)
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
    current_app.cache.set(cache_key, result, timeout=60)

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
        return jsonify(
            {"message": "Unauthorized - no treatment relationship with this patient"}
        ), 403

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
        "medical_history_summary": patient.medical_history[:500] + "..."
        if patient.medical_history and len(patient.medical_history) > 500
        else patient.medical_history,
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
