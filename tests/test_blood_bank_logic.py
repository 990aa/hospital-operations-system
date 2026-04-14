"""Property-based hardening tests for blood bank donation processing."""

import os
import sys
import importlib.util
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BLOOD_BANK_ROOT = PROJECT_ROOT / "blood-bank-ms"
BLOOD_BANK_APP_ROOT = BLOOD_BANK_ROOT / "app"
for import_path in (BLOOD_BANK_ROOT, BLOOD_BANK_APP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import db as bb_db  # type: ignore[import-not-found]
from db_init import init_db  # type: ignore[import-not-found]

_LOGIC_PATH = BLOOD_BANK_APP_ROOT / "logic.py"
_LOGIC_SPEC = importlib.util.spec_from_file_location("blood_bank_logic_test", _LOGIC_PATH)
if _LOGIC_SPEC is None or _LOGIC_SPEC.loader is None:
    raise RuntimeError(f"Unable to load blood-bank logic module from {_LOGIC_PATH}")
_LOGIC_MODULE = importlib.util.module_from_spec(_LOGIC_SPEC)
_LOGIC_SPEC.loader.exec_module(_LOGIC_MODULE)
process_donation = _LOGIC_MODULE.process_donation


@pytest.fixture()
def setup_bb_db(tmp_path):
    test_db = tmp_path / "bb_hypothesis.db"
    original = bb_db.DB_NAME
    bb_db.DB_NAME = str(test_db)
    init_db()

    yield str(test_db)

    bb_db.DB_NAME = original
    if os.path.exists(test_db):
        os.remove(test_db)


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(quantity=st.floats(min_value=0.001, max_value=10000, allow_nan=False, allow_infinity=False))
def test_donation_always_creates_bag_or_fails_cleanly(quantity, setup_bb_db):
    conn = bb_db.get_db_connection()
    conn.execute(
        "INSERT INTO DONOR (name, blood_group, phone) VALUES (?, ?, ?)",
        ("Property Donor", "A+", "9001230000"),
    )
    conn.commit()
    donor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    ok, msg = process_donation(donor_id=donor_id, quantity_ml=float(quantity))
    assert isinstance(ok, bool)
    assert isinstance(msg, str)
    assert len(msg) > 0
