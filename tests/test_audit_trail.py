"""Audit trail tests for admin-originated writes."""

import uuid

from models.database import AuditLog


def test_admin_writes_are_captured_in_audit_log(admin_token, test_client):
    dept_name = f"Audit-{uuid.uuid4().hex[:8]}"
    response = admin_token.post(
        "/api/departments",
        json={"name": dept_name, "description": "Created for audit validation"},
    )
    assert response.status_code == 201

    with test_client.application.app_context():
        rows = (
            AuditLog.query.filter_by(action="create", entity_type="Department")
            .order_by(AuditLog.id.desc())
            .all()
        )

    assert rows
    latest = rows[0]
    assert latest.actor_username == "admin"
    assert latest.path == "/api/departments"
    assert latest.request_id is not None


def test_admin_can_list_audit_logs(admin_token):
    response = admin_token.get(
        "/api/admin/audit-logs?action=create&entity_type=Department"
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert "entries" in payload
    assert "count" in payload
    assert isinstance(payload["entries"], list)


def test_non_admin_cannot_access_audit_logs(patient_token):
    response = patient_token.get("/api/admin/audit-logs")
    assert response.status_code in [302, 401, 403]
