from flask import Blueprint, request, jsonify
from flask_security import login_required, current_user, roles_required
from models.database import db, User, Doctor, Patient, Appointment, Department

patient_bp = Blueprint('patient', __name__)

@patient_bp.route('/doctors', methods=['GET'])
def search_doctors():
    department_id = request.args.get('department_id')
    if department_id:
        doctors = Doctor.query.filter_by(department_id=department_id).all()
    else:
        doctors = Doctor.query.all()
    return jsonify([d.to_dict() for d in doctors])

@patient_bp.route('/departments', methods=['GET'])
def get_departments():
    depts = Department.query.all()
    return jsonify([d.to_dict() for d in depts])

@patient_bp.route('/appointments', methods=['POST'])
@roles_required('patient')
def book_appointment():
    data = request.json
    
    patient = Patient.query.filter_by(user_id=current_user.id).first()
    
    # Check for conflict
    existing = Appointment.query.filter_by(
        doctor_id=data['doctor_id'], 
        date=data['date'], 
        time=data['time'],
        status='Booked'
    ).first()
    
    if existing:
        return jsonify({"message": "Doctor is not available at this time"}), 400

    new_app = Appointment(
        patient_id=patient.id,
        doctor_id=data['doctor_id'],
        date=data['date'],
        time=data['time'],
        status='Booked'
    )
    db.session.add(new_app)
    db.session.commit()
    return jsonify({"message": "Appointment booked successfully"})

@patient_bp.route('/my-appointments', methods=['GET'])
@login_required
def my_appointments():
    # Helper logical separation, or keep shared logic?
    # This endpoint was shared by all roles in previous impl.
    # I'll duplicate/adapt logic based on roles here or create a shared 'common' blueprint?
    # Or just handle it here. Since I am splitting files, sharing logic is slightly harder without a service layer.
    # I will adapt: if patient -> show theirs. If doctor -> show theirs (Wait, backend/routes/doctor.py handles doctor appointments).
    # But the frontend calls `/api/my-appointments` for everyone in `loadHistory` / `loadData`.
    # I should probably put this in a shared common route file or just handle roles here.
    
    if current_user.has_role('patient'):
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        appointments = Appointment.query.filter_by(patient_id=patient.id).all()
    elif current_user.has_role('doctor'):
         doctor = Doctor.query.filter_by(user_id=current_user.id).first()
         appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    elif current_user.has_role('admin'):
         appointments = Appointment.query.all()
    else:
        return jsonify([])
        
    results = []
    for app in appointments:
        d = app.to_dict()
        if app.treatment:
            d['treatment'] = app.treatment.to_dict()
        results.append(d)
        
    return jsonify(results)

@patient_bp.route('/appointments/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    # Check permission
    # Patient can cancel own. Doctor can cancel own. Admin can cancel all.
    
    can_cancel = False
    if current_user.has_role('admin'):
        can_cancel = True
    elif current_user.has_role('doctor'):
        doctor = Doctor.query.filter_by(user_id=current_user.id).first()
        if appointment.doctor_id == doctor.id:
            can_cancel = True
    elif current_user.has_role('patient'):
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        if appointment.patient_id == patient.id:
            can_cancel = True
            
    if not can_cancel:
        return jsonify({"message": "Unauthorized"}), 403
    
    appointment.status = 'Cancelled'
    db.session.commit()
    return jsonify({"message": "Appointment cancelled"})

@patient_bp.route('/profile', methods=['POST'])
@login_required
def update_profile():
    data = request.json
    user = User.query.get(current_user.id)
    if 'name' in data:
        user.name = data['name']
    
    if user.has_role('patient'):
        patient = Patient.query.filter_by(user_id=user.id).first()
        if 'history' in data:
            patient.medical_history = data['history']
            
    db.session.commit()
    return jsonify({"message": "Profile updated"})
