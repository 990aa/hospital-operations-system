"""
Backend Validation Module.

This module provides decorators and utility functions for validating
API request data before processing. Ensures data integrity and provides
clear error messages for invalid inputs.

Author: Abdul Ahad
"""

from functools import wraps
from flask import request, jsonify
import re
from datetime import datetime


def validate_required_fields(*required_fields):
    """
    Decorator to validate that required fields are present in request JSON.

    Usage:
        @validate_required_fields('username', 'password', 'email')
        def my_route():
            # All required fields are guaranteed to be present
            pass

    Args:
        *required_fields: Field names that must be present in request.json

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.json
            if not data:
                return jsonify({"message": "Request body is required"}), 400

            missing = [
                field
                for field in required_fields
                if field not in data or not data[field]
            ]
            if missing:
                return jsonify(
                    {"message": "Missing required fields", "missing_fields": missing}
                ), 400

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_email(func):
    """
    Decorator to validate email format if 'email' field is present in request.

    Usage:
        @validate_email
        def register_route():
            # Email format is validated if present
            pass
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        data = request.json
        if data and "email" in data and data["email"]:
            email = data["email"]
            # Basic email regex pattern
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, email):
                return jsonify({"message": "Invalid email format"}), 400
        return func(*args, **kwargs)

    return wrapper


def validate_phone(func):
    """
    Decorator to validate phone format if 'phone' field is present in request.

    Accepts formats: (123) 456-7890, 123-456-7890, 1234567890, +1234567890

    Usage:
        @validate_phone
        def update_profile():
            # Phone format is validated if present
            pass
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        data = request.json
        if data and "phone" in data and data["phone"]:
            phone = data["phone"]
            # Phone pattern: allows optional +, (), -, spaces, and 10-15 digits
            phone_pattern = r"^\+?[\d\s\-()]{10,15}$"
            if not re.match(phone_pattern, phone):
                return jsonify({"message": "Invalid phone format"}), 400
        return func(*args, **kwargs)

    return wrapper


def validate_date_format(field_name="date"):
    """
    Decorator to validate date format (YYYY-MM-DD) for a specific field.

    Usage:
        @validate_date_format('appointment_date')
        def book_appointment():
            # Date field is validated
            pass

    Args:
        field_name: Name of the date field to validate
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.json
            if data and field_name in data and data[field_name]:
                date_str = data[field_name]
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    return jsonify(
                        {
                            "message": f"Invalid date format for {field_name}",
                            "expected_format": "YYYY-MM-DD",
                            "received": date_str,
                        }
                    ), 400
            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_time_format(field_name="time"):
    """
    Decorator to validate time format (HH:MM) for a specific field.

    Usage:
        @validate_time_format('appointment_time')
        def book_appointment():
            # Time field is validated
            pass

    Args:
        field_name: Name of the time field to validate
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.json
            if data and field_name in data and data[field_name]:
                time_str = data[field_name]
                try:
                    datetime.strptime(time_str, "%H:%M")
                except ValueError:
                    return jsonify(
                        {
                            "message": f"Invalid time format for {field_name}",
                            "expected_format": "HH:MM (24-hour)",
                            "received": time_str,
                        }
                    ), 400
            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_password_strength(func):
    """
    Decorator to validate password strength.

    Requirements:
        - Minimum 6 characters
        - At least one letter or number

    Usage:
        @validate_password_strength
        def register():
            # Password strength is validated
            pass
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        data = request.json
        if data and "password" in data:
            password = data["password"]
            if len(password) < 6:
                return jsonify(
                    {"message": "Password must be at least 6 characters long"}
                ), 400
            if not re.search(r"[a-zA-Z0-9]", password):
                return jsonify(
                    {"message": "Password must contain at least one letter or number"}
                ), 400
        return func(*args, **kwargs)

    return wrapper


def validate_numeric_range(field_name, min_value=None, max_value=None):
    """
    Decorator to validate that a numeric field is within a specified range.

    Usage:
        @validate_numeric_range('age', min_value=0, max_value=120)
        def update_profile():
            # Age is validated to be between 0 and 120
            pass

    Args:
        field_name: Name of the numeric field to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.json
            if data and field_name in data:
                try:
                    value = float(data[field_name])
                except (ValueError, TypeError):
                    return jsonify(
                        {"message": f"Field '{field_name}' must be a number"}
                    ), 400

                if min_value is not None and value < min_value:
                    return jsonify(
                        {
                            "message": f"Field '{field_name}' must be at least {min_value}"
                        }
                    ), 400

                if max_value is not None and value > max_value:
                    return jsonify(
                        {"message": f"Field '{field_name}' must be at most {max_value}"}
                    ), 400

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_string_length(field_name, min_length=None, max_length=None):
    """
    Decorator to validate string field length.

    Usage:
        @validate_string_length('username', min_length=3, max_length=50)
        def register():
            # Username length is validated
            pass

    Args:
        field_name: Name of the string field to validate
        min_length: Minimum string length
        max_length: Maximum string length
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.json
            if data and field_name in data and data[field_name]:
                value = str(data[field_name])
                length = len(value)

                if min_length is not None and length < min_length:
                    return jsonify(
                        {
                            "message": f"Field '{field_name}' must be at least {min_length} characters"
                        }
                    ), 400

                if max_length is not None and length > max_length:
                    return jsonify(
                        {
                            "message": f"Field '{field_name}' must be at most {max_length} characters"
                        }
                    ), 400

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_enum(field_name, allowed_values):
    """
    Decorator to validate that a field value is in allowed list.

    Usage:
        @validate_enum('status', ['pending', 'completed', 'cancelled'])
        def update_status():
            # Status is validated against allowed values
            pass

    Args:
        field_name: Name of the field to validate
        allowed_values: List of allowed values
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.json
            if data and field_name in data:
                value = data[field_name]
                if value not in allowed_values:
                    return jsonify(
                        {
                            "message": f"Invalid value for '{field_name}'",
                            "allowed_values": allowed_values,
                            "received": value,
                        }
                    ), 400
            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_future_date(field_name="date"):
    """
    Decorator to validate that a date is in the future.

    Usage:
        @validate_future_date('appointment_date')
        def book_appointment():
            # Date must be in the future
            pass

    Args:
        field_name: Name of the date field to validate
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.json
            if data and field_name in data and data[field_name]:
                date_str = data[field_name]
                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if date < datetime.now().date():
                        return jsonify(
                            {
                                "message": f"Date '{field_name}' must be in the future",
                                "received": date_str,
                            }
                        ), 400
                except ValueError:
                    pass  # Let date_format validator handle this
            return func(*args, **kwargs)

        return wrapper

    return decorator


# --- Utility Function ---


def sanitize_string(value, max_length=1000):
    """
    Sanitize a string value by trimming whitespace and limiting length.

    Args:
        value: String value to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    if not value:
        return value
    sanitized = str(value).strip()
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized
