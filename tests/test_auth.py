"""
Authentication Tests.

Tests for login, logout, and registration functionality.

Author: Abdul Ahad
"""


def test_login_logout(test_client):
    """
    Test login and logout flow.

    Verifies:
    - Successful login returns 200 with user data
    - User role is correctly identified
    - Logout works properly
    """
    # Login with valid credentials
    response = test_client.post(
        "/api/login", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["role"] == "admin"
    assert "user" in data
    assert data["user"]["name"] == "Test Admin"

    # Valid logout
    response = test_client.post("/api/logout")
    assert response.status_code == 200


def test_login_invalid(test_client):
    """
    Test login with invalid credentials.

    Verifies:
    - Invalid password returns 401
    - Non-existent user returns 401
    """
    # Wrong password
    response = test_client.post(
        "/api/login", json={"username": "admin", "password": "wrongpassword"}
    )
    assert response.status_code == 401

    # Non-existent user
    response = test_client.post(
        "/api/login", json={"username": "nonexistent", "password": "password"}
    )
    assert response.status_code == 401


def test_register_patient(test_client):
    """
    Test patient registration.

    Verifies:
    - New patient can register
    - Duplicate username is rejected
    - New user can login after registration
    """
    response = test_client.post(
        "/api/register",
        json={
            "username": "newpatient",
            "password": "password123",
            "name": "New Patient",
            "email": "newpatient@test.com",
            "phone": "5551234567",
        },
    )
    assert response.status_code == 200

    # Verify login
    response = test_client.post(
        "/api/login", json={"username": "newpatient", "password": "password123"}
    )
    assert response.status_code == 200
    assert response.get_json()["role"] == "patient"


def test_register_duplicate_username(test_client):
    """
    Test registration with duplicate username.

    Verifies:
    - Registration with existing username is rejected
    """
    # First registration
    test_client.post(
        "/api/register",
        json={
            "username": "duplicateuser",
            "password": "password123",
            "name": "First User",
            "email": "first@test.com",
        },
    )

    # Duplicate registration should fail
    response = test_client.post(
        "/api/register",
        json={
            "username": "duplicateuser",
            "password": "password456",
            "name": "Second User",
            "email": "second@test.com",
        },
    )
    assert response.status_code == 400
    assert "already exists" in response.get_json()["message"]


def test_register_without_email(test_client):
    """
    Test registration without email is rejected.

    Verifies:
    - Email is mandatory for patient registration
    """
    response = test_client.post(
        "/api/register",
        json={
            "username": "noemail",
            "password": "password123",
            "name": "No Email Patient",
        },
    )
    assert response.status_code == 400


def test_register_duplicate_email(test_client):
    """
    Test registration with duplicate email is rejected.

    Verifies:
    - Email uniqueness is enforced during registration
    """
    # First registration
    test_client.post(
        "/api/register",
        json={
            "username": "emailuser1",
            "password": "password123",
            "name": "Email User One",
            "email": "duplicate@test.com",
        },
    )

    # Second registration with same email should fail
    response = test_client.post(
        "/api/register",
        json={
            "username": "emailuser2",
            "password": "password456",
            "name": "Email User Two",
            "email": "duplicate@test.com",
        },
    )
    assert response.status_code == 400


def test_current_user_endpoint(test_client, admin_token):
    """
    Test current user endpoint.

    Verifies:
    - Returns user data when authenticated
    - Returns 401 when not authenticated
    """
    # When authenticated
    response = admin_token.get("/api/current-user")
    assert response.status_code == 200
    data = response.get_json()
    assert data["username"] == "admin"
    assert "admin" in data["roles"]

    # Logout and check
    admin_token.post("/api/logout")
    response = admin_token.get("/api/current-user")
    assert response.status_code == 401
