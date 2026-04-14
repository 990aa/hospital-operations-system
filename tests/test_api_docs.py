"""OpenAPI documentation endpoint tests."""


def test_openapi_spec_available(test_client):
    response = test_client.get("/api/openapi.json")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["openapi"].startswith("3.")


def test_swagger_ui_available(test_client):
    response = test_client.get("/api/docs", follow_redirects=True)
    assert response.status_code == 200
    assert b"swagger" in response.data.lower()


def test_meta_ping_endpoint_available(test_client):
    response = test_client.get("/api/meta/ping")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "hospital-operations-system"
