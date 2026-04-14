"""Security hardening regression tests."""

from datetime import datetime, timezone

import jwt
from flask_jwt_extended import create_refresh_token

from models.database import User


def test_registered_password_is_not_stored_plaintext(test_client):
    response = test_client.post(
        "/api/register",
        json={
            "username": "securepatient",
            "password": "StrongPass123",
            "name": "Secure Patient",
            "email": "securepatient@test.com",
            "phone": "9000012345",
        },
    )
    assert response.status_code == 200

    with test_client.application.app_context():
        user = User.query.filter_by(username="securepatient").first()
        assert user is not None
        assert user.password != "StrongPass123"
        assert user.password.startswith("$argon2")
        assert user.check_password("StrongPass123") is True


def test_jwt_issue_sets_refresh_cookie_and_expiry_window(test_client):
    response = test_client.post(
        "/api/token", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" in data
    assert data["role"] == "admin"

    # Access token should be short-lived (~15 minutes).
    decoded_access = jwt.decode(
        data["access_token"],
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )
    ttl_seconds = decoded_access["exp"] - decoded_access["iat"]
    assert 850 <= ttl_seconds <= 930

    set_cookie_headers = response.headers.getlist("Set-Cookie")
    assert any("refresh_token_cookie=" in header for header in set_cookie_headers)


def test_jwt_refresh_issues_new_access_token(test_client):
    issue_response = test_client.post(
        "/api/token", json={"username": "admin", "password": "admin"}
    )
    assert issue_response.status_code == 200

    refresh_response = test_client.post("/api/token/refresh")
    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.get_json()
    assert "access_token" in refresh_payload
    assert refresh_payload["role"] == "admin"


def test_issue_token_invalid_credentials_returns_401(test_client):
    response = test_client.post(
        "/api/token", json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_jwt_refresh_unknown_user_returns_401(test_client):
    with test_client.application.app_context():
        refresh_token = create_refresh_token(
            identity="999999", additional_claims={"role": "admin"}
        )

    test_client.set_cookie(
        "refresh_token_cookie", refresh_token, domain="localhost"
    )
    response = test_client.post("/api/token/refresh")
    assert response.status_code == 401


def test_login_role_hint_for_unregistered_patient_returns_flag(test_client):
    response = test_client.post(
        "/api/login",
        json={"username": "ghost", "password": "whatever", "role": "patient"},
    )
    assert response.status_code == 401
    payload = response.get_json()
    assert payload.get("not_registered") is True


def test_rate_limit_blocks_after_10_login_attempts(test_client):
    last_response = None
    for _ in range(11):
        last_response = test_client.post(
            "/api/login", json={"username": "admin", "password": "wrong-password"}
        )

    assert last_response is not None
    assert last_response.status_code == 429


def test_admin_route_forbidden_for_non_admin(patient_token):
    response = patient_token.get("/api/admin/stats")
    assert response.status_code == 403


def test_unauthenticated_api_returns_401_not_500(test_client):
    response = test_client.get("/api/current-user")
    assert response.status_code == 401

    protected_response = test_client.get("/api/admin/stats")
    assert protected_response.status_code != 500
