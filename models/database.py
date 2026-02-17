from flask_sqlalchemy import SQLAlchemy
from flask_security import UserMixin, RoleMixin

# Initialize the SQLAlchemy instance
db = SQLAlchemy()

# Association table for User-Role relationship
roles_users = db.Table(
    "roles_users",
    db.Column("user_id", db.Integer(), db.ForeignKey("user.id")),
    db.Column("role_id", db.Integer(), db.ForeignKey("role.id")),
)


class Role(db.Model, RoleMixin):
    """
    Role model for user authorization.

    This model defines the different roles available in the system
    (admin, doctor, patient) for role-based access control.

    Attributes:
        id: Primary key for the role
        name: Unique role name (e.g., 'admin', 'doctor', 'patient')
        description: Description of the role's permissions
        users: Many-to-many relationship with User model
    """

    __tablename__ = "role"
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))


class User(db.Model, UserMixin):
    """
    User model for handling authentication and basic user details.

    This model serves as the base for all users in the system (Admin, Doctor, Patient).
    It stores authentication credentials and basic profile information.

    Attributes:
        id: Primary key for the user
        username: Unique username for login
        email: User's email address for notifications
        phone: User's phone number for SMS notifications
        password: Hashed password for authentication
        active: Whether the user account is active
        fs_uniquifier: Unique identifier for Flask-Security
        name: Display name of the user
        roles: Many-to-many relationship with Role
        doctor_profile: One-to-one relationship with Doctor profile
        patient_profile: One-to-one relationship with Patient profile
    """

    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    phone = db.Column(
        db.String(20), nullable=True
    )  # Phone number for SMS notifications
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean())
    fs_uniquifier = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

    # Relationships
    roles = db.relationship(
        "Role", secondary=roles_users, backref=db.backref("users", lazy="dynamic")
    )
    doctor_profile = db.relationship("Doctor", backref="user", uselist=False)
    patient_profile = db.relationship("Patient", backref="user", uselist=False)

    def to_dict(self):
        """Return dictionary representation of the user."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "phone": self.phone,
            "roles": [r.name for r in self.roles],
            "name": self.name,
        }


class Department(db.Model):
    """
    Department/Specialization model.

    This model represents medical departments or specializations in the hospital
    (e.g., Cardiology, Neurology, General Medicine).

    Attributes:
        id: Primary key for the department
        name: Unique department name
        description: Description of the department's focus
        doctors: One-to-many relationship with Doctor model
    """

    __tablename__ = "department"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))

    def to_dict(self):
        """Return dictionary representation of the department."""
        return {"id": self.id, "name": self.name, "description": self.description}


class Doctor(db.Model):
    """
    Doctor details linked to a User.

    This model stores doctor-specific information including their department,
    availability schedule, and contact preferences for notifications.

    Attributes:
        id: Primary key for the doctor
        user_id: Foreign key to User model
        department_id: Foreign key to Department model
        availability: Doctor's working hours (e.g., "Mon-Fri, 9AM-5PM")
        email_notifications: Whether to send email notifications to this doctor
        department: Relationship to Department model
        appointments: One-to-many relationship with Appointment model
    """

    __tablename__ = "doctor"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    department_id = db.Column(
        db.Integer, db.ForeignKey("department.id"), nullable=False
    )
    availability = db.Column(
        db.String(500), default="Mon-Fri, 9AM-5PM"
    )  # Simple string for simplicity
    email_notifications = db.Column(
        db.Boolean, default=True
    )  # Enable/disable monthly reports

    # Relationships
    department = db.relationship("Department", backref="doctors")

    def to_dict(self):
        """Return dictionary representation of the doctor."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username,
            "name": self.user.name,
            "email": self.user.email,
            "phone": self.user.phone,
            "department": self.department.name,
            "availability": self.availability,
            "email_notifications": self.email_notifications,
        }


class Patient(db.Model):
    """
    Patient details linked to a User.

    This model stores additional information specific to patients including
    their medical history and notification preferences.

    Attributes:
        id: Primary key for the patient
        user_id: Foreign key to User model
        medical_history: Text field for patient's medical history
        notification_pref: Preferred notification method ('email', 'sms', 'chat', 'none')
        user: Relationship to User model for accessing user details
        appointments: One-to-many relationship with Appointment model
    """

    __tablename__ = "patient"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    medical_history = db.Column(db.Text, default="")
    # Notification preference: 'email', 'sms', 'chat', 'none'
    notification_pref = db.Column(db.String(20), default="email")

    def to_dict(self):
        """Return dictionary representation of the patient."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username,
            "name": self.user.name,
            "email": self.user.email,
            "phone": self.user.phone,
            "medical_history": self.medical_history,
            "notification_pref": self.notification_pref,
        }


class Appointment(db.Model):
    """
    Appointment model linking Patient and Doctor.

    This model represents a scheduled appointment between a patient and a doctor.
    It tracks the appointment date, time, and status (Booked, Completed, Cancelled).

    Attributes:
        id: Primary key for the appointment
        patient_id: Foreign key to Patient model
        doctor_id: Foreign key to Doctor model
        date: Appointment date in YYYY-MM-DD format
        time: Appointment time in HH:MM format
        status: Current status ('Booked', 'Completed', 'Cancelled')
        patient: Relationship to Patient model
        doctor: Relationship to Doctor model
        treatment: One-to-one relationship with Treatment model
    """

    __tablename__ = "appointment"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctor.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)  # YYYY-MM-DD
    time = db.Column(db.String(10), nullable=False)  # HH:MM
    status = db.Column(db.String(20), default="Booked")  # Booked, Completed, Cancelled

    # Relationships
    patient = db.relationship("Patient", backref="appointments")
    doctor = db.relationship("Doctor", backref="appointments")
    treatment = db.relationship("Treatment", backref="appointment", uselist=False)

    def to_dict(self):
        """Return dictionary representation of the appointment."""
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.user.name,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.user.name,
            "department": self.doctor.department.name,
            "date": self.date,
            "time": self.time,
            "status": self.status,
        }


class Treatment(db.Model):
    """
    Treatment record for a completed appointment.

    This model stores the medical details of a completed appointment including
    diagnosis, prescriptions, and doctor's notes.

    Attributes:
        id: Primary key for the treatment record
        appointment_id: Foreign key to Appointment model
        diagnosis: Medical diagnosis text
        prescription: Prescribed medications/treatments
        notes: Additional notes from the doctor
        appointment: Relationship to Appointment model
    """

    __tablename__ = "treatment"
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(
        db.Integer, db.ForeignKey("appointment.id"), nullable=False
    )
    diagnosis = db.Column(db.Text, nullable=False)
    prescription = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)

    def to_dict(self):
        """Return dictionary representation of the treatment."""
        return {
            "id": self.id,
            "appointment_id": self.appointment_id,
            "diagnosis": self.diagnosis,
            "prescription": self.prescription,
            "notes": self.notes,
        }


class ExportJob(db.Model):
    """
    Model for tracking async CSV export jobs.

    This model stores information about patient treatment export jobs
    that are processed asynchronously via Celery.

    Attributes:
        id: Primary key for the export job
        patient_id: Foreign key to Patient model who requested the export
        status: Current status ('pending', 'processing', 'completed', 'failed')
        file_path: Path to the generated CSV file
        created_at: Timestamp when the job was created
        completed_at: Timestamp when the job completed
        error_message: Error message if the job failed
    """

    __tablename__ = "export_job"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    status = db.Column(
        db.String(20), default="pending"
    )  # pending, processing, completed, failed
    file_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    # Relationship
    patient = db.relationship("Patient", backref="export_jobs")

    def to_dict(self):
        """Return dictionary representation of the export job."""
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.user.name,
            "status": self.status,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error_message": self.error_message,
        }


class Payment(db.Model):
    """
    Model for tracking patient payments (dummy portal - no actual processing).

    This model stores payment records for appointments, demonstrating
    a payment portal feature without actual payment processing.

    Attributes:
        id: Primary key for the payment
        appointment_id: Foreign key to Appointment model
        patient_id: Foreign key to Patient model
        amount: Payment amount in dollars
        payment_method: Payment method ('credit_card', 'debit_card', 'insurance')
        card_last4: Last 4 digits of card number (for display)
        status: Payment status ('pending', 'completed', 'failed', 'refunded')
        transaction_id: Mock transaction ID (randomly generated)
        payment_date: Timestamp when payment was made
        notes: Additional notes about the payment
    """

    __tablename__ = "payment"
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(
        db.Integer, db.ForeignKey("appointment.id"), nullable=False
    )
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(
        db.String(20), default="credit_card"
    )  # credit_card, debit_card, insurance
    card_last4 = db.Column(db.String(4), nullable=True)  # Last 4 digits for display
    status = db.Column(
        db.String(20), default="completed"
    )  # pending, completed, failed, refunded
    transaction_id = db.Column(db.String(50), unique=True, nullable=False)
    payment_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    notes = db.Column(db.Text, nullable=True)

    # Relationships
    appointment = db.relationship("Appointment", backref="payments")
    patient = db.relationship("Patient", backref="payments")

    def to_dict(self):
        """Return dictionary representation of the payment."""
        return {
            "id": self.id,
            "appointment_id": self.appointment_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.user.name,
            "amount": self.amount,
            "payment_method": self.payment_method,
            "card_last4": self.card_last4,
            "status": self.status,
            "transaction_id": self.transaction_id,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "notes": self.notes,
        }
