from flask import Blueprint, jsonify, current_app
from flask_security import login_user, logout_user, login_required, current_user
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    set_refresh_cookies,
    unset_jwt_cookies,
)
from models.database import db, User, Patient
from backend.errors import problem
from backend.extensions import limiter
from backend.schemas import LoginRequest, RegisterRequest, validate
from backend.validators import sanitize_string

auth_bp = Blueprint("auth", __name__)


def _resolve_role(user: User) -> str:
    """Map the current user object to frontend role labels."""
    if user.has_role("admin"):
        return "admin"
    if user.has_role("doctor"):
        return "doctor"
    if user.has_role("blood_bank_staff"):
        return "blood_bank_staff"
    return "patient"


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute; 50 per hour")
@validate(LoginRequest)
def login(data: LoginRequest):
    """Log in a user (Admin, Doctor, or Patient)."""
    username = sanitize_string(data.username, max_length=50)
    password = data.password

    user = User.query.filter_by(username=username).first()

    # If user not found at all, give a role-aware message so unregistered
    # patients are directed to the register form rather than just told
    # "Invalid credentials".
    if not user:
        # Check the role hint passed from the frontend (optional field, harmless if absent)
        role_hint = (data.role or "").lower()
        if role_hint == "patient":
            return problem(
                401,
                "Invalid Credentials",
                "No account found. Please register first.",
                not_registered=True,
            )
        return problem(401, "Invalid Credentials", "Invalid credentials")

    if not user.check_password(password):
        return problem(401, "Invalid Credentials", "Invalid credentials")

    login_user(user)
    return jsonify({"role": _resolve_role(user), "user": user.to_dict()})


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    response = jsonify({"message": "Logged out"})
    unset_jwt_cookies(response)
    return response


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
@validate(RegisterRequest)
def register(data: RegisterRequest):
    """Register a new patient. Email is mandatory for notifications."""

    # Sanitize inputs
    username = sanitize_string(data.username, max_length=50)
    name = sanitize_string(data.name, max_length=100)
    email = sanitize_string(data.email, max_length=255)
    phone = sanitize_string(data.phone, max_length=20) if data.phone else None

    if User.query.filter_by(username=username).first():
        return problem(400, "Bad Request", "Username already exists")

    # Email is mandatory for patients (all notifications go via email).
    if User.query.filter_by(email=email).first():
        return problem(400, "Bad Request", "Email already in use")

    # Create User
    user_datastore = current_app.extensions["security"].datastore

    new_user = user_datastore.create_user(
        username=username,
        password=data.password,
        name=name,
        email=email,
        phone=phone,
        active=True,
    )
    new_user.set_password(data.password)
    user_datastore.add_role_to_user(new_user, "patient")
    db.session.commit()

    # Create Patient Profile
    new_patient = Patient(user_id=new_user.id)
    db.session.add(new_patient)
    db.session.commit()

    return jsonify({"message": "Registration successful"})


@auth_bp.route("/token", methods=["POST"])
@limiter.limit("10 per minute; 50 per hour")
@validate(LoginRequest)
def issue_token(data: LoginRequest):
    """Issue access and refresh JWT tokens for stateless API clients."""
    username = sanitize_string(data.username, max_length=50)
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(data.password):
        return problem(401, "Invalid Credentials", "invalid_credentials")

    role = _resolve_role(user)
    claims = {"role": role}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims)
    response = jsonify({"access_token": access, "role": role})
    set_refresh_cookies(response, refresh)
    return response


@auth_bp.route("/token/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh_token():
    """Issue a new short-lived access token using a valid refresh token cookie."""
    identity = get_jwt_identity()
    user = User.query.get(int(identity)) if identity is not None else None
    if not user:
        return problem(401, "Unauthorized", "User not found")

    role = _resolve_role(user)
    access = create_access_token(
        identity=str(user.id), additional_claims={"role": role}
    )
    return jsonify({"access_token": access, "role": role})


@auth_bp.route("/current-user", methods=["GET"])
def get_current_user():
    if current_user.is_authenticated:
        return jsonify(current_user.to_dict())
    return jsonify(None), 401
