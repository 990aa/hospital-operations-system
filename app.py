"""
Hospital Operations System - Main Application Entry Point.

This is the main Flask application that initializes all components:
- Flask web server
- SQLAlchemy database
- Flask-Security for authentication
- Flask-Caching with Redis
- Flask-Mail for email notifications
- Celery for background tasks

Author: Abdul Ahad
"""

import os
import logging
import traceback
import time
import uuid
from datetime import timedelta
from logging.config import dictConfig
from dotenv import load_dotenv
import structlog
from sqlalchemy import inspect, text
from werkzeug.exceptions import HTTPException

from flask import Flask, render_template, jsonify, request, g
from flask_mail import Mail
from models.database import db, User, Role, Department
from flask_security import Security, SQLAlchemyUserDatastore
from backend.errors import problem

# Load environment variables from .env file in project root.
# This keeps sensitive credentials (SMTP password) out of the codebase
# and avoids polluting the system environment on Windows.
load_dotenv()

# Shared extension singletons initialised inside create_app()
from backend.extensions import cache, jwt, limiter, talisman, api_docs, metrics

# Ensure all front-end vendor assets are present before serving requests.
# Downloads only on first run (or when files are missing); no-op thereafter.
from backend.ensure_vendors import ensure_vendors

ensure_vendors()

# Import route blueprints
from backend.routes.auth_routes import auth_bp
from backend.routes.admin_routes import admin_bp
from backend.routes.doctor_routes import doctor_bp
from backend.routes.patient_routes import patient_bp
from backend.routes.blood_bank_routes import blood_bank_bp
from backend.routes.docs_routes import docs_blp

# Import Celery configuration
from backend.celery_config import celery

# Flask-Mail singleton – initialised with app inside create_app()
mail = Mail()


def _configure_structlog(log_level: str = "INFO") -> None:
    """Configure stdlib logging and structlog JSON output."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "format": "%(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "plain",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": level,
            },
        }
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _probe_database() -> dict:
    """Run a lightweight DB round-trip used by health checks."""
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "detail": str(exc)}


def _probe_cache() -> dict:
    """Run a cache set/get/delete probe used by health checks."""
    probe_key = f"health:{uuid.uuid4().hex}"
    try:
        cache.set(probe_key, "ok", timeout=5)
        cache_value = cache.get(probe_key)
        cache.delete(probe_key)
        if cache_value != "ok":
            return {"status": "down", "detail": "cache round-trip mismatch"}
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "detail": str(exc)}


def _health_payload() -> dict:
    """Build structured health payload for API and Docker checks."""
    from datetime import datetime

    checks = {
        "database": _probe_database(),
        "cache": _probe_cache(),
    }
    status = (
        "healthy" if all(v["status"] == "up" for v in checks.values()) else "degraded"
    )
    return {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }


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
    # Using SQLite by default, overridable via environment variables.
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        os.environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///hospital.db"),
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Disable warning

    # Security Configuration
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "thisisasecretkey")
    app.config["SECURITY_PASSWORD_SALT"] = os.environ.get(
        "SECURITY_PASSWORD_SALT", "somesalt"
    )
    app.config["SECURITY_REGISTERABLE"] = False  # Only admin can register doctors
    app.config["SECURITY_SEND_REGISTER_EMAIL"] = False  # Disable email for now
    app.config["SECURITY_USERNAME_ENABLE"] = True  # Enable username login

    if test_config:
        app.config.update(test_config)

    app.config.setdefault("LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
    app.config.setdefault("METRICS_ENABLED", not app.config.get("TESTING", False))

    # OpenAPI / Swagger configuration (flask-smorest)
    app.config.setdefault("API_TITLE", "Hospital Operations API")
    app.config.setdefault("API_VERSION", "v1")
    app.config.setdefault("OPENAPI_VERSION", "3.0.3")
    app.config.setdefault("OPENAPI_URL_PREFIX", "/api")
    app.config.setdefault("OPENAPI_JSON_PATH", "openapi.json")
    app.config.setdefault("OPENAPI_SWAGGER_UI_PATH", "/docs")
    app.config.setdefault(
        "OPENAPI_SWAGGER_UI_URL", "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    )

    # JWT configuration for stateless API auth (session auth remains enabled).
    app.config.setdefault(
        "JWT_SECRET_KEY", os.environ.get("JWT_SECRET_KEY", app.config["SECRET_KEY"])
    )
    app.config.setdefault("JWT_ACCESS_TOKEN_EXPIRES", timedelta(minutes=15))
    app.config.setdefault("JWT_REFRESH_TOKEN_EXPIRES", timedelta(days=7))
    app.config.setdefault("JWT_TOKEN_LOCATION", ["headers", "cookies"])
    app.config.setdefault("JWT_COOKIE_CSRF_PROTECT", False)
    app.config.setdefault("JWT_REFRESH_COOKIE_PATH", "/api/token/refresh")
    app.config.setdefault(
        "JWT_COOKIE_SECURE",
        bool(os.environ.get("APP_ENV", "development").lower() == "production"),
    )

    app.config.setdefault(
        "RATELIMIT_STORAGE_URI", os.environ.get("REDIS_URL", "memory://")
    )
    if app.config.get("TESTING"):
        app.config["RATELIMIT_STORAGE_URI"] = "memory://"

    # Logging configuration
    # Request context fields are bound by middleware so every log line can be
    # correlated across services by request_id.
    _configure_structlog(app.config.get("LOG_LEVEL", "INFO"))
    app.logger.setLevel(
        getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    )

    # Caching Configuration
    # Using Redis for caching - improves performance for frequently accessed data
    app.config.setdefault("CACHE_TYPE", os.environ.get("CACHE_TYPE", "RedisCache"))
    app.config.setdefault(
        "CACHE_REDIS_URL",
        os.environ.get("CACHE_REDIS_URL", "redis://localhost:6379/0"),
    )
    app.config.setdefault(
        "CACHE_DEFAULT_TIMEOUT", 300
    )  # 5 minutes default cache expiry

    # Initialize cache with app
    # ``cache`` is the module-level singleton from backend.extensions so that
    # route modules can import it directly with a static type instead of going
    # through the dynamic ``current_app.cache`` attribute.
    cache.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    api_docs.init_app(app)
    if app.config.get("METRICS_ENABLED", True):
        try:
            metrics.init_app(app)
        except ValueError as exc:
            app.logger.warning("Prometheus metrics already initialized: %s", exc)
    talisman.init_app(
        app,
        force_https=False,
        content_security_policy={
            "default-src": "'self'",
            "script-src": [
                "'self'",
                "'unsafe-inline'",
                "cdn.jsdelivr.net",
                "unpkg.com",
            ],
        },
    )

    # Flask-Mail Configuration
    # Credentials are loaded from the .env file via python-dotenv.
    # Uses Gmail SMTP with an App Password for secure demo delivery.
    app.config.setdefault("MAIL_SERVER", "smtp.gmail.com")
    app.config.setdefault("MAIL_PORT", 587)
    app.config.setdefault("MAIL_USE_TLS", True)
    app.config.setdefault("MAIL_USERNAME", os.environ.get("SMTP_USERNAME", ""))
    app.config.setdefault("MAIL_PASSWORD", os.environ.get("SMTP_PASSWORD", ""))
    app.config.setdefault(
        "MAIL_DEFAULT_SENDER", os.environ.get("FROM_EMAIL", "hms238537@gmail.com")
    )

    # Initialize Flask-Mail with app
    mail.init_app(app)

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
    # Server-rendered blood bank module pages live under /blood-bank.
    app.register_blueprint(blood_bank_bp)
    api_docs.register_blueprint(docs_blp, url_prefix="/api")

    # Routes
    @app.route("/")
    def index():
        """
        Serve the main application page.

        This renders the Vue.js frontend which handles all client-side routing.
        """
        return render_template("index.html")

    @app.before_request
    def bind_request_context():
        """Attach request metadata for tracing and structured logging."""
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = request_id
        g.request_started_at = time.perf_counter()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.path,
        )

    @app.after_request
    def append_request_id(response):
        """Propagate request ID to clients and emit per-request access logs."""
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        started_at = getattr(g, "request_started_at", None)
        duration_ms = None
        if started_at is not None:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        structlog.get_logger("hos.http").info(
            "request.completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
            remote_addr=request.remote_addr,
        )
        structlog.contextvars.clear_contextvars()
        return response

    @app.route("/api/health")
    def api_health_check():
        """Detailed health status for orchestrators and monitoring systems."""
        payload = _health_payload()
        status_code = 200 if payload["status"] == "healthy" else 503
        return jsonify(payload), status_code

    @app.route("/health")
    def health_check():
        """Backward-compatible lightweight health endpoint."""
        payload = _health_payload()
        return {
            "status": payload["status"],
            "timestamp": payload["timestamp"],
            "cache": (
                "connected"
                if payload["checks"]["cache"]["status"] == "up"
                else "unavailable"
            ),
        }

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
        structlog.get_logger("hos.client").error("client.error", payload=payload)
        return jsonify({"logged": True})

    # --- TEST_ONLY_BLOCK END ---

    @app.errorhandler(404)
    def not_found_error(error):
        """Return problem+json for unknown API routes while keeping normal web 404 behavior."""
        if request.path.startswith("/api"):
            structlog.get_logger("hos.api").warning(
                "api.not_found",
                path=request.path,
            )
            return problem(404, "Not Found", str(error))
        return error, 404

    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith("/api"):
            return problem(403, "Forbidden", str(error))
        return error, 403

    @app.errorhandler(422)
    def unprocessable_error(error):
        if request.path.startswith("/api"):
            return problem(422, "Validation Error", str(error))
        return error, 422

    @app.errorhandler(Exception)
    def unhandled_exception(error):
        """Centralized exception handler.

        - Preserves HTTPException status codes (401/403/404/etc.) for API routes.
        - Converts unexpected API exceptions to a safe JSON 500 response.
        - Keeps terminal logs detailed with traceback for debugging.
        """
        if isinstance(error, HTTPException):
            if request.path.startswith("/api"):
                structlog.get_logger("hos.api").warning(
                    "api.http_exception",
                    path=request.path,
                    method=request.method,
                    status=error.code,
                    description=error.description,
                )
                return problem(error.code or 500, error.name, error.description)
            return error

        if request.path.startswith("/api"):
            structlog.get_logger("hos.api").error(
                "api.unhandled_exception",
                path=request.path,
                method=request.method,
                error=str(error),
                traceback=traceback.format_exc(),
            )
            return problem(500, "Internal Server Error", "Internal server error")
        structlog.get_logger("hos.web").error(
            "web.unhandled_exception",
            error=str(error),
            traceback=traceback.format_exc(),
        )
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
        app.user_datastore.find_or_create_role(
            name="blood_bank_staff", description="Blood bank authorized staff"
        )
        db.session.commit()

        # Create admin user if doesn't exist
        if not app.user_datastore.find_user(username="admin"):
            admin_user = app.user_datastore.create_user(
                username="admin",
                email="admin@hospital.com",
                password="admin",
                roles=["admin"],
                name="Admin",
                active=True,
                fs_uniquifier="admin_uniq",
            )
            admin_user.set_password("admin")
            db.session.commit()
            print("Admin created: username='admin', password='admin'")

        # Seed a dedicated blood bank operator account for demonstrations.
        if not app.user_datastore.find_user(username="bbstaff"):
            blood_bank_user = app.user_datastore.create_user(
                username="bbstaff",
                email="bbstaff@hospital.com",
                password="bbstaff",
                roles=["blood_bank_staff"],
                name="Blood Bank Staff",
                active=True,
                fs_uniquifier="bbstaff_uniq",
            )
            blood_bank_user.set_password("bbstaff")
            db.session.commit()
            print("Blood bank staff created: username='bbstaff', password='bbstaff'")

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

        # One-time hardening pass: re-hash known seeded/demo users to Argon2.
        from scripts.migrate_passwords import migrate_passwords

        migrated_count = migrate_passwords(app)
        if migrated_count:
            print(f"Migrated {migrated_count} legacy password hashes to Argon2")


# Create the Flask application instance
app = create_app()

# Initialize schema and baseline seed data for all runtimes, including
# gunicorn imports in Docker where __main__ is not executed.
create_initial_data(app)


if __name__ == "__main__":
    # Run the development server
    # Use environment variables so local and Docker runs share one entrypoint.
    debug_env = os.environ.get("FLASK_DEBUG", "true").strip().lower()
    debug_enabled = debug_env in {"1", "true", "yes", "on"}
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(host=host, port=port, debug=debug_enabled)
