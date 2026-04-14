"""Database schema initializer for the Blood Bank Management System."""

import os
import sqlite3

import db

# Standalone runs import from app.settings, while integrated HOS runs can have
# a top-level module named "app" that is not this package.
try:
    from app.settings import EXPIRING_SOON_DAYS
except (ImportError, ModuleNotFoundError):
    from settings import EXPIRING_SOON_DAYS


def init_db(db_name: str | None = None) -> None:
    """Create a fresh database with schema, constraints, triggers, and views.

    Args:
        db_name: Optional database file path. When omitted, ``db.DB_NAME``
            is used.

    The initializer removes an existing database file at the target path,
    recreates the full schema, and seeds all static domain tables.
    """
    target_db_name = db_name or db.DB_NAME

    if os.path.exists(target_db_name):
        os.remove(target_db_name)

    conn = sqlite3.connect(target_db_name)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA recursive_triggers = ON;")

    # Create domain lookup/master tables first so foreign key targets exist.

    cursor.execute("""
    CREATE TABLE BLOOD_GROUP_MASTER (
        blood_group TEXT PRIMARY KEY
    );
    """)
    for bg in ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"):
        cursor.execute("INSERT INTO BLOOD_GROUP_MASTER VALUES (?)", (bg,))

    cursor.execute("""
    CREATE TABLE URGENCY_LEVEL_MASTER (
        urgency_level TEXT PRIMARY KEY
    );
    """)
    for ul in ("Normal", "Critical"):
        cursor.execute("INSERT INTO URGENCY_LEVEL_MASTER VALUES (?)", (ul,))

    cursor.execute("""
    CREATE TABLE BAG_STATUS_MASTER (
        status TEXT PRIMARY KEY
    );
    """)
    for s in ("Available", "Empty", "Expired", "Quarantined"):
        cursor.execute("INSERT INTO BAG_STATUS_MASTER VALUES (?)", (s,))

    cursor.execute("""
    CREATE TABLE REQUEST_STATUS_MASTER (
        status TEXT PRIMARY KEY
    );
    """)
    for s in ("Pending", "Partially Fulfilled", "Fulfilled", "Cancelled"):
        cursor.execute("INSERT INTO REQUEST_STATUS_MASTER VALUES (?)", (s,))

    cursor.execute("""
    CREATE TABLE COMPONENT_MASTER (
        component_type  TEXT PRIMARY KEY,
        shelf_life_days INTEGER NOT NULL
    );
    """)
    for ct, sl in [
        ("Whole Blood", 42),
        ("Red Blood Cells", 42),
        ("Platelets", 5),
        ("Plasma", 365),
        ("Cryoprecipitate", 365),
    ]:
        cursor.execute("INSERT INTO COMPONENT_MASTER VALUES (?, ?)", (ct, sl))

    # Compatibility matrix controls medically valid donor/recipient pairs.
    cursor.execute("""
    CREATE TABLE COMPATIBILITY_MATRIX (
        recipient_group  TEXT NOT NULL,
        donor_group      TEXT NOT NULL,
        preference_rank  INTEGER NOT NULL,
        PRIMARY KEY (recipient_group, donor_group),
        FOREIGN KEY (recipient_group) REFERENCES BLOOD_GROUP_MASTER(blood_group),
        FOREIGN KEY (donor_group)     REFERENCES BLOOD_GROUP_MASTER(blood_group)
    );
    """)
    compat_data = [
        # Lower preference_rank means "consume first" during allocation.
        ("A+", "A+", 1),
        ("A+", "A-", 2),
        ("A+", "O+", 3),
        ("A+", "O-", 4),
        ("A-", "A-", 1),
        ("A-", "O-", 2),
        ("B+", "B+", 1),
        ("B+", "B-", 2),
        ("B+", "O+", 3),
        ("B+", "O-", 4),
        ("B-", "B-", 1),
        ("B-", "O-", 2),
        ("AB+", "AB+", 1),
        ("AB+", "AB-", 2),
        ("AB+", "A+", 3),
        ("AB+", "A-", 4),
        ("AB+", "B+", 5),
        ("AB+", "B-", 6),
        ("AB+", "O+", 7),
        ("AB+", "O-", 8),
        ("AB-", "AB-", 1),
        ("AB-", "A-", 2),
        ("AB-", "B-", 3),
        ("AB-", "O-", 4),
        ("O+", "O+", 1),
        ("O+", "O-", 2),
        ("O-", "O-", 1),
    ]
    cursor.executemany("INSERT INTO COMPATIBILITY_MATRIX VALUES (?, ?, ?)", compat_data)

    # Create operational tables used by the application runtime.

    # Donor registry uses soft-delete via the is_active flag.
    cursor.execute("""
    CREATE TABLE DONOR (
        donor_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name               TEXT    NOT NULL,
        blood_group        TEXT    NOT NULL,
        phone              TEXT,
        email              TEXT,
        last_donation_date DATE,
        is_active          INTEGER DEFAULT 1,
        FOREIGN KEY (blood_group) REFERENCES BLOOD_GROUP_MASTER(blood_group)
    );
    """)

    # Hospital/recipient registry also uses soft-delete.
    cursor.execute("""
    CREATE TABLE RECIPIENT (
        recipient_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        hospital_name TEXT NOT NULL,
        contact_info  TEXT,
        is_active     INTEGER DEFAULT 1
    );
    """)

    # 3. DONATION_LOG
    cursor.execute("""
    CREATE TABLE DONATION_LOG (
        donation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        donor_id      INTEGER NOT NULL,
        donation_date DATE    NOT NULL,
        quantity_ml   REAL    NOT NULL,
        FOREIGN KEY (donor_id) REFERENCES DONOR(donor_id)
    );
    """)

    # Inventory bag table tracks per-bag volume and component metadata.
    cursor.execute("""
    CREATE TABLE BLOOD_BAG (
        bag_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        donation_id       INTEGER NOT NULL,
        blood_group       TEXT    NOT NULL,
        component_type    TEXT    NOT NULL DEFAULT 'Whole Blood',
        collection_date   DATE    NOT NULL,
        expiry_date       DATE    NOT NULL,
        initial_volume_ml REAL    NOT NULL,
        current_volume_ml REAL    NOT NULL,
        status            TEXT    DEFAULT 'Available',
        FOREIGN KEY (donation_id)    REFERENCES DONATION_LOG(donation_id),
        FOREIGN KEY (blood_group)    REFERENCES BLOOD_GROUP_MASTER(blood_group),
        FOREIGN KEY (component_type) REFERENCES COMPONENT_MASTER(component_type),
        FOREIGN KEY (status)         REFERENCES BAG_STATUS_MASTER(status)
    );
    """)

    # Request table stores requested and allocated amounts for partial fills.
    cursor.execute("""
    CREATE TABLE TRANSFUSION_REQ (
        req_id                INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_id          INTEGER NOT NULL,
        requested_group       TEXT    NOT NULL,
        requested_component   TEXT    NOT NULL DEFAULT 'Whole Blood',
        quantity_ml           REAL    NOT NULL,
        quantity_allocated_ml REAL    DEFAULT 0,
        urgency_level         TEXT    DEFAULT 'Normal',
        req_date              DATE    NOT NULL,
        status                TEXT    DEFAULT 'Pending',
        FOREIGN KEY (recipient_id)        REFERENCES RECIPIENT(recipient_id),
        FOREIGN KEY (requested_group)     REFERENCES BLOOD_GROUP_MASTER(blood_group),
        FOREIGN KEY (requested_component) REFERENCES COMPONENT_MASTER(component_type),
        FOREIGN KEY (urgency_level)       REFERENCES URGENCY_LEVEL_MASTER(urgency_level),
        FOREIGN KEY (status)              REFERENCES REQUEST_STATUS_MASTER(status)
    );
    """)

    # 6. FULFILLMENT_LOG
    cursor.execute("""
    CREATE TABLE FULFILLMENT_LOG (
        fulfillment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        req_id               INTEGER NOT NULL,
        bag_id               INTEGER NOT NULL,
        quantity_allocated_ml REAL    NOT NULL,
        fulfillment_date     DATE    DEFAULT (DATE('now')),
        FOREIGN KEY (req_id) REFERENCES TRANSFUSION_REQ(req_id),
        FOREIGN KEY (bag_id) REFERENCES BLOOD_BAG(bag_id)
    );
    """)

    # Audit trail table stores trigger-generated forensic change history.
    cursor.execute("""
    CREATE TABLE AUDIT_LOG (
        log_id       INTEGER  PRIMARY KEY AUTOINCREMENT,
        action_type  TEXT     NOT NULL,
        table_name   TEXT     NOT NULL,
        record_id    INTEGER,
        old_value    TEXT,
        new_value    TEXT,
        timestamp    DATETIME DEFAULT (DATETIME('now')),
        performed_by TEXT     DEFAULT 'SYSTEM'
    );
    """)

    # Indexes accelerate frequent filter and ordering.
    cursor.execute(
        "CREATE INDEX idx_bag_status_expiry ON BLOOD_BAG(status, expiry_date);"
    )
    cursor.execute(
        "CREATE INDEX idx_bag_component_group ON BLOOD_BAG(component_type, blood_group, status);"
    )
    cursor.execute(
        "CREATE INDEX idx_req_status_urgency ON TRANSFUSION_REQ(status, urgency_level);"
    )
    cursor.execute(
        "CREATE INDEX idx_req_recipient_status ON TRANSFUSION_REQ(recipient_id, status);"
    )
    cursor.execute("CREATE INDEX idx_donor_active ON DONOR(is_active);")
    cursor.execute("CREATE INDEX idx_recipient_active ON RECIPIENT(is_active);")
    cursor.execute(
        "CREATE INDEX idx_fulfillment_date ON FULFILLMENT_LOG(fulfillment_date);"
    )

    # Triggers enforce integrity and produce automatic audit records.

    # Mark a bag as Empty when deducted volume reaches zero or below.
    cursor.execute("""
    CREATE TRIGGER trg_auto_expire_bag
    AFTER UPDATE OF current_volume_ml ON BLOOD_BAG
    WHEN NEW.current_volume_ml <= 0 AND NEW.status != 'Empty'
    BEGIN
        UPDATE BLOOD_BAG SET status = 'Empty' WHERE bag_id = NEW.bag_id;
    END;
    """)

    # Block donation inserts that violate the minimum donation interval.
    cursor.execute("""
    CREATE TRIGGER trg_donation_safety_lock
    BEFORE INSERT ON DONATION_LOG
    BEGIN
        SELECT CASE
            WHEN (SELECT last_donation_date FROM DONOR
                  WHERE donor_id = NEW.donor_id) IS NOT NULL
             AND julianday(NEW.donation_date)
               - julianday((SELECT last_donation_date FROM DONOR
                            WHERE donor_id = NEW.donor_id)) < 56
            THEN RAISE(ABORT,
                 'DONATION_SAFETY: Donor must wait at least 56 days between donations')
        END;
    END;
    """)

    # Block fulfillment inserts that exceed current bag volume.
    cursor.execute("""
    CREATE TRIGGER trg_fulfillment_volume_guard
    BEFORE INSERT ON FULFILLMENT_LOG
    BEGIN
        SELECT CASE
            WHEN NEW.quantity_allocated_ml >
                 (SELECT current_volume_ml FROM BLOOD_BAG
                  WHERE bag_id = NEW.bag_id)
            THEN RAISE(ABORT,
                 'VOLUME_GUARD: Allocated quantity exceeds available bag volume')
        END;
    END;
    """)

    # Recompute request allocated amount and status after each fulfillment.
    cursor.execute("""
    CREATE TRIGGER trg_update_req_allocated
    AFTER INSERT ON FULFILLMENT_LOG
    BEGIN
        UPDATE TRANSFUSION_REQ
        SET quantity_allocated_ml = (
                SELECT COALESCE(SUM(quantity_allocated_ml), 0)
                FROM FULFILLMENT_LOG WHERE req_id = NEW.req_id),
            status = CASE
                WHEN (SELECT COALESCE(SUM(quantity_allocated_ml), 0)
                      FROM FULFILLMENT_LOG WHERE req_id = NEW.req_id)
                     >= quantity_ml
                THEN 'Fulfilled'
                WHEN (SELECT COALESCE(SUM(quantity_allocated_ml), 0)
                      FROM FULFILLMENT_LOG WHERE req_id = NEW.req_id) > 0
                THEN 'Partially Fulfilled'
                ELSE status
            END
        WHERE req_id = NEW.req_id;
    END;
    """)

    # Audit triggers capture inserts/updates for sensitive transactional tables.

    cursor.execute("""
    CREATE TRIGGER trg_audit_bag_insert
    AFTER INSERT ON BLOOD_BAG
    BEGIN
        INSERT INTO AUDIT_LOG(action_type, table_name, record_id, new_value)
        VALUES('INSERT', 'BLOOD_BAG', NEW.bag_id,
               'group='||NEW.blood_group||', component='||NEW.component_type
               ||', vol='||NEW.initial_volume_ml);
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER trg_audit_bag_update
    AFTER UPDATE ON BLOOD_BAG
    BEGIN
        INSERT INTO AUDIT_LOG(action_type, table_name, record_id, old_value, new_value)
        VALUES('UPDATE', 'BLOOD_BAG', OLD.bag_id,
               'status='||OLD.status||', vol='||OLD.current_volume_ml,
               'status='||NEW.status||', vol='||NEW.current_volume_ml);
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER trg_audit_req_insert
    AFTER INSERT ON TRANSFUSION_REQ
    BEGIN
        INSERT INTO AUDIT_LOG(action_type, table_name, record_id, new_value)
        VALUES('INSERT', 'TRANSFUSION_REQ', NEW.req_id,
               'group='||NEW.requested_group||', component='||NEW.requested_component
               ||', qty='||NEW.quantity_ml||', urgency='||NEW.urgency_level);
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER trg_audit_req_update
    AFTER UPDATE ON TRANSFUSION_REQ
    BEGIN
        INSERT INTO AUDIT_LOG(action_type, table_name, record_id, old_value, new_value)
        VALUES('UPDATE', 'TRANSFUSION_REQ', OLD.req_id,
               'status='||OLD.status||', allocated='||OLD.quantity_allocated_ml,
               'status='||NEW.status||', allocated='||NEW.quantity_allocated_ml);
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER trg_audit_donation_insert
    AFTER INSERT ON DONATION_LOG
    BEGIN
        INSERT INTO AUDIT_LOG(action_type, table_name, record_id, new_value)
        VALUES('INSERT', 'DONATION_LOG', NEW.donation_id,
               'donor='||NEW.donor_id||', qty='||NEW.quantity_ml
               ||', date='||NEW.donation_date);
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER trg_audit_fulfillment_insert
    AFTER INSERT ON FULFILLMENT_LOG
    BEGIN
        INSERT INTO AUDIT_LOG(action_type, table_name, record_id, new_value)
        VALUES('INSERT', 'FULFILLMENT_LOG', NEW.fulfillment_id,
               'req='||NEW.req_id||', bag='||NEW.bag_id
               ||', qty='||NEW.quantity_allocated_ml);
    END;
    """)

    # Dashboard views centralize common reporting queries.

    cursor.execute("""
    CREATE VIEW vw_inventory_summary AS
    SELECT blood_group,
           component_type,
           COUNT(*)               AS bag_count,
           SUM(current_volume_ml) AS total_volume_ml
    FROM   BLOOD_BAG
    WHERE  status = 'Available'
    GROUP  BY blood_group, component_type;
    """)

    cursor.execute("""
    CREATE VIEW vw_critical_pending AS
    SELECT tr.req_id,
           tr.requested_group,
           tr.requested_component,
           tr.quantity_ml,
           tr.quantity_allocated_ml,
           (tr.quantity_ml - tr.quantity_allocated_ml) AS remaining_ml,
           tr.urgency_level,
           tr.status,
           r.name          AS recipient_name,
           r.hospital_name
    FROM   TRANSFUSION_REQ tr
    JOIN   RECIPIENT r ON tr.recipient_id = r.recipient_id
    WHERE  tr.urgency_level = 'Critical'
            AND  r.is_active = 1
      AND  tr.status IN ('Pending', 'Partially Fulfilled');
    """)

    cursor.execute(
        f"""
    CREATE VIEW vw_expiring_soon AS
    SELECT bag_id,
           blood_group,
           component_type,
           current_volume_ml,
           expiry_date,
           CAST(julianday(expiry_date) - julianday('now') AS INTEGER) AS days_until_expiry
    FROM   BLOOD_BAG
    WHERE  status = 'Available'
      AND  julianday(expiry_date) - julianday('now') <= {int(EXPIRING_SOON_DAYS)}
      AND  julianday(expiry_date) - julianday('now') >= 0
    ORDER  BY expiry_date ASC;
    """
    )

    conn.commit()
    conn.close()
    print(
        "Database initialized: triggers, views, audit trail, "
        "domain normalization, component tracking."
    )


if __name__ == "__main__":
    init_db()
