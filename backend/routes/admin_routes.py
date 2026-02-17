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
from flask_security import roles_required
from flask_security.utils import hash_password
from sqlalchemy import or_
from models.database import db, User, Doctor, Patient, Appointment, ExportJob

# Create Blueprint for admin routes
admin_bp = Blueprint("admin", __name__)


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
    cached = current_app.cache.get(cache_key)
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
    current_app.cache.set(cache_key, stats, timeout=300)

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
        data = request.json
        user_datastore = current_app.extensions["security"].datastore

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
            password=hash_password(data["password"]),
            name=data["name"],
            active=True,
        )
        user_datastore.add_role_to_user(new_user, "doctor")
        db.session.commit()  # Commit to get user ID

        # Create Doctor Profile
        new_doctor = Doctor(
            user_id=new_user.id,
            department_id=data["department_id"],
            availability=data.get("availability", "Mon-Fri 9AM-5PM"),
            email_notifications=data.get("email_notifications", True),
        )
        db.session.add(new_doctor)
        db.session.commit()

        # Invalidate cache after adding doctor
        current_app.cache.delete("admin_stats")
        current_app.cache.delete("all_doctors")

        return jsonify({"message": "Doctor added successfully"}), 201

    # GET - with optional search
    search = request.args.get("search", "").strip()

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

    doctors = query.all()
    return jsonify([d.to_dict() for d in doctors])


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

    # Delete doctor profile first
    db.session.delete(doctor)
    # Then delete user account
    db.session.delete(user)
    db.session.commit()

    # Invalidate cache
    current_app.cache.delete("admin_stats")
    current_app.cache.delete("all_doctors")

    return jsonify({"message": "Doctor deleted"})


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

    # Delete patient profile first
    db.session.delete(patient)
    # Then delete user account
    db.session.delete(user)
    db.session.commit()

    # Invalidate cache
    current_app.cache.delete("admin_stats")

    return jsonify({"message": "Patient deleted"})


# Export Job Monitoring Routes


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
