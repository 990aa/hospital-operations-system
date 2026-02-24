"""
Hospital Management System - Main Application Entry Point.

This is the main Flask application that initializes all components:
- Flask web server
- SQLAlchemy database
- Flask-Security for authentication
- Flask-Caching with Redis
- Celery for background tasks

Author: Abdul Ahad
"""

import logging
import traceback
from sqlalchemy import inspect
from werkzeug.exceptions import HTTPException

from flask import Flask, render_template, jsonify, request
from models.database import db, User, Role, Department
from flask_security import Security, SQLAlchemyUserDatastore
from flask_security.utils import hash_password

# Shared extension singleton (Cache) initialised inside create_app()
from backend.extensions import cache

# Ensure all front-end vendor assets are present before serving requests.
# Downloads only on first run (or when files are missing); no-op thereafter.
from backend.ensure_vendors import ensure_vendors
ensure_vendors()

# Import route blueprints
from backend.routes.auth_routes import auth_bp
from backend.routes.admin_routes import admin_bp
from backend.routes.doctor_routes import doctor_bp
from backend.routes.patient_routes import patient_bp

# Import Celery configuration
from backend.celery_config import celery


class HospitalApp(Flask):
    """
    Typed Flask subclass that declares the custom attribute attached
    by create_app() so that static type checkers (ty, mypy) can resolve
    ``app.user_datastore`` without raising ``unresolved-attribute`` errors.

    The ``Cache`` singleton is now a module-level object in
    ``backend.extensions`` and is imported directly by route modules,
    avoiding the need for a ``current_app.cache`` dynamic lookup.
    """

    user_datastore: SQLAlchemyUserDatastore


def create_app(test_config=None):
    """
    Create and configure the Flask application.

    This factory function creates a Flask app with all necessary configurations
    including database, security, caching, and Celery integration.

    Args:
        test_config: Optional dictionary with test-specific configurations.

    Returns:
        Configured Flask application instance
    """
    # Create Flask app with custom template and static folders
    app = HospitalApp(
        __name__, template_folder="frontend", static_folder="frontend/static"
    )

    # Database Configuration
    # Using SQLite
    app.config.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///hospital.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Disable warning

    # Security Configuration
    app.config["SECRET_KEY"] = "thisisasecretkey"
    app.config["SECURITY_PASSWORD_SALT"] = "somesalt"
    app.config["SECURITY_REGISTERABLE"] = False  # Only admin can register doctors
    app.config["SECURITY_SEND_REGISTER_EMAIL"] = False  # Disable email for now
    app.config["SECURITY_USERNAME_ENABLE"] = True  # Enable username login

    if test_config:
        app.config.update(test_config)

    # Logging configuration
    # We keep logging at INFO so normal startup and request logs are visible,
    # while explicit error logs (CLIENT_ERROR/API_EXCEPTION) are emitted
    # by our handlers below for terminal-first debugging.
    app.logger.setLevel(logging.INFO)

    # Caching Configuration
    # Using Redis for caching - improves performance for frequently accessed data
    app.config.setdefault("CACHE_TYPE", "RedisCache")
    app.config.setdefault("CACHE_REDIS_URL", "redis://localhost:6379/0")
    app.config.setdefault(
        "CACHE_DEFAULT_TIMEOUT", 300
    )  # 5 minutes default cache expiry

    # Initialize cache with app
    # ``cache`` is the module-level singleton from backend.extensions so that
    # route modules can import it directly with a static type instead of going
    # through the dynamic ``current_app.cache`` attribute.
    cache.init_app(app)

    # Initialize Extensions
    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize Flask-Security
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    Security(app, user_datastore)

    # Store references for access in other modules
    app.user_datastore = user_datastore

    # Initialize Celery with Flask app context
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        """
        Custom Celery task class that runs tasks within Flask app context.

        This ensures database operations and other Flask-dependent operations
        work correctly in background tasks.
        """

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    # Register Blueprints
    # All routes are prefixed with /api
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
    app.register_blueprint(doctor_bp, url_prefix="/api")
    app.register_blueprint(patient_bp, url_prefix="/api")

    # Routes
    @app.route("/")
    def index():
        """
        Serve the main application page.

        This renders the Vue.js frontend which handles all client-side routing.
        """
        return render_template("index.html")

    # --- TEST_ONLY_BLOCK START ---
    # Health check endpoint used by automated tests and CI pipelines.
    # Safe to delete before final submission without breaking app functionality.
    @app.route("/health")
    def health_check():
        """
        Health check endpoint for monitoring.

        Returns:
            JSON with status and timestamp
        """
        from datetime import datetime

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "cache": "connected" if cache else "not configured",
        }

    # --- TEST_ONLY_BLOCK END ---

    # --- TEST_ONLY_BLOCK START ---
    # Client-side error logger endpoint used during development and test runs.
    # Forwards browser-side errors to the terminal for debugging.
    # Safe to delete before final submission; the app will still function
    # (the frontend silently ignores /api/client-log failures).
    @app.route("/api/client-log", methods=["POST"])
    def client_log():
        """Log frontend/runtime errors to backend terminal logs.

        This endpoint accepts structured JSON payloads from the frontend
        (for example, failed fetch parsing, API failures, and runtime errors)
        and writes the full payload to server logs so errors are not shown in UI.
        """
        payload = request.get_json(silent=True) or {}
        app.logger.error("CLIENT_ERROR %s", payload)
        return jsonify({"logged": True})

    # --- TEST_ONLY_BLOCK END ---

    @app.errorhandler(404)
    def not_found_error(error):
        """Return JSON for unknown API routes while keeping normal web 404 behavior."""
        if request.path.startswith("/api"):
            app.logger.error("API_404 path=%s", request.path)
            return jsonify({"message": "Route not found"}), 404
        return error, 404

    @app.errorhandler(Exception)
    def unhandled_exception(error):
        """Centralized exception handler.

        - Preserves HTTPException status codes (401/403/404/etc.) for API routes.
        - Converts unexpected API exceptions to a safe JSON 500 response.
        - Keeps terminal logs detailed with traceback for debugging.
        """
        if isinstance(error, HTTPException):
            if request.path.startswith("/api"):
                app.logger.error(
                    "API_HTTP_EXCEPTION path=%s method=%s status=%s description=%s",
                    request.path,
                    request.method,
                    error.code,
                    error.description,
                )
                return jsonify({"message": error.description}), error.code
            return error

        if request.path.startswith("/api"):
            app.logger.error(
                "API_EXCEPTION path=%s method=%s error=%s\n%s",
                request.path,
                request.method,
                str(error),
                traceback.format_exc(),
            )
            return jsonify({"message": "Internal server error"}), 500
        app.logger.error("WEB_EXCEPTION %s\n%s", str(error), traceback.format_exc())
        return "Internal server error", 500

    return app


def create_initial_data(app):
    """
    Create initial data for the application.

    This function creates:
    - Default roles (admin, doctor, patient)
    - Admin user with default credentials
    - Default departments

    Args:
        app: Flask application instance
    """
    with app.app_context():
        # Create all database tables
        db.create_all()

        # Lightweight schema migration for existing SQLite databases
        # We use additive ALTER TABLE statements so existing developer data
        # is preserved while introducing new doctor availability fields.
        inspector = inspect(db.engine)
        doctor_columns = {column["name"] for column in inspector.get_columns("doctor")}
        migration_statements = []
        if "availability_days" not in doctor_columns:
            migration_statements.append(
                "ALTER TABLE doctor ADD COLUMN availability_days VARCHAR(100) DEFAULT 'Mon,Tue,Wed,Thu,Fri'"
            )
        if "availability_start" not in doctor_columns:
            migration_statements.append(
                "ALTER TABLE doctor ADD COLUMN availability_start VARCHAR(5) DEFAULT '09:00'"
            )
        if "availability_end" not in doctor_columns:
            migration_statements.append(
                "ALTER TABLE doctor ADD COLUMN availability_end VARCHAR(5) DEFAULT '17:00'"
            )
        if "slot_minutes" not in doctor_columns:
            migration_statements.append(
                "ALTER TABLE doctor ADD COLUMN slot_minutes INTEGER DEFAULT 30"
            )
        if "bio" not in doctor_columns:
            migration_statements.append(
                "ALTER TABLE doctor ADD COLUMN bio TEXT DEFAULT ''"
            )
        if "appointment_cost" not in doctor_columns:
            migration_statements.append(
                "ALTER TABLE doctor ADD COLUMN appointment_cost REAL DEFAULT 500.0"
            )

        # Execute each migration statement in sequence.
        for statement in migration_statements:
            db.session.execute(db.text(statement))

        if migration_statements:
            db.session.commit()

        # Appointment table additive migrations for follow-up workflow and
        # race-safe uniqueness constraints during concurrent bookings.
        appointment_columns = {
            column["name"] for column in inspector.get_columns("appointment")
        }
        appointment_migrations = []
        if "is_follow_up" not in appointment_columns:
            appointment_migrations.append(
                "ALTER TABLE appointment ADD COLUMN is_follow_up BOOLEAN DEFAULT 0"
            )
        if "follow_up_source_appointment_id" not in appointment_columns:
            appointment_migrations.append(
                "ALTER TABLE appointment ADD COLUMN follow_up_source_appointment_id INTEGER"
            )

        for statement in appointment_migrations:
            db.session.execute(db.text(statement))

        if appointment_migrations:
            db.session.commit()

        # Create unique index for doctor/date/time to prevent duplicate slots
        # under simultaneous booking attempts.
        existing_indexes = {
            idx["name"]
            for idx in inspector.get_indexes("appointment")
            if idx.get("name")
        }
        if "uq_appointment_doctor_date_time" not in existing_indexes:
            try:
                db.session.execute(
                    db.text(
                        "CREATE UNIQUE INDEX uq_appointment_doctor_date_time ON appointment (doctor_id, date, time)"
                    )
                )
                db.session.commit()
            except Exception as error:
                db.session.rollback()
                app.logger.warning(
                    "Could not create uq_appointment_doctor_date_time index: %s", error
                )

        # Create default roles
        # Roles are used for access control in the application
        app.user_datastore.find_or_create_role(
            name="admin", description="Administrator"
        )
        app.user_datastore.find_or_create_role(name="doctor", description="Doctor")
        app.user_datastore.find_or_create_role(name="patient", description="Patient")
        db.session.commit()

        # Create admin user if doesn't exist
        if not app.user_datastore.find_user(username="admin"):
            app.user_datastore.create_user(
                username="admin",
                email="admin@hospital.com",
                password=hash_password("admin"),
                roles=["admin"],
                name="Admin",
                active=True,
                fs_uniquifier="admin_uniq",
            )
            db.session.commit()
            print("Admin created: username='admin', password='admin'")

        # Create default departments
        # Departments represent medical specializations
        if not Department.query.first():
            depts = [
                Department(name="General Medicine", description="General health care"),
                Department(name="Cardiology", description="Heart related treatments"),
                Department(name="Dermatology", description="Skin related treatments"),
                Department(name="Pediatrics", description="Child health care"),
                Department(name="Neurology", description="Brain and nerves"),
            ]
            db.session.add_all(depts)
            db.session.commit()
            print("Initial departments created")

        # Clean invalid/orphan patient rows so patients only exist after registration.
        # This removes ghost patient records caused by old inconsistent seed data
        # (for example, rows with no linked user or empty user names).
        from models.database import Patient

        invalid_patients = (
            Patient.query.join(User, Patient.user_id == User.id, isouter=True)
            .filter((User.id.is_(None)) | (User.name.is_(None)) | (User.name == ""))
            .all()
        )
        for patient in invalid_patients:
            db.session.delete(patient)
        if invalid_patients:
            db.session.commit()
            print(f"Removed {len(invalid_patients)} invalid patient profiles")


# Create the Flask application instance
app = create_app()


if __name__ == "__main__":
    # Initialize database and create initial data
    create_initial_data(app)
    # Run the development server
    # Use debug=True only in development!
    app.run(debug=True, port=5000)
