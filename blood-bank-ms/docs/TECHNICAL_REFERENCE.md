# Blood Bank Management System — Technical Implementation Reference

This document provides exhaustive technical detail on every aspect of the Blood Bank Management System. It is intended as a reference for understanding the architectural decisions, database engineering strategies, algorithmic logic, and implementation patterns used throughout the project. Any question about the project's internals should be answerable from this document.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Technology Stack Rationale](#2-technology-stack-rationale)
3. [Database Architecture](#3-database-architecture)
4. [Domain Normalisation Strategy](#4-domain-normalisation-strategy)
5. [Trigger Engineering](#5-trigger-engineering)
6. [SQL View Design](#6-sql-view-design)
7. [Audit Trail Architecture](#7-audit-trail-architecture)
8. [Component Tracking System](#8-component-tracking-system)
9. [Soft Delete Pattern](#9-soft-delete-pattern)
10. [Smart Allocation Algorithm](#10-smart-allocation-algorithm)
11. [Cross-Match Compatibility Scoring](#11-cross-match-compatibility-scoring)
12. [Partial Fulfillment Mechanism](#12-partial-fulfillment-mechanism)
13. [Predictive Shortage Alert Engine](#13-predictive-shortage-alert-engine)
14. [Donor Loyalty Module](#14-donor-loyalty-module)
15. [Flask Application Layer](#15-flask-application-layer)
16. [Connection Management and PRAGMAs](#16-connection-management-and-pragmas)
17. [Schema Initialisation Strategy](#17-schema-initialisation-strategy)
18. [Frontend Architecture](#18-frontend-architecture)
19. [Error Handling Strategy](#19-error-handling-strategy)
20. [Data Flow Diagrams](#20-data-flow-diagrams)
21. [Design Decisions and Trade-offs](#21-design-decisions-and-trade-offs)

---

## 1. Architecture Overview

The system follows a **three-tier architecture**:

```
┌─────────────────────────────────────────────────┐
│  PRESENTATION LAYER                             │
│  Jinja2 Templates + Bootstrap 5                 │
│  (base.html, home.html, donor.html,             │
│   hospital.html, audit.html)                    │
├─────────────────────────────────────────────────┤
│  APPLICATION LAYER                              │
│  Flask (main.py) + Business Logic (app/logic.py)│
│  Routes: /, /donor, /hospital, /audit,          │
│          /allocate_all                           │
├─────────────────────────────────────────────────┤
│  DATA LAYER                                     │
│  SQLite3 (bloodbank.db)                         │
│  13 Tables, 3 Views, 10 Triggers                │
│  Connection helper: db.py                       │
│  Schema initialiser: db_init.py                 │
└─────────────────────────────────────────────────┘
```

**Key architectural principle:** Business rules that involve data integrity are enforced at the database level via triggers and foreign keys, not just in application code. This means even direct SQL access to the database cannot violate constraints such as the 56-day donation interval, volume over-allocation, or invalid blood group values.

---

## 2. Technology Stack Rationale

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.14+ | Native sqlite3 module eliminates ORM dependency. Dynamic typing enables rapid prototyping while type annotations (ty check) ensure correctness. |
| **Web Framework** | Flask 3.1 | Micro-framework allows raw SQL queries (demonstrating DBMS concepts directly) without ORM abstraction hiding the SQL. Jinja2 templating is built-in. |
| **Database** | SQLite 3 | Zero-configuration, file-based RDBMS with full SQL support including triggers, views, foreign keys, and recursive triggers. Ideal for single-user academic projects. |
| **Frontend** | Bootstrap 5 + Bootstrap Icons | Responsive CSS framework with professional icon library (SVG-based). No JavaScript frameworks needed. |
| **Package Manager** | uv | Modern, fast Python package manager. Manages virtual environment and dependency resolution through pyproject.toml. |
| **Linting** | ruff | Fastest Python linter/formatter. Replaces flake8, isort, and black in a single tool. |
| **Type Checking** | ty | Strict type analysis for Python. Catches type errors without runtime overhead. |
| **Testing** | pytest | Industry-standard Python test framework with fixture support, parameterisation, and detailed failure reports. |

### Why Not an ORM?

The project deliberately avoids ORMs (SQLAlchemy, Django ORM) because:
1. The goal is to demonstrate raw SQL proficiency for a DBMS course.
2. Triggers, views, and complex JOINs are more naturally expressed in SQL.
3. The COMPATIBILITY_MATRIX and its JOIN-based allocation query would be awkward in ORM syntax.
4. Direct SQL makes the trigger/view/constraint interactions transparent for evaluation.

---

## 3. Database Architecture

### 3.1 Schema Summary

The database contains 13 tables organised into three categories:

**Master/Lookup Tables (6):**
- BLOOD_GROUP_MASTER — 8 rows (A+, A-, B+, B-, AB+, AB-, O+, O-)
- URGENCY_LEVEL_MASTER — 2 rows (Normal, Critical)
- BAG_STATUS_MASTER — 4 rows (Available, Empty, Expired, Quarantined)
- REQUEST_STATUS_MASTER — 4 rows (Pending, Partially Fulfilled, Fulfilled, Cancelled)
- COMPONENT_MASTER — 5 rows with shelf_life_days column
- COMPATIBILITY_MATRIX — 27 rows with preference_rank column

**Core Operational Tables (6):**
- DONOR — donor registry with soft-delete flag
- RECIPIENT — hospital/recipient registry with soft-delete flag
- DONATION_LOG — event log of each donation
- BLOOD_BAG — inventory tracking per physical bag
- TRANSFUSION_REQ — hospital blood requests with partial allocation tracking
- FULFILLMENT_LOG — N:M join between requests and bags

**System Table (1):**
- AUDIT_LOG — forensic trail of all INSERT/UPDATE operations

### 3.2 Normalisation Level

The schema is in **Third Normal Form (3NF)**:

- **1NF:** All columns contain atomic values. No repeating groups.
- **2NF:** All non-key columns depend on the entire primary key. COMPATIBILITY_MATRIX has a composite PK (recipient_group, donor_group) and preference_rank depends on both.
- **3NF:** No transitive dependencies. Blood group labels are not stored redundantly — DONOR.blood_group, BLOOD_BAG.blood_group, and TRANSFUSION_REQ.requested_group all reference BLOOD_GROUP_MASTER via FK.

### 3.3 Foreign Key Map

Every FK relationship enforces referential integrity:

```
DONOR.blood_group                  → BLOOD_GROUP_MASTER.blood_group
BLOOD_BAG.blood_group              → BLOOD_GROUP_MASTER.blood_group
BLOOD_BAG.component_type           → COMPONENT_MASTER.component_type
BLOOD_BAG.status                   → BAG_STATUS_MASTER.status
BLOOD_BAG.donation_id              → DONATION_LOG.donation_id
TRANSFUSION_REQ.requested_group    → BLOOD_GROUP_MASTER.blood_group
TRANSFUSION_REQ.requested_component→ COMPONENT_MASTER.component_type
TRANSFUSION_REQ.urgency_level      → URGENCY_LEVEL_MASTER.urgency_level
TRANSFUSION_REQ.status             → REQUEST_STATUS_MASTER.status
TRANSFUSION_REQ.recipient_id       → RECIPIENT.recipient_id
DONATION_LOG.donor_id              → DONOR.donor_id
FULFILLMENT_LOG.req_id             → TRANSFUSION_REQ.req_id
FULFILLMENT_LOG.bag_id             → BLOOD_BAG.bag_id
COMPATIBILITY_MATRIX.recipient_group → BLOOD_GROUP_MASTER.blood_group
COMPATIBILITY_MATRIX.donor_group   → BLOOD_GROUP_MASTER.blood_group
```

### 3.4 Data Types Strategy

SQLite uses dynamic typing, but the schema uses type declarations for documentation and intent:

- **INTEGER PRIMARY KEY AUTOINCREMENT** for all surrogate keys — guarantees monotonically increasing unique IDs.
- **TEXT** for all string columns — SQLite stores strings as UTF-8 regardless of declared type.
- **REAL** for volume columns (quantity_ml, current_volume_ml, initial_volume_ml) — allows fractional ml tracking without floating-point issues at this scale.
- **DATE** for date columns — stored as ISO-8601 text strings (YYYY-MM-DD) which sort lexicographically and work with julianday().
- **DATETIME DEFAULT (DATETIME('now'))** for AUDIT_LOG.timestamp — automatically captures the exact moment of the audit event.

---

## 4. Domain Normalisation Strategy

### 4.1 Problem

Without normalisation, free-text fields allow inconsistencies: "A positive", "A+", "a+", "Apositive" would all be valid entries for the same blood group. Similarly, urgency could be "Critical", "Urgent", "CRITICAL", "critical" — all meaning the same thing but causing query failures.

### 4.2 Solution

Six master tables serve as **controlled vocabularies**. Every table that references a domain value uses a FOREIGN KEY to the master table. This means:

1. **Invalid values are rejected at INSERT/UPDATE time** — the FK constraint fails before data is written.
2. **Application dropdowns are populated from master tables** — ensuring the UI and database stay synchronised.
3. **Queries are reliable** — WHERE blood_group = 'A+' will always find all A+ records because no misspellings can exist.

### 4.3 COMPONENT_MASTER Design

This table is notable because it stores both the component type name AND its shelf life:

| component_type | shelf_life_days |
|----------------|-----------------|
| Whole Blood | 42 |
| Red Blood Cells | 42 |
| Platelets | 5 |
| Plasma | 365 |
| Cryoprecipitate | 365 |

The shelf_life_days column is queried during donation processing to calculate the expiry date for each bag. This avoids hardcoding shelf lives in application code — adding a new component type is a single INSERT into COMPONENT_MASTER.

### 4.4 COMPATIBILITY_MATRIX Design

The 27-row matrix encodes ABO/Rh blood group compatibility with a preference ranking:

**Design decisions:**
- **Composite primary key** (recipient_group, donor_group) prevents duplicate entries.
- **Both columns are FKs to BLOOD_GROUP_MASTER** ensuring only valid blood groups appear.
- **preference_rank (INTEGER)** determines allocation order: rank 1 = exact match (use first), higher ranks = increasingly distant compatibility (use only when needed).
- **27 rows, not 64:** Only medically valid combinations are stored. Invalid pairings (e.g., A+ donor for B- recipient) have no row, so the allocation JOIN naturally excludes them.

The full matrix:

| Recipient | Donors (by preference) |
|-----------|----------------------|
| A+ | A+(1), A-(2), O+(3), O-(4) |
| A- | A-(1), O-(2) |
| B+ | B+(1), B-(2), O+(3), O-(4) |
| B- | B-(1), O-(2) |
| AB+ | AB+(1), AB-(2), A+(3), A-(4), B+(5), B-(6), O+(7), O-(8) |
| AB- | AB-(1), A-(2), B-(3), O-(4) |
| O+ | O+(1), O-(2) |
| O- | O-(1) |

AB+ is the universal recipient (8 compatible donors, all groups). O- is the universal donor (compatible with all 8 recipients but always at the lowest preference rank except when donating to O- patients).

---

## 5. Trigger Engineering

### 5.1 Overview

The database uses 10 triggers: 4 business-rule triggers and 6 audit-trail triggers.

### 5.2 trg_auto_expire_bag

**Type:** AFTER UPDATE OF current_volume_ml ON BLOOD_BAG
**Condition:** NEW.current_volume_ml <= 0 AND NEW.status != 'Empty'
**Action:** UPDATE BLOOD_BAG SET status = 'Empty' WHERE bag_id = NEW.bag_id

**Technical details:**
- Uses AFTER UPDATE (not BEFORE) because it needs the volume change to be committed first.
- The condition `NEW.status != 'Empty'` prevents infinite recursion — without it, the status update would trigger trg_audit_bag_update, which would fire again.
- Requires `PRAGMA recursive_triggers = ON` because the status UPDATE fires the audit trigger trg_audit_bag_update, which is a trigger firing from within a trigger context.

**Cascade chain:**
```
Application UPDATEs bag volume → trg_auto_expire_bag fires
  → UPDATEs status to Empty → trg_audit_bag_update fires
    → INSERTs into AUDIT_LOG (records the status change)
```

### 5.3 trg_donation_safety_lock

**Type:** BEFORE INSERT ON DONATION_LOG
**Action:** RAISE(ABORT, 'DONATION_SAFETY: ...')

**Technical details:**
- Uses BEFORE INSERT to prevent the row from ever being inserted.
- Queries DONOR.last_donation_date for the donor_id being inserted.
- Uses julianday() for date arithmetic — julianday(NEW.donation_date) minus julianday(last_donation_date) gives the exact number of days between donations.
- The threshold is strictly < 56 (i.e., exactly 56 days is allowed).
- RAISE(ABORT) rolls back only the current statement, not the entire transaction.

**Dual enforcement strategy:**
The application layer (process_donation in logic.py) also checks this rule and provides a user-friendly error message. The trigger serves as a safety net — even if someone inserts directly via SQL, the constraint holds. This is a defence-in-depth pattern.

### 5.4 trg_fulfillment_volume_guard

**Type:** BEFORE INSERT ON FULFILLMENT_LOG
**Action:** RAISE(ABORT, 'VOLUME_GUARD: ...')

**Technical details:**
- Compares NEW.quantity_allocated_ml against the bag's current current_volume_ml.
- This is critical because the allocation algorithm inserts the FULFILLMENT_LOG record BEFORE deducting the volume from the bag. The trigger ensures the deduction will be valid.
- Without this trigger, a race condition or bug could allocate 500ml from a 200ml bag.

### 5.5 trg_update_req_allocated

**Type:** AFTER INSERT ON FULFILLMENT_LOG
**Action:** UPDATE TRANSFUSION_REQ

**Technical details:**
- Recalculates quantity_allocated_ml by summing ALL FULFILLMENT_LOG entries for the request (not just adding the new one). This ensures accuracy even if fulfillment records are modified.
- Sets status using a CASE expression:
  - Sum >= quantity_ml → 'Fulfilled'
  - Sum > 0 → 'Partially Fulfilled'
  - Otherwise → keeps current status
- This trigger is the mechanism that enables partial fulfillment without any application-level status management.

### 5.6 Audit Trail Triggers (6)

Six triggers cover four tables:

| Trigger | Table | Event | What is Logged |
|---------|-------|-------|----------------|
| trg_audit_bag_insert | BLOOD_BAG | AFTER INSERT | blood_group, component_type, initial_volume_ml |
| trg_audit_bag_update | BLOOD_BAG | AFTER UPDATE | old status+vol, new status+vol |
| trg_audit_req_insert | TRANSFUSION_REQ | AFTER INSERT | requested_group, component, qty, urgency |
| trg_audit_req_update | TRANSFUSION_REQ | AFTER UPDATE | old status+allocated, new status+allocated |
| trg_audit_donation_insert | DONATION_LOG | AFTER INSERT | donor_id, qty, date |
| trg_audit_fulfillment_insert | FULFILLMENT_LOG | AFTER INSERT | req_id, bag_id, qty |

**Design decisions:**
- Audit triggers use AFTER (not BEFORE) to ensure only successful operations are logged.
- The old_value/new_value columns use concatenated string format (e.g., "status=Available, vol=450.0") for human readability. In a production system, JSON would be preferred.
- performed_by defaults to 'SYSTEM' because SQLite has no built-in user context. In a multi-user system, this would be set via application context.

---

## 6. SQL View Design

### 6.1 vw_inventory_summary

```sql
SELECT blood_group, component_type,
       COUNT(*) AS bag_count,
       SUM(current_volume_ml) AS total_volume_ml
FROM   BLOOD_BAG
WHERE  status = 'Available'
GROUP  BY blood_group, component_type
```

**Purpose:** Provides a real-time summary of available inventory grouped by blood group and component type. Used by the dashboard's stock ticker and "By Component" tab.

**Why a view?** This query is executed on every dashboard page load. Defining it as a view ensures the query is consistent across all callers and can be optimised by the query planner.

### 6.2 vw_critical_pending

```sql
SELECT tr.req_id, tr.requested_group, tr.requested_component,
       tr.quantity_ml, tr.quantity_allocated_ml,
       (tr.quantity_ml - tr.quantity_allocated_ml) AS remaining_ml,
       tr.urgency_level, tr.status,
       r.name AS recipient_name, r.hospital_name
FROM   TRANSFUSION_REQ tr
JOIN   RECIPIENT r ON tr.recipient_id = r.recipient_id
WHERE  tr.urgency_level = 'Critical'
  AND  tr.status IN ('Pending', 'Partially Fulfilled')
```

**Purpose:** Shows all Critical requests that still need blood. The computed column remaining_ml simplifies dashboard rendering.

**Why a view?** The JOIN between TRANSFUSION_REQ and RECIPIENT, combined with the WHERE filter and computed column, would be duplicated across multiple queries without the view.

### 6.3 vw_expiring_soon

```sql
SELECT bag_id, blood_group, component_type, current_volume_ml,
       expiry_date,
       CAST(julianday(expiry_date) - julianday('now') AS INTEGER) AS days_until_expiry
FROM   BLOOD_BAG
WHERE  status = 'Available'
  AND  julianday(expiry_date) - julianday('now') <= 5
  AND  julianday(expiry_date) - julianday('now') >= 0
ORDER  BY expiry_date ASC
```

**Purpose:** Lists bags expiring within 5 days. The computed column days_until_expiry is used for colour-coding in the UI (red badge for <= 2 days, warning badge otherwise).

**Technical note:** The >= 0 condition excludes already-expired bags. In a production system, a scheduled job would mark these as 'Expired' via a status update.

---

## 7. Audit Trail Architecture

### 7.1 Design Philosophy

The audit trail follows the **database-level trigger pattern** rather than application-level logging. This means:

1. **Every data modification is captured** — whether from the web UI, a seed script, direct SQL, or another trigger's cascading effect.
2. **No application code is needed** — the six AFTER triggers handle all logging automatically.
3. **Trigger cascades are logged** — when trg_auto_expire_bag changes a bag's status, trg_audit_bag_update fires and logs that status change, creating a complete chain of causation.

### 7.2 AUDIT_LOG Table Structure

| Column | Type | Purpose |
|--------|------|---------|
| log_id | INTEGER PK | Unique identifier, auto-incrementing |
| action_type | TEXT | 'INSERT' or 'UPDATE' |
| table_name | TEXT | Which table was modified |
| record_id | INTEGER | PK of the affected row |
| old_value | TEXT | Previous state (NULL for INSERTs) |
| new_value | TEXT | New state |
| timestamp | DATETIME | Auto-set to DATETIME('now') |
| performed_by | TEXT | Defaults to 'SYSTEM' |

### 7.3 Audit Entry Examples

**Donation INSERT:**
```
action_type=INSERT, table_name=DONATION_LOG, record_id=1,
new_value="donor=1, qty=450.0, date=2026-02-28"
```

**Bag Volume Deduction:**
```
action_type=UPDATE, table_name=BLOOD_BAG, record_id=4,
old_value="status=Available, vol=450.0",
new_value="status=Available, vol=0.0"
```

**Auto-Expire Cascade:**
```
action_type=UPDATE, table_name=BLOOD_BAG, record_id=4,
old_value="status=Available, vol=0.0",
new_value="status=Empty, vol=0.0"
```

### 7.4 Audit Growth Characteristics

Each allocation event on a single bag generates approximately 3-4 audit entries:
1. FULFILLMENT_LOG INSERT (the allocation record)
2. TRANSFUSION_REQ UPDATE (status/allocated change)
3. BLOOD_BAG UPDATE (volume deduction)
4. BLOOD_BAG UPDATE (status to Empty, only if volume reaches 0)

Under stress testing with 50 donors and 30 requests, the audit log grows to hundreds of entries without performance degradation.

---

## 8. Component Tracking System

### 8.1 Concept

A standard whole-blood donation of approximately 450ml can be processed in two ways:

1. **Whole Blood:** A single BLOOD_BAG record of 450ml with component_type = 'Whole Blood' and a 42-day shelf life.
2. **Component Split:** Three separate BLOOD_BAG records:
   - Red Blood Cells: 200ml, 42-day shelf life
   - Platelets: 50ml, 5-day shelf life
   - Plasma: 200ml, 365-day shelf life

### 8.2 Implementation

The split is controlled by the `split_components` parameter in `process_donation()`:

```python
COMPONENT_SPLIT = {
    "Red Blood Cells": 200,
    "Platelets": 50,
    "Plasma": 200,
}
```

When `split_components=True`:
1. The function iterates over COMPONENT_SPLIT items.
2. For each component, it queries COMPONENT_MASTER for the shelf_life_days.
3. The expiry date is calculated as `collection_date + timedelta(days=shelf_life_days)`.
4. A separate BLOOD_BAG record is inserted with the component-specific volume and expiry.

### 8.3 Allocation Interaction

The allocation algorithm filters bags by `component_type`:

```sql
AND bb.component_type = ?
```

This means a request for "Red Blood Cells" will NEVER be fulfilled by a "Whole Blood" or "Plasma" bag. This matches real-world clinical practice where component-specific transfusion is standard.

### 8.4 Volume Accounting

For a 450ml split donation:
- DONATION_LOG records quantity_ml = 450 (the total donated)
- Three BLOOD_BAG records are created: 200 + 50 + 200 = 450ml total
- The sum of bag initial volumes equals the donation volume, maintaining accounting integrity

---

## 9. Soft Delete Pattern

### 9.1 Rationale

Hard deleting donors or hospitals would violate referential integrity (orphaned DONATION_LOG, BLOOD_BAG, TRANSFUSION_REQ records) and destroy historical data needed for audit compliance.

### 9.2 Implementation

Both DONOR and RECIPIENT tables include:

```sql
is_active INTEGER DEFAULT 1
```

**Deactivation:** `UPDATE DONOR SET is_active = 0 WHERE donor_id = ?`

**Filtering:** All application queries include `WHERE is_active = 1`:
- Donor dropdown: `SELECT * FROM DONOR WHERE is_active = 1`
- Loyalty leaderboard: `WHERE d.is_active = 1`
- Eligible donors for shortage alerts: `WHERE d.blood_group = ? AND d.is_active = 1`
- Donation processing: `WHERE donor_id = ? AND is_active = 1`

### 9.3 Data Preservation Guarantee

When a donor is deactivated:
- Their BLOOD_BAG records are NOT affected (bags are linked via DONATION_LOG.donation_id, not directly via donor_id with a cascade)
- Their existing blood bags remain available for allocation
- Their DONATION_LOG entries persist for audit
- The donor's row remains in the database for historical reference

---

## 10. Smart Allocation Algorithm

### 10.1 Algorithm Overview

The `smart_allocate_all()` function implements a **priority-queue-based, compatibility-aware, partial-fulfillment allocation** algorithm.

### 10.2 Step-by-Step Execution

**Step 1 — Build Priority Queue:**
```sql
SELECT * FROM TRANSFUSION_REQ
WHERE status IN ('Pending', 'Partially Fulfilled')
ORDER BY
    CASE WHEN urgency_level = 'Critical' THEN 1 ELSE 2 END,
    quantity_ml DESC
```

This produces a priority-ordered list where:
- All Critical requests come before all Normal requests
- Within the same urgency, larger volume needs come first (maximising impact)

**Step 2 — For Each Request, Find Compatible Bags:**
```sql
SELECT bb.bag_id, bb.current_volume_ml, bb.expiry_date,
       cm.preference_rank
FROM   BLOOD_BAG bb
JOIN   COMPATIBILITY_MATRIX cm
       ON cm.donor_group = bb.blood_group
WHERE  cm.recipient_group = ?
  AND  bb.status = 'Available'
  AND  bb.current_volume_ml > 0
  AND  bb.component_type = ?
ORDER  BY cm.preference_rank ASC, bb.expiry_date ASC
```

This query:
- JOINs BLOOD_BAG with COMPATIBILITY_MATRIX on the bag's blood group as donor_group
- Filters for bags compatible with the requested recipient_group
- Filters for the correct component type
- Sorts by preference_rank (exact match first) then expiry_date (FIFO — oldest first to minimise waste)

**Step 3 — Iterative Volume Deduction:**

```
for each compatible bag (in preference+FIFO order):
    if already_allocated >= needed: break
    take = min(bag.current_volume_ml, needed - already_allocated)
    INSERT FULFILLMENT_LOG(req_id, bag_id, take)
      → triggers: volume_guard check, req_allocated update, audit
    UPDATE BLOOD_BAG SET current_volume_ml = vol - take
      → triggers: auto_expire if vol=0, audit
    already_allocated += take
```

**Step 4 — Transaction Safety:**
The entire allocation is wrapped in try/except with conn.rollback() on failure, ensuring atomicity — either all allocations for all requests succeed, or none do.

### 10.3 Operation Order Significance

The order of INSERT-then-UPDATE within the loop is critical:

1. **FULFILLMENT_LOG INSERT first** — The volume_guard trigger checks the bag's current_volume_ml at this point. Since the volume has not been deducted yet, the guard sees the full remaining volume and validates correctly.

2. **BLOOD_BAG UPDATE second** — Deducts the volume. If this were done first, the volume_guard trigger on the subsequent FULFILLMENT_LOG INSERT would see the already-reduced volume and potentially reject a valid allocation.

### 10.4 Idempotency

Running the allocation multiple times when all requests are already fulfilled produces no changes. The WHERE clause filters out Fulfilled requests, so the loop body never executes. This is important for safe retry behaviour.

---

## 11. Cross-Match Compatibility Scoring

### 11.1 Medical Background

ABO/Rh blood group compatibility follows strict immunological rules:
- **Type O-** is the universal donor (no A, B, or Rh antigens)
- **Type AB+** is the universal recipient (has all antigens, no antibodies)
- Transfusing incompatible blood causes potentially fatal haemolytic reactions

### 11.2 Preference Ranking Strategy

The preference_rank column encodes clinical best practice:

- **Rank 1 (Exact Match):** Always used first. No immunological risk, preserves rare blood for those who truly need it.
- **Rank 2-3 (Close Alternatives):** Used when exact match is unavailable. Single-antigen differences.
- **Rank 4+ (Universal Donor):** O- blood is compatible with everyone but is the rarest type. It should only be used for non-O- patients when all closer alternatives are exhausted.

### 11.3 Conservation Effect

This ranking system means:
- An A+ patient will use A+ blood first, then A-, then O+, then O- (in that order).
- O- blood is naturally conserved for O- patients (where it's the only option, rank 1).
- AB+ patients have the most options (8 compatible groups) and therefore put the least pressure on rare blood.

---

## 12. Partial Fulfillment Mechanism

### 12.1 Problem

Traditional systems treat requests as binary: either fully fulfilled or not. This means a patient needing 500ml of O- gets nothing if only 300ml exists, even though 300ml could save their life.

### 12.2 Solution

The system tracks `quantity_allocated_ml` on each TRANSFUSION_REQ and allows incremental allocation:

1. **First allocation run:** 300ml available, 300ml allocated. Status → "Partially Fulfilled" (300/500 = 60%).
2. **New donation arrives:** 250ml of compatible blood added.
3. **Second allocation run:** 200ml more allocated. Status → "Fulfilled" (500/500 = 100%).

### 12.3 Database-Level Automation

The trg_update_req_allocated trigger handles all status transitions automatically:

```sql
SET quantity_allocated_ml = (
    SELECT COALESCE(SUM(quantity_allocated_ml), 0)
    FROM FULFILLMENT_LOG WHERE req_id = NEW.req_id
),
status = CASE
    WHEN SUM >= quantity_ml THEN 'Fulfilled'
    WHEN SUM > 0 THEN 'Partially Fulfilled'
    ELSE status
END
```

No application code manages request status — it is always derived from the sum of FULFILLMENT_LOG entries.

### 12.4 UI Representation

The hospital page renders a progress bar for each request:

```
percentage = (quantity_allocated_ml / quantity_ml) * 100
```

The bar is green at 100% and yellow for partial fulfillment, giving immediate visual feedback.

---

## 13. Predictive Shortage Alert Engine

### 13.1 Algorithm

The `get_shortage_alerts()` function implements a **rolling-average projection model**:

1. **Current Stock:** Sum of current_volume_ml for all Available bags, grouped by blood_group.
2. **Average Daily Consumption:** Sum of all FULFILLMENT_LOG allocations in the past 30 days, divided by 30, grouped by blood_group.
3. **Projected Days:** current_stock / average_daily_consumption.
4. **Alert Threshold:** Groups with < 3 projected days of supply generate an alert.

### 13.2 Edge Cases Handled

- **Zero consumption, positive stock:** projected_days = infinity (no alert).
- **Zero consumption, zero stock:** projected_days = 0 (alert).
- **High consumption, low stock:** projected_days < 3 (alert with suggested donors).

### 13.3 Donor Suggestion Integration

For each alerted blood group, the system calls `get_eligible_donors_for_group()` to find donors who:
- Have the matching blood group
- Are active (not soft-deleted)
- Are eligible to donate (56+ days since last donation, or never donated)

These donors are displayed on shortage alert cards with their contact information.

### 13.4 SQL for Consumption Calculation

```sql
SELECT bgm.blood_group,
       COALESCE(SUM(fl.quantity_allocated_ml), 0) / 30.0 AS avg_daily
FROM   BLOOD_GROUP_MASTER bgm
LEFT JOIN BLOOD_BAG bb ON bgm.blood_group = bb.blood_group
LEFT JOIN FULFILLMENT_LOG fl ON fl.bag_id = bb.bag_id
      AND fl.fulfillment_date >= DATE('now', '-30 days')
GROUP  BY bgm.blood_group
```

The LEFT JOIN from BLOOD_GROUP_MASTER ensures all 8 blood groups are represented, even those with zero consumption or zero stock.

---

## 14. Donor Loyalty Module

### 14.1 Scoring Formula

```
loyalty_score = (total_donations * 10) + rare_group_bonus
```

Where rare_group_bonus depends on blood group rarity:
- O-, AB-: +10 (rarest, highest clinical value)
- A-, B-: +5 (moderately rare)
- A+, B+, AB+, O+: +0 (common)

### 14.2 Eligibility Calculation

A donor is eligible to donate if:
- They have never donated (last_donation_date IS NULL), OR
- At least 56 days have passed since their last donation

This is calculated in SQL using:
```sql
CASE
    WHEN d.last_donation_date IS NULL THEN 1
    WHEN julianday('now') - julianday(d.last_donation_date) >= 56 THEN 1
    ELSE 0
END AS is_eligible
```

### 14.3 Leaderboard Ordering

The loyalty leaderboard is sorted by descending loyalty score:

```sql
ORDER BY (COUNT(dl.donation_id) * 10
          + CASE ... rare_bonus ... END) DESC
```

This surfaces the most valuable donors at the top, making it easy to identify who to contact during shortages.

### 14.4 get_eligible_donors_for_group

This function is used by the shortage alert system. It finds donors of a specific blood group who are eligible:

```sql
WHERE d.blood_group = ? AND d.is_active = 1
HAVING days_since_last >= 56 OR d.last_donation_date IS NULL
ORDER BY total_donations DESC, days_since_last DESC
LIMIT ?
```

The ordering prioritises frequent donors (more likely to respond) and those who have waited longest (most ready to donate).

---

## 15. Flask Application Layer

### 15.1 Route Architecture

| Route | Method(s) | Handler | Purpose |
|-------|-----------|---------|---------|
| / | GET | index() | Dashboard with all views and analytics |
| /donor | GET, POST | donor() | Donor registration, donation logging, deactivation |
| /hospital | GET, POST | hospital() | Hospital registration, blood requests, deactivation |
| /allocate_all | POST | allocate_all() | Runs smart allocation algorithm |
| /audit | GET | audit() | Displays full audit trail |

### 15.2 POST Action Routing

The /donor and /hospital routes use hidden form fields to distinguish between multiple POST actions:

**Donor route:**
- `register` in form → New donor registration
- `donate` in form → Log donation
- `deactivate` in form → Soft delete donor

**Hospital route:**
- `add_hospital` in form → New hospital registration
- `request_blood` in form → New transfusion request
- `deactivate_hospital` in form → Soft delete hospital

### 15.3 Flash Message Pattern

All user-visible feedback uses Flask's flash() mechanism:

```python
flash("message text", "category")  # category = success|danger|warning|info
```

The base template renders these as Bootstrap alerts:
```html
{% for category, message in messages %}
    <div class="alert alert-{{ category }}">{{ message }}</div>
{% endfor %}
```

### 15.4 Dashboard Data Assembly

The index() route assembles 10 distinct data sets for the dashboard:

1. critical_agg — Aggregated critical shortages by blood group
2. critical_details — Per-request critical details
3. inventory_ticker — Stock summary by blood group
4. inventory_detail — Stock by blood group + component (from view)
5. expiring_soon — Bags expiring within 5 days (from view)
6. shortage_alerts — Predictive shortage projections
7. shortage_donors — Suggested donors for each alerted group
8. donations — Recent donation history
9. fulfilled_history — Recent fulfillment records
10. full_inventory — All available bags
11. audit_log — Latest 25 audit entries

---

## 16. Connection Management and PRAGMAs

### 16.1 Connection Helper (db.py)

```python
DB_NAME: str = "bloodbank.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA recursive_triggers = ON;")
    return conn
```

### 16.2 PRAGMA Significance

**foreign_keys = ON:**
- SQLite does NOT enforce foreign keys by default. This PRAGMA must be set on every connection.
- Without it, inserting "Z+" as a blood_group would succeed silently, defeating the entire normalisation strategy.

**recursive_triggers = ON:**
- Required for the auto-expire cascade: when trg_auto_expire_bag updates BLOOD_BAG.status, the trg_audit_bag_update trigger must fire to log the change.
- Without this PRAGMA, the audit trigger would not fire from within the auto-expire trigger context, creating a gap in the audit trail.

### 16.3 row_factory = sqlite3.Row

This setting makes query results accessible by column name (row["blood_group"]) instead of only by index (row[2]). This improves code readability and reduces bugs from column order changes.

### 16.4 Test Database Isolation

Tests override DB_NAME before calling init_db():

```python
db.DB_NAME = TEST_DB
init_db()
```

This ensures tests use a separate database file (bloodbank_test_advanced.db), preventing interference with the production database.

---

## 17. Schema Initialisation Strategy

### 17.1 Drop-and-Recreate Pattern

The init_db() function uses a destructive pattern:

```python
if os.path.exists(db_name):
    os.remove(db_name)
```

This ensures a clean state every time. The rationale:
- During development, schema changes are frequent. ALTER TABLE in SQLite is limited.
- The seed script can repopulate data instantly.
- In production, a migration tool (Alembic, etc.) would replace this approach.

### 17.2 Initialisation Order

The order of table creation matters due to FK dependencies:

1. Master tables first (no FK dependencies)
2. DONOR and RECIPIENT (depend on BLOOD_GROUP_MASTER)
3. DONATION_LOG (depends on DONOR)
4. BLOOD_BAG (depends on DONATION_LOG, BLOOD_GROUP_MASTER, COMPONENT_MASTER, BAG_STATUS_MASTER)
5. TRANSFUSION_REQ (depends on RECIPIENT, BLOOD_GROUP_MASTER, COMPONENT_MASTER, URGENCY_LEVEL_MASTER, REQUEST_STATUS_MASTER)
6. FULFILLMENT_LOG (depends on TRANSFUSION_REQ, BLOOD_BAG)
7. AUDIT_LOG (no FK dependencies, but logically last)
8. Triggers (reference existing tables)
9. Views (reference existing tables)

---

## 18. Frontend Architecture

### 18.1 Template Hierarchy

```
base.html (layout: navbar, flash messages, Bootstrap/Icons CSS/JS)
├── home.html (dashboard: alerts, ticker, tabs, tables)
├── donor.html (registration form, donation form, loyalty leaderboard)
├── hospital.html (hospital form, request form, prioritised waitlist)
└── audit.html (full audit log table)
```

### 18.2 Bootstrap Icons Integration

All icons use the Bootstrap Icons library (loaded via CDN in base.html) with the `<i class="bi bi-..."></i>` pattern. This replaces emojis for a professional appearance. Example icon mappings:

- Blood droplet: bi-droplet-fill
- Warning triangle: bi-exclamation-triangle-fill
- Trend graph: bi-graph-down-arrow
- Clock/timer: bi-clock-history
- Trophy: bi-trophy
- Hospital: bi-hospital
- Checkmark: bi-check-lg, bi-check-circle-fill
- Star: bi-star-fill

### 18.3 Responsive Design

Bootstrap 5's grid system (col-md-3, col-md-4, col-md-8) ensures the layout adapts to different screen sizes. The dashboard stock ticker cards stack vertically on mobile and display in a 4-column grid on desktop.

### 18.4 Progress Bar Rendering

The hospital page renders fulfillment progress bars dynamically:

```html
{% set pct = ((req.quantity_allocated_ml / req.quantity_ml) * 100) | round(0) | int %}
<div class="progress-bar bg-{{ 'success' if pct == 100 else 'warning' }}"
     style="width: {{ pct }}%">{{ pct }}%</div>
```

---

## 19. Error Handling Strategy

### 19.1 Three-Layer Defence

1. **UI Layer:** Dropdowns populated from master tables prevent invalid selections. HTML5 `required` attributes prevent empty submissions.
2. **Application Layer:** Python code validates inputs and catches exceptions with try/except, returning user-friendly flash messages.
3. **Database Layer:** FK constraints, triggers with RAISE(ABORT), and NOT NULL constraints reject invalid data even if the application layer is bypassed.

### 19.2 Transaction Management

All write operations follow the pattern:

```python
conn = get_db_connection()
try:
    # ... operations ...
    conn.commit()
    return True, "Success message"
except Exception as e:
    conn.rollback()
    return False, str(e)
finally:
    conn.close()
```

This ensures:
- Successful operations are committed atomically
- Failed operations are rolled back completely
- Connections are always closed (no resource leaks)

### 19.3 Error Message Propagation

Trigger error messages (DONATION_SAFETY, VOLUME_GUARD) propagate through the exception chain:
1. Trigger fires RAISE(ABORT, 'message')
2. sqlite3 raises IntegrityError with the message
3. process_donation() catches Exception, returns (False, str(e))
4. main.py calls flash(message, "danger")
5. base.html renders the red alert div

---

## 20. Data Flow Diagrams

### 20.1 Donation Flow

```
User submits donation form
  → main.py donor() route
    → process_donation(donor_id, quantity, split)
      → Query DONOR (check active, get blood_group)
      → Application-level 56-day check
      → INSERT DONATION_LOG
        → trg_donation_safety_lock (DB-level 56-day check)
        → trg_audit_donation_insert (audit log)
      → For each component:
        → Query COMPONENT_MASTER (get shelf_life_days)
        → Calculate expiry_date
        → INSERT BLOOD_BAG
          → trg_audit_bag_insert (audit log)
      → UPDATE DONOR.last_donation_date
      → COMMIT
```

### 20.2 Allocation Flow

```
User clicks "Allocate" button
  → main.py allocate_all() route
    → smart_allocate_all()
      → Query all Pending/Partial requests (ordered by urgency, qty)
      → For each request:
        → Query compatible bags (JOIN COMPATIBILITY_MATRIX, ordered)
        → For each bag until needed volume filled:
          → INSERT FULFILLMENT_LOG
            → trg_fulfillment_volume_guard (check)
            → trg_update_req_allocated (update request status)
            → trg_audit_fulfillment_insert (audit)
            → trg_audit_req_update (audit)
          → UPDATE BLOOD_BAG.current_volume_ml
            → trg_auto_expire_bag (if vol=0)
              → trg_audit_bag_update (audit)
            → trg_audit_bag_update (audit)
      → COMMIT
```

### 20.3 Dashboard Load Flow

```
User navigates to /
  → main.py index() route
    → 9 SQL queries + 2 function calls
    → Render home.html with 11 template variables
    → Browser renders: alerts, shortage forecast,
      expiring-soon, stock ticker, tabs (inventory,
      components, donations, fulfilled, audit)
```

---

## 21. Design Decisions and Trade-offs

### 21.1 Volume Tracking vs Unit Tracking

**Decision:** Track blood in millilitres, not "units."

**Rationale:** A standard blood unit is approximately 450ml, but clinical needs vary (200ml for a child, 600ml for a trauma patient). Ml-level tracking enables partial usage of bags across multiple small transfusions, reducing waste.

**Trade-off:** More complex allocation logic. Each bag requires tracking both initial_volume_ml and current_volume_ml.

### 21.2 Database-Level vs Application-Level Constraints

**Decision:** Enforce critical business rules at the database level via triggers.

**Rationale:** Application code can be bypassed (direct SQL access, bugs, future code changes). Database triggers are inescapable — they fire regardless of how data is modified.

**Trade-off:** Debugging trigger interactions is harder than debugging Python code. Error messages from RAISE(ABORT) are less user-friendly than application-level validation.

**Mitigation:** Dual enforcement — the application layer provides user-friendly messages, and triggers serve as the safety net.

### 21.3 Compatibility Matrix as a Table vs Application Logic

**Decision:** Store blood group compatibility rules in a database table, not in Python code.

**Rationale:**
1. The allocation query directly JOINs with the matrix, making the SQL self-contained.
2. Adding or modifying compatibility rules requires only INSERT/UPDATE/DELETE on the table, not code changes.
3. The preference_rank column enables the SQL ORDER BY to handle prioritisation without application logic.

**Trade-off:** 27 rows of reference data that rarely change. A Python dictionary would be simpler for a small project.

### 21.4 Partial Fulfillment via Trigger vs Application Code

**Decision:** Use a trigger (trg_update_req_allocated) to automatically update request status.

**Rationale:** The trigger recalculates the total allocated from all FULFILLMENT_LOG records. This is always accurate, even if records are modified or deleted. Application-level tracking could become inconsistent if the sum drifts.

**Trade-off:** The trigger fires on every FULFILLMENT_LOG INSERT, adding overhead. For this project's scale, the overhead is negligible.

### 21.5 Recursive Triggers for Audit Completeness

**Decision:** Enable PRAGMA recursive_triggers to allow trigger-triggered-triggers.

**Rationale:** When a bag's volume reaches zero, trg_auto_expire_bag updates the status. This status change must be logged by trg_audit_bag_update. Without recursive triggers, the audit trail would be incomplete.

**Trade-off:** Recursive triggers increase the risk of infinite loops. This is mitigated by the WHEN condition `NEW.status != 'Empty'` on the auto-expire trigger, which prevents re-firing.

### 21.6 FIFO Expiry Ordering in Allocation

**Decision:** Within the same compatibility rank, allocate from bags with the earliest expiry date first.

**Rationale:** This is the standard FIFO (First Expired, First Out) strategy used in real blood banks. It minimises waste from expiration.

**Implementation:** `ORDER BY cm.preference_rank ASC, bb.expiry_date ASC`

### 21.7 Critical-First, Largest-First Priority

**Decision:** Allocate to Critical requests before Normal, and within the same urgency level, larger requests first.

**Rationale:** Critical patients face immediate mortality risk. Larger requests (e.g., 600ml trauma) indicate more severe conditions than smaller ones (e.g., 150ml elective).

**Trade-off:** Smaller Normal requests may wait longer. In a production system, time-based aging could be added to prevent starvation.

### 21.8 SQLite vs PostgreSQL/MySQL

**Decision:** Use SQLite for the database engine.

**Rationale:** Zero configuration, single-file database, full SQL support including triggers and views, native Python support via the sqlite3 standard library. Ideal for a single-user academic project.

**Trade-off:** No concurrent write support (single-writer lock), no stored procedures, no built-in user authentication. For a multi-user production system, PostgreSQL would be the appropriate choice.
