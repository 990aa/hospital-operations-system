"""One-time password migration to Argon2 for known seeded/demo users."""

from __future__ import annotations

from flask_security.utils import verify_password

from models.database import db, User

DEMO_DEFAULT_PASSWORDS = {
    "admin": "admin",
    "bbstaff": "bbstaff",
}


def _candidate_passwords_for_user(user: User) -> list[str]:
    candidates = []
    if user.username in DEMO_DEFAULT_PASSWORDS:
        candidates.append(DEMO_DEFAULT_PASSWORDS[user.username])
    # scripts/seed_db.py uses this default for demo doctors/patients.
    candidates.append("password")
    # tests often create username=password fixtures.
    candidates.append(user.username)

    deduped = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def migrate_passwords(app) -> int:
    """Re-hash known legacy/demo passwords to Argon2 when possible."""
    migrated = 0

    with app.app_context():
        users = User.query.all()
        for user in users:
            if not user.password or user.password.startswith("$argon2"):
                continue

            for candidate in _candidate_passwords_for_user(user):
                verified = False
                if user.password == candidate:
                    verified = True
                else:
                    try:
                        verified = bool(verify_password(candidate, user.password))
                    except Exception:
                        verified = False

                if verified:
                    user.set_password(candidate)
                    migrated += 1
                    break

        if migrated:
            db.session.commit()

    return migrated


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    count = migrate_passwords(app)
    print(f"Migrated {count} users to Argon2 password hashes.")
