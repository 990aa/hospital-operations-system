"""Observability and health endpoint tests."""

from app import create_app
from models.database import db


def _metrics_client():
    """Build a dedicated app with metrics enabled for endpoint validation."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "metrics-test-secret",
            "SECURITY_PASSWORD_SALT": "metrics-test-salt",
            "CACHE_TYPE": "SimpleCache",
            "METRICS_ENABLED": True,
            "RATELIMIT_ENABLED": True,
            "RATELIMIT_STORAGE_URI": "memory://",
        }
    )
    with app.app_context():
        db.create_all()
    return app.test_client()


def test_api_health_endpoint_includes_dependency_checks(test_client):
    response = test_client.get("/api/health")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["status"] == "healthy"
    assert payload["checks"]["database"]["status"] == "up"
    assert payload["checks"]["cache"]["status"] == "up"


def test_request_id_is_echoed_back(test_client):
    response = test_client.get("/api/health", headers={"X-Request-ID": "req-obsv-1"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "req-obsv-1"


def test_problem_response_contains_request_id(test_client):
    response = test_client.get(
        "/api/this-route-does-not-exist",
        headers={"X-Request-ID": "req-obsv-404"},
    )
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["request_id"] == "req-obsv-404"


def test_metrics_endpoint_exposes_custom_booking_metrics():
    client = _metrics_client()
    response = client.get("/metrics")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "hos_appointment_booking_attempts_total" in body
    assert "hos_appointment_booking_duration_seconds" in body
