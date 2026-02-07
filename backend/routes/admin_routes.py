from flask import Blueprint, request, jsonify, current_app
from flask_security import login_required, current_user, roles_required
from flask_security.utils import hash_password
from models.database import db, User, Doctor, Patient, Appointment, Department

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/stats', methods=['GET'])
@roles_required('admin')
def admin_stats():
    return jsonify({
        "total_doctors": Doctor.query.count(),
        "total_patients": Patient.query.count(),
        "total_appointments": Appointment.query.count()
    })

@admin_bp.route('/admin/doctors', methods=['GET', 'POST'])
@roles_required('admin')
def manage_doctors():
    if request.method == 'POST':
        data = request.json
        user_datastore = current_app.extensions['security'].datastore
        
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"message": "Username already exists"}), 400
        
        new_user = user_datastore.create_user(
            username=data['username'],
            password=hash_password(data['password']),
            name=data['name'],
            active=True
        )
        user_datastore.add_role_to_user(new_user, 'doctor')
        db.session.commit() # Commit user first to get ID

        # Create Doctor Profile
        new_doctor = Doctor(
            user_id=new_user.id,
            department_id=data['department_id'],
            availability=data.get('availability', 'Mon-Fri 9AM-5PM')
        )
        db.session.add(new_doctor)
        db.session.commit()
        return jsonify({"message": "Doctor added successfully"})

    # GET
    doctors = Doctor.query.all()
    return jsonify([d.to_dict() for d in doctors])

@admin_bp.route('/admin/doctors/<int:id>', methods=['DELETE'])
@roles_required('admin')
def delete_doctor(id):
    doctor = Doctor.query.get_or_404(id)
    user = User.query.get(doctor.user_id)
    
    # Simple delete (cascade handling manually or via ORM)
    db.session.delete(doctor)
    # Also remove user? Yes.
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Doctor deleted"})

@admin_bp.route('/admin/patients', methods=['GET'])
@roles_required('admin')
def get_patients():
    patients = Patient.query.all()
    return jsonify([p.to_dict() for p in patients])

@admin_bp.route('/admin/patients/<int:id>', methods=['DELETE'])
@roles_required('admin')
def delete_patient(id):
    patient = Patient.query.get_or_404(id)
    user = User.query.get(patient.user_id)
    
    db.session.delete(patient)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Patient deleted"})
