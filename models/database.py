from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

# Initialize the SQLAlchemy instance
db = SQLAlchemy()

class User(UserMixin, db.Model):
    """
    User model for handling authentication and basic user details.
    Roles: 'admin', 'doctor', 'patient'
    """
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # In a real app, hash this!
    role = db.Column(db.String(20), nullable=False) # 'admin', 'doctor', 'patient'
    name = db.Column(db.String(100), nullable=False)
    
    # Relationships
    doctor_profile = db.relationship('Doctor', backref='user', uselist=False)
    patient_profile = db.relationship('Patient', backref='user', uselist=False)

    def to_dict(self):
        """Return dictionary representation of the user."""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "name": self.name
        }

class Department(db.Model):
    """
    Department/Specialization model.
    """
    __tablename__ = 'department'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description
        }

class Doctor(db.Model):
    """
    Doctor details linked to a User.
    """
    __tablename__ = 'doctor'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    availability = db.Column(db.String(500), default="Mon-Fri, 9AM-5PM") # Simple string for simplicity

    # Relationships
    department = db.relationship('Department', backref='doctors')
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.user.name,
            "department": self.department.name,
            "availability": self.availability
        }

class Patient(db.Model):
    """
    Patient details linked to a User.
    """
    __tablename__ = 'patient'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    medical_history = db.Column(db.Text, default="")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.user.name,
            "medical_history": self.medical_history
        }

class Appointment(db.Model):
    """
    Appointment model linking Patient and Doctor.
    """
    __tablename__ = 'appointment'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False) # YYYY-MM-DD
    time = db.Column(db.String(10), nullable=False) # HH:MM
    status = db.Column(db.String(20), default="Booked") # Booked, Completed, Cancelled

    # Relationships
    patient = db.relationship('Patient', backref='appointments')
    doctor = db.relationship('Doctor', backref='appointments')
    treatment = db.relationship('Treatment', backref='appointment', uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.user.name,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.user.name,
            "department": self.doctor.department.name,
            "date": self.date,
            "time": self.time,
            "status": self.status
        }

class Treatment(db.Model):
    """
    Treatment record for a completed appointment.
    """
    __tablename__ = 'treatment'
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    diagnosis = db.Column(db.Text, nullable=False)
    prescription = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "appointment_id": self.appointment_id,
            "diagnosis": self.diagnosis,
            "prescription": self.prescription,
            "notes": self.notes
        }
