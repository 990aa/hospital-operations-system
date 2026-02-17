"""
Comprehensive Route and Rendering Tests.

Verifies that the main entry point renders without syntax errors and all
API endpoints return appropriate responses.
"""

import pytest

def test_home_page_renders(test_client):
    """Verify that index.html renders without Jinja2 TemplateSyntaxErrors."""
    response = test_client.get('/')
    assert response.status_code == 200
    assert b'Hospital Management System' in response.data
    # Verify Vue.js is loaded (development build for debugging)
    assert b'vue.global.js' in response.data

def test_api_health_check(test_client):
    """Verify that the health check endpoint is functional."""
    response = test_client.get('/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'healthy'

def test_unauthorized_access(test_client):
    """Verify that protected API routes correctly return 401/403 for unauthenticated users."""
    protected_routes = [
        '/api/admin/stats',
        '/api/admin/doctors',
        '/api/admin/patients',
        '/api/doctor/appointments',
        '/api/my-appointments',
        '/api/profile'
    ]
    for route in protected_routes:
        response = test_client.get(route)
        # Flask-Security may redirect (302) to login page or return 401/403
        assert response.status_code in [302, 401, 403]
