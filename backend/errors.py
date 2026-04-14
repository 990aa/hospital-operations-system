"""Consistent RFC 7807-style error helpers."""

from flask import jsonify, has_request_context, g


def _json_safe(value):
    """Recursively convert values to JSON-safe primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return str(value)


def problem(status: int, title: str, detail: str, **extra):
    """Return a Problem Details JSON response tuple."""
    request_id = None
    if has_request_context():
        request_id = getattr(g, "request_id", None)

    body = {
        "type": f"https://hospital-operations-system.example/errors/{title.lower().replace(' ', '-')}",
        "title": title,
        "status": status,
        "detail": detail,
        "message": detail,
        "request_id": request_id,
        **_json_safe(extra),
    }
    return jsonify(body), status
