"""Factory Boy model factories for deterministic test data generation."""

from datetime import date

import factory

from models.database import Appointment, Department, Doctor, Patient, User, db


class BaseSQLAlchemyFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"


class UserFactory(BaseSQLAlchemyFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user_{n}")
    name = factory.Faker("name")
    email = factory.Sequence(lambda n: f"user_{n}@test.local")
    phone = factory.Sequence(lambda n: f"900000{n:04d}")
    password = ""
    active = True
    fs_uniquifier = factory.Sequence(lambda n: f"uniq_{n}")

    @factory.post_generation
    def raw_password(self, create, extracted, **kwargs):
        if not create:
            return
        self.set_password(extracted or "password123")


class DepartmentFactory(BaseSQLAlchemyFactory):
    class Meta:
        model = Department

    name = factory.Sequence(lambda n: f"Department {n}")
    description = factory.Faker("sentence")


class DoctorFactory(BaseSQLAlchemyFactory):
    class Meta:
        model = Doctor

    user = factory.SubFactory(UserFactory)
    department = factory.SubFactory(DepartmentFactory)
    availability = "Mon-Fri 09:00-17:00"
    availability_days = "Mon,Tue,Wed,Thu,Fri"
    availability_start = "09:00"
    availability_end = "17:00"
    slot_minutes = 30
    email_notifications = True
    appointment_cost = 500.0


class PatientFactory(BaseSQLAlchemyFactory):
    class Meta:
        model = Patient

    user = factory.SubFactory(UserFactory)
    medical_history = ""
    notification_pref = "email"


class AppointmentFactory(BaseSQLAlchemyFactory):
    class Meta:
        model = Appointment

    patient = factory.SubFactory(PatientFactory)
    doctor = factory.SubFactory(DoctorFactory)
    date = factory.LazyFunction(lambda: date.today().isoformat())
    time = "09:00"
    status = "Booked"
