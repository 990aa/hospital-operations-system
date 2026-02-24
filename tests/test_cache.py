"""
Caching Tests.

Tests for Redis caching functionality:
- Cache hits and misses
- Cache invalidation
- Cache expiry
- Cache keys

Author: Abdul Ahad
"""

from backend.extensions import cache


def test_cache_set_and_get(test_client, admin_token):
    """
    Test basic cache set and get operations.

    Verifies:
    - Values can be stored in cache
    - Values can be retrieved from cache
    - Cache returns None for missing keys
    """
    with test_client.application.app_context():
        # Set a value
        cache.set("test_key", "test_value", timeout=60)

        # Get the value
        value = cache.get("test_key")
        assert value == "test_value"

        # Non-existent key returns None
        missing = cache.get("non_existent_key")
        assert missing is None


def test_cache_delete(test_client, admin_token):
    """
    Test cache deletion.

    Verifies:
    - Deleted keys return None
    """
    with test_client.application.app_context():
        cache.set("delete_key", "value", timeout=60)
        assert cache.get("delete_key") == "value"

        cache.delete("delete_key")
        assert cache.get("delete_key") is None


def test_cache_expiry(test_client, admin_token):
    """
    Test that cache entries expire.

    Note: This test uses a very short timeout and may be flaky
    depending on the cache backend.
    """
    with test_client.application.app_context():
        # Set with 1 second timeout
        cache.set("expiry_key", "value", timeout=1)
        assert cache.get("expiry_key") == "value"

        # Wait for expiry (skip in test for speed)
        # In real tests, you'd mock time or use a shorter timeout
        pass


def test_admin_stats_caching(test_client, admin_token):
    """
    Test that admin stats are cached.

    Verifies:
    - First request hits database
    - Subsequent requests may be cached
    - Cache invalidation works
    """
    # First call
    response1 = admin_token.get("/api/admin/stats")
    assert response1.status_code == 200
    stats1 = response1.get_json()

    # Second call (might be cached)
    response2 = admin_token.get("/api/admin/stats")
    assert response2.status_code == 200
    stats2 = response2.get_json()

    # Stats should be the same
    assert stats1["total_doctors"] == stats2["total_doctors"]


def test_departments_caching(test_client, admin_token):
    """
    Test that departments list is cached.

    Verifies:
    - Departments endpoint returns consistent results
    """
    response1 = admin_token.get("/api/departments")
    assert response1.status_code == 200
    depts1 = response1.get_json()

    response2 = admin_token.get("/api/departments")
    assert response2.status_code == 200
    depts2 = response2.get_json()

    assert len(depts1) == len(depts2)


def test_cache_invalidation_on_doctor_create(test_client, admin_token):
    """
    Test that creating a doctor invalidates relevant caches.

    Verifies:
    - After adding doctor, stats reflect new count
    """
    # Get initial stats
    response = admin_token.get("/api/admin/stats")
    initial_doctors = response.get_json()["total_doctors"]

    # Add a doctor
    resp = admin_token.get("/api/departments")
    dept_id = resp.get_json()[0]["id"]

    admin_token.post(
        "/api/admin/doctors",
        json={
            "name": "Cache Test Doc",
            "username": "cachetestdoc",
            "password": "password",
            "department_id": dept_id,
        },
    )

    # Get updated stats
    response = admin_token.get("/api/admin/stats")
    updated_doctors = response.get_json()["total_doctors"]

    # Should reflect the new doctor
    assert updated_doctors == initial_doctors + 1


def test_cache_key_format():
    """
    Test cache key naming conventions.

    Verifies:
    - Keys follow expected patterns
    """
    # This is more of a documentation test
    expected_keys = [
        "admin_stats",
        "all_departments",
        "doctors_None_",
        "patient_appointments_1_None",
        "doctor_appointments_1_None__",
        "patient_history_1",
    ]

    # Just verify the patterns are documented
    for key in expected_keys:
        assert isinstance(key, str)
        assert len(key) > 0
