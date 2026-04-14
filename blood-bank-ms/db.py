"""Database connection helpers for the Blood Bank Management System."""

import sqlite3

DB_NAME: str = "bloodbank.db"


def get_db_connection(db_name: str | None = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection.

    Args:
        db_name: Optional database file path. When omitted, ``DB_NAME`` is used.

    Returns:
        A configured ``sqlite3.Connection`` with row dictionaries and required
        PRAGMA settings enabled.
    """
    target_db = db_name or DB_NAME
    conn = sqlite3.connect(target_db)

    # Return rows as mapping-like objects (row["column_name"]).
    conn.row_factory = sqlite3.Row

    # Enforce referential integrity and allow trigger-to-trigger cascades.
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA recursive_triggers = ON;")
    return conn
