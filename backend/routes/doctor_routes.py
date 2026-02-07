from flask import Blueprint, request, jsonify
from flask_security import login_required, current_user, roles_required
from models.database import db, Doctor, Appointment, Treatment

doctor_bp = Blueprint('doctor', __name__)

@doctor_bp.route('/doctor/appointments', methods=['GET'])
@roles_required('doctor')
def doctor_appointments():
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if not doctor:
        return jsonify([])
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    return jsonify([a.to_dict() for a in appointments])

@doctor_bp.route('/appointments/<int:id>/complete', methods=['POST'])
@roles_required('doctor')
def complete_appointment(id):
    data = request.json
    appointment = Appointment.query.get_or_404(id)
    
    # Check if this appointment belongs to the current doctor
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    if appointment.doctor_id != doctor.id:
        return jsonify({"message": "Unauthorized"}), 403

    appointment.status = 'Completed'
    
    treatment = Treatment(
        appointment_id=id,
        diagnosis=data['diagnosis'],
        prescription=data['prescription'],
        notes=data.get('notes', '')
    )
    db.session.add(treatment)
    db.session.commit()
    return jsonify({"message": "Appointment completed and treatment recorded"})
