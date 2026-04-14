"""Additional model-level tests for password and audit helper branches."""

from datetime import datetime

from models.database import AuditLog, User, _audit_actor_context, _json_default


def _make_user(password: str) -> User:
    return User(
        username="model_user",
        email="model@example.com",
        phone="1234567890",
        password=password,
        active=True,
        fs_uniquifier="model_user_uniq",
        name="Model User",
    )


def test_user_check_password_plaintext_fallback_path():
    user = _make_user("plaintext123")
    assert user.check_password("plaintext123") is True
    assert user.check_password("wrong") is False


def test_user_check_password_argon2_mismatch_branch():
    user = _make_user("temp")
    user.set_password("secure-password")
    assert user.check_password("incorrect-password") is False


def test_audit_log_to_dict_parses_and_falls_back_for_changes():
    good = AuditLog(action="create", entity_type="Department", changes='{"name": "ER"}')
    assert good.to_dict()["changes"]["name"] == "ER"

    bad = AuditLog(action="update", entity_type="Doctor", changes="{bad-json")
    assert bad.to_dict()["changes"] == "{bad-json"


def test_json_default_supports_isoformat_and_string_fallback():
    now = datetime.now()
    assert _json_default(now) == now.isoformat()

    class Sample:
        pass

    assert _json_default(Sample())


def test_audit_actor_context_without_request_context():
    assert _audit_actor_context() is None
