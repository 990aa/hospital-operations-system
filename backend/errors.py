"""Consistent RFC 7807-style error helpers."""

from flask import jsonify


def problem(status: int, title: str, detail: str, **extra):
    """Return a Problem Details JSON response tuple."""
    body = {
        "type": f"https://hospital-operations-system.example/errors/{title.lower().replace(' ', '-')}",
        "title": title,
        "status": status,
        "detail": detail,
        "message": detail,
        **extra,
    }
    return jsonify(body), status
