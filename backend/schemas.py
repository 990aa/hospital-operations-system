"""Pydantic request schemas and validation decorator for JSON API endpoints."""

from datetime import datetime
from functools import wraps
import re
from typing import Literal

from flask import request
from pydantic import (
    BaseModel,
    EmailStr,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.errors import problem


WEEKDAY_LITERAL = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")


def _reject_script_markup(value: str, field_name: str) -> str:
    if "<" in value or ">" in value:
        raise ValueError(f"{field_name} contains disallowed markup")
    return value


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str | None = None

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise ValueError(
                "Username must be 3-50 chars and use letters, numbers, ., _, or -"
            )
        return value


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    email: EmailStr
    phone: str | None = None

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise ValueError(
                "Username must be 3-50 chars and use letters, numbers, ., _, or -"
            )
        return value

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        return _reject_script_markup(value, "name")

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class BookAppointmentRequest(BaseModel):
    doctor_id: int
    date: str

    @field_validator("date")
    @classmethod
    def valid_iso_date(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%d")
        return value


class CreateDoctorRequest(BaseModel):
    name: str
    username: str
    password: str
    email: EmailStr | None = None
    phone: str | None = None
    department_id: int
    availability_days: list[WEEKDAY_LITERAL] = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    availability_start: str = "09:00"
    availability_end: str = "17:00"
    slot_minutes: int = 30
    bio: str | None = None
    email_notifications: bool = True
    appointment_cost: float = 500.0

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise ValueError(
                "Username must be 3-50 chars and use letters, numbers, ., _, or -"
            )
        return value

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        return _reject_script_markup(value, "name")

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value

    @field_validator("availability_start", "availability_end")
    @classmethod
    def valid_time(cls, value: str) -> str:
        datetime.strptime(value, "%H:%M")
        return value

    @field_validator("slot_minutes")
    @classmethod
    def slot_range(cls, value: int) -> int:
        if value < 10 or value > 60:
            raise ValueError("slot_minutes must be between 10 and 60")
        return value


class UpdateDoctorRequest(BaseModel):
    name: str | None = None
    username: str | None = None
    password: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    department_id: int | None = None
    availability_days: list[WEEKDAY_LITERAL] | None = None
    availability_start: str | None = None
    availability_end: str | None = None
    slot_minutes: int | None = None
    bio: str | None = None
    email_notifications: bool | None = None
    appointment_cost: float | None = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class CreateDepartmentRequest(BaseModel):
    name: str
    description: str | None = None


class UpdatePatientRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    password: str | None = None
    medical_history: str | None = None
    notification_pref: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class UpdateAvailabilityRequest(BaseModel):
    availability_days: list[WEEKDAY_LITERAL] | None = None
    availability_start: str | None = None
    availability_end: str | None = None
    slot_minutes: int | None = None

    @field_validator("slot_minutes")
    @classmethod
    def slot_range(cls, value: int | None) -> int | None:
        if value is not None and (value < 10 or value > 60):
            raise ValueError("slot_minutes must be between 10 and 60")
        return value


class CompleteAppointmentRequest(BaseModel):
    diagnosis: str
    prescription: str
    notes: str | None = None
    next_visit_date: str | None = None

    @field_validator("next_visit_date")
    @classmethod
    def valid_optional_iso_date(cls, value: str | None) -> str | None:
        if value:
            datetime.strptime(value, "%Y-%m-%d")
        return value


class UpdateTreatmentRequest(BaseModel):
    diagnosis: str | None = None
    prescription: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class RescheduleAppointmentRequest(BaseModel):
    new_date: str

    @field_validator("new_date")
    @classmethod
    def valid_iso_date(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%d")
        return value


class UpdateAppointmentStatusRequest(BaseModel):
    status: Literal["Completed", "Cancelled"]


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    history: str | None = None
    notification_pref: Literal["email"] | None = None

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _reject_script_markup(value, "name")

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class ProcessPaymentRequest(BaseModel):
    payment_method: Literal["credit_card", "debit_card"] = "credit_card"
    card_number: str
    notes: str | None = None


def validate(schema_cls):
    """Validate request JSON against a Pydantic schema class."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            payload = request.get_json(silent=True)
            if payload is None:
                return problem(400, "Bad Request", "Request body must be valid JSON")

            try:
                data = schema_cls(**payload)
            except ValidationError as exc:
                return problem(
                    422,
                    "Validation Error",
                    "Request validation failed",
                    errors=exc.errors(),
                )

            return fn(*args, data=data, **kwargs)

        return wrapper

    return decorator
