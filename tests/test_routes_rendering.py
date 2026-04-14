"""
Comprehensive Route and Rendering Tests.

Verifies that the main entry point renders without syntax errors and all
API endpoints return appropriate responses.
"""


def test_home_page_renders(test_client):
    """Verify that index.html renders without Jinja2 TemplateSyntaxErrors."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"Hospital Operations System" in response.data
    # Verify Vue.js is loaded from local vendor (not CDN)
    assert b"vue.global.prod.js" in response.data


def test_home_page_uses_local_vendor_assets(test_client):
    """
    Verify that index.html references local vendor assets instead of CDN.

    This prevents blank-screen failures when CDN resources are unavailable.
    All of Bootstrap CSS/JS, Bootstrap Icons, Vue.js, and Plotly must be
    served from the local /static/vendor/ directory.
    """
    response = test_client.get("/")
    assert response.status_code == 200
    html = response.data

    # Local vendor assets must be present
    assert b"/static/vendor/css/bootstrap.min.css" in html
    assert b"/static/vendor/css/bootstrap-icons.css" in html
    assert b"/static/vendor/js/bootstrap.bundle.min.js" in html
    assert b"/static/vendor/js/vue.global.prod.js" in html
    assert b"/static/vendor/js/plotly-2.35.2.min.js" in html

    # No CDN references should remain
    assert b"cdn.jsdelivr.net" not in html
    assert b"unpkg.com" not in html
    assert b"cdn.plot.ly" not in html


def test_local_vendor_files_are_served(test_client):
    """
    Verify that the vendor static files are actually served by Flask.

    Ensures the physical files exist and Flask can serve them with HTTP 200.
    """
    vendor_files = [
        "/static/vendor/css/bootstrap.min.css",
        "/static/vendor/css/bootstrap-icons.css",
        "/static/vendor/js/bootstrap.bundle.min.js",
        "/static/vendor/js/vue.global.prod.js",
        "/static/vendor/js/plotly-2.35.2.min.js",
    ]
    for path in vendor_files:
        resp = test_client.get(path)
        assert resp.status_code == 200, f"Vendor file not served: {path}"


def test_api_health_check(test_client):
    """Verify that the health check endpoint is functional."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"


def test_unauthorized_access(test_client):
    """Verify that protected API routes correctly return 401/403 for unauthenticated users."""
    protected_routes = [
        "/api/admin/stats",
        "/api/admin/doctors",
        "/api/admin/patients",
        "/api/doctor/appointments",
        "/api/my-appointments",
        "/api/profile",
    ]
    for route in protected_routes:
        response = test_client.get(route)
        # Flask-Security may redirect (302) to login page or return 401/403
        assert response.status_code in [302, 401, 403]
