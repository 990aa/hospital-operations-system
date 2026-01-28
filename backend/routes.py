from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models.database import db, User, Doctor, Patient, Department, Appointment, Treatment

api = Blueprint('api', __name__)

# --- Authentication ---

@api.route('/login', methods=['POST'])
def login():
    """Log in a user (Admin, Doctor, or Patient)."""
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    
    if user and user.password == password: # In real app use check_password_hash
        login_user(user)
        return jsonify({"message": "Login successful", "role": user.role, "user": user.to_dict()})
    
    return jsonify({"message": "Invalid credentials"}), 401

@api.route('/logout', methods=['POST'])
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    return jsonify({"message": "Logged out"})

@api.route('/register', methods=['POST'])
def register():
    """Register a new patient."""
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"message": "Username already exists"}), 400
    
    # Create User
    new_user = User(
        username=data['username'],
        password=data['password'], # In real app use generate_password_hash
        role='patient',
        name=data['name']
    )
    db.session.add(new_user)
    db.session.commit()

    # Create Patient Profile
    new_patient = Patient(user_id=new_user.id)
    db.session.add(new_patient)
    db.session.commit()

    return jsonify({"message": "Registration successful"})

@api.route('/current-user', methods=['GET'])
def get_current_user():
    if current_user.is_authenticated:
        return jsonify(current_user.to_dict())
    return jsonify(None), 401

# --- Admin Routes ---

@api.route('/admin/stats', methods=['GET'])
@login_required
def admin_stats():
    if current_user.role != 'admin':
        return jsonify({"message": "Unauthorized"}), 403
    
    return jsonify({
        "total_doctors": Doctor.query.count(),
        "total_patients": Patient.query.count(),
        "total_appointments": Appointment.query.count()
    })

@api.route('/departments', methods=['GET'])
def get_departments():
    depts = Department.query.all()
    return jsonify([d.to_dict() for d in depts])

@api.route('/admin/doctors', methods=['GET', 'POST'])
@login_required
def manage_doctors():
    if current_user.role != 'admin':
        return jsonify({"message": "Unauthorized"}), 403

    if request.method == 'POST':
        data = request.json
        # Create User for Doctor
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"message": "Username already exists"}), 400
        
        new_user = User(
            username=data['username'],
            password=data['password'],
            role='doctor',
            name=data['name']
        )
        db.session.add(new_user)
        db.session.commit()

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

@api.route('/admin/doctors/<int:id>', methods=['DELETE'])
@login_required
def delete_doctor(id):
    if current_user.role != 'admin':
        return jsonify({"message": "Unauthorized"}), 403
    
    doctor = Doctor.query.get_or_404(id)
    user = User.query.get(doctor.user_id)
    
    # Delete related appointments first if strict on cascade, or let DB handle it.
    # For simplicity, we just delete doctor and user. 
    # NOTE: In production, handle cascading properly.
    
    db.session.delete(doctor)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Doctor deleted"})

@api.route('/admin/patients', methods=['GET'])
@login_required
def get_patients():
    if current_user.role != 'admin':
        return jsonify({"message": "Unauthorized"}), 403
    patients = Patient.query.all()
    return jsonify([p.to_dict() for p in patients])

@api.route('/admin/patients/<int:id>', methods=['DELETE'])
@login_required
def delete_patient(id):
    if current_user.role != 'admin':
        return jsonify({"message": "Unauthorized"}), 403
    
    patient = Patient.query.get_or_404(id)
    user = User.query.get(patient.user_id)
    
    db.session.delete(patient)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Patient deleted"})

@api.route('/profile', methods=['POST'])
@login_required
def update_profile():
    data = request.json
    user = User.query.get(current_user.id)
    if 'name' in data:
        user.name = data['name']
    
    if user.role == 'patient':
        patient = Patient.query.filter_by(user_id=user.id).first()
        if 'history' in data:
            patient.medical_history = data['history']
            
    db.session.commit()
    return jsonify({"message": "Profile updated"})

# --- Doctor Routes ---

@api.route('/doctor/appointments', methods=['GET'])
@login_required
def doctor_appointments():
    if current_user.role != 'doctor':
        return jsonify({"message": "Unauthorized"}), 403
    
    doctor = Doctor.query.filter_by(user_id=current_user.id).first()
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    return jsonify([a.to_dict() for a in appointments])

@api.route('/appointments/<int:id>/complete', methods=['POST'])
@login_required
def complete_appointment(id):
    if current_user.role != 'doctor':
        return jsonify({"message": "Unauthorized"}), 403

    data = request.json
    appointment = Appointment.query.get_or_404(id)
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

# --- Patient Routes ---

@api.route('/doctors', methods=['GET'])
def search_doctors():
    department_id = request.args.get('department_id')
    if department_id:
        doctors = Doctor.query.filter_by(department_id=department_id).all()
    else:
        doctors = Doctor.query.all()
    return jsonify([d.to_dict() for d in doctors])

@api.route('/appointments', methods=['POST'])
@login_required
def book_appointment():
    if current_user.role != 'patient':
        return jsonify({"message": "Unauthorized"}), 403
    
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

@api.route('/my-appointments', methods=['GET'])
@login_required
def my_appointments():
    if current_user.role == 'patient':
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        appointments = Appointment.query.filter_by(patient_id=patient.id).all()
    elif current_user.role == 'doctor':
         doctor = Doctor.query.filter_by(user_id=current_user.id).first()
         appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    elif current_user.role == 'admin':
         appointments = Appointment.query.all()
    else:
        return jsonify([])
        
    # Enrich with treatment info if completed
    results = []
    for app in appointments:
        d = app.to_dict()
        if app.treatment:
            d['treatment'] = app.treatment.to_dict()
        results.append(d)
        
    return jsonify(results)

@api.route('/appointments/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    # Allow patient or doctor or admin to cancel?
    # Requirement: "Patient... Can book, reschedule, or cancel"
    # Requirement: "Doctor... mark as completed or cancelled"
    
    appointment.status = 'Cancelled'
    db.session.commit()
    return jsonify({"message": "Appointment cancelled"})
