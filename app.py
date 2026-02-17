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

from flask import Flask, render_template
from flask_caching import Cache
from models.database import db, User, Role, Department
from flask_security import Security, SQLAlchemyUserDatastore
from flask_security.utils import hash_password

# Import route blueprints
from backend.routes.auth_routes import auth_bp
from backend.routes.admin_routes import admin_bp
from backend.routes.doctor_routes import doctor_bp
from backend.routes.patient_routes import patient_bp

# Import Celery configuration
from backend.celery_config import celery


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
    app = Flask(__name__, template_folder="frontend", static_folder="frontend/static")

    if test_config:
        app.config.update(test_config)

    # Database Configuration
    # Using SQLite for simplicity - can be changed to PostgreSQL/MySQL in production
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hospital.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Disable warning

    # Security Configuration
    app.config["SECRET_KEY"] = "thisisasecretkey"  # Change in production
    app.config["SECURITY_PASSWORD_SALT"] = "somesalt"  # Change in production
    app.config["SECURITY_REGISTERABLE"] = False  # Only admin can register doctors
    app.config["SECURITY_SEND_REGISTER_EMAIL"] = False  # Disable email for now
    app.config["SECURITY_USERNAME_ENABLE"] = True  # Enable username login

    # Caching Configuration
    # Using Redis for caching - improves performance for frequently accessed data
    app.config.setdefault("CACHE_TYPE", "RedisCache")
    app.config.setdefault("CACHE_REDIS_URL", "redis://localhost:6379/0")
    app.config.setdefault(
        "CACHE_DEFAULT_TIMEOUT", 300
    )  # 5 minutes default cache expiry

    # Initialize cache with app
    cache = Cache()
    cache.init_app(app)

    # Make cache available globally
    app.cache = cache

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
            "cache": "connected" if app.cache else "not configured",
        }

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
                name="Super Admin",
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


# Create the Flask application instance
app = create_app()


if __name__ == "__main__":
    # Initialize database and create initial data
    create_initial_data(app)
    # Run the development server
    # Use debug=True only in development!
    app.run(debug=True, port=5000)
