# Blood Bank Management System 

A full-featured, web-based Blood Bank Management System built with **Python / Flask / SQLite**.  
Designed as a DBMS course project, it showcases advanced relational database techniques including triggers, views, audit trails, domain normalization, and an intelligent allocation engine.

---

## Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Database Triggers** | Auto-expire bags when volume reaches 0, 56-day donation safety lock, fulfillment volume guard |
| 2 | **SQL Views** | `vw_inventory_summary`, `vw_critical_pending`, `vw_expiring_soon` for real-time dashboards |
| 3 | **Audit Trail** | Forensic INSERT/UPDATE logging via 6 triggers on sensitive tables (HIPAA-style) |
| 4 | **Domain Normalization** | FK-enforced lookup tables for blood groups, urgency levels, bag statuses, request statuses |
| 5 | **Component Tracking** | Split whole-blood into RBC (42d), Platelets (5d), Plasma (365d) with individual shelf lives |
| 6 | **Soft Deletes** | `is_active` flag on DONOR and RECIPIENT — data preserved for audit, hidden from UI |
| 7 | **Predictive Shortage Alerts** | Projected stock-days based on 30-day rolling consumption average |
| 8 | **Cross-Match Compatibility** | 27-row COMPATIBILITY_MATRIX with preference ranking — conserves O− universal donor blood |
| 9 | **Donor Loyalty Module** | Scoring (donations × 10 + rare-group bonus), eligibility tracking, leaderboard |
| 10 | **Partial Fulfillment** | Incremental allocation with progress bars; status: Pending → Partially Fulfilled → Fulfilled |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.14+ |
| Web Framework | Flask 3.1 |
| Database | SQLite 3 (13 tables, 3 views, 10 triggers) |
| Templating | Jinja2 + Bootstrap 5 |
| Package Manager | [uv](https://docs.astral.sh/uv/) |
| Linting | ruff, ty |
| Testing | pytest (95 tests) |

---

## Quick Start

### Prerequisites

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** package manager

### 1. Install Dependencies

```bash
uv sync
```

### 2. Initialise the Database

```bash
uv run python db_init.py
```

### 3. (Optional) Load Demo Data

```bash
uv run python seed_demo.py
```

This registers 12 donors, 4 hospitals, logs donations (both whole-blood and component-split), creates 8 transfusion requests (including Critical), runs allocation, sets up an expiring-soon bag, and soft-deletes a donor — all for a realistic demo.

### 4. Start the Application

```bash
uv run python main.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## Linting & Type Checking

```bash
uvx ruff check --fix    # Lint
uvx ruff format          # Format
uvx ty check             # Type check
```

---

## Database Schema

The system uses **13 tables**, **3 views**, and **10 triggers**:

### Master/Lookup Tables (6)
- `BLOOD_GROUP_MASTER` — 8 valid blood groups
- `URGENCY_LEVEL_MASTER` — Normal, Critical
- `BAG_STATUS_MASTER` — Available, Empty, Expired, Quarantined
- `REQUEST_STATUS_MASTER` — Pending, Partially Fulfilled, Fulfilled, Cancelled
- `COMPONENT_MASTER` — Whole Blood, RBC, Platelets, Plasma, Cryoprecipitate
- `COMPATIBILITY_MATRIX` — 27-row cross-match preference table

### Core Tables (6)
- `DONOR` — donor registry with `is_active` soft-delete flag
- `RECIPIENT` — hospital registry with `is_active` soft-delete flag
- `DONATION_LOG` — donation events
- `BLOOD_BAG` — inventory with ml-level volume tracking
- `TRANSFUSION_REQ` — blood requests with partial fulfillment tracking
- `FULFILLMENT_LOG` — N:M allocation records

### Audit Table (1)
- `AUDIT_LOG` — forensic trail of all changes

### Views (3)
- `vw_inventory_summary` — stock by group + component
- `vw_critical_pending` — unresolved critical requests
- `vw_expiring_soon` — bags expiring within 5 days

### Triggers (10)
- `trg_auto_expire_bag` — flips status to Empty when volume ≤ 0
- `trg_donation_safety_lock` — enforces 56-day donation interval
- `trg_fulfillment_volume_guard` — prevents over-allocation
- `trg_update_req_allocated` — auto-updates request status on fulfillment
- 6 audit triggers — log INSERT/UPDATE on BLOOD_BAG, TRANSFUSION_REQ, DONATION_LOG, FULFILLMENT_LOG

---

## Smart Allocation Algorithm

The `smart_allocate_all()` function:

1. **Priority queue**: Critical urgency first, then largest quantity descending
2. **Compatibility scoring**: Uses `COMPATIBILITY_MATRIX` — exact match preferred, O− used last
3. **FIFO expiry**: Oldest compatible bags consumed first to minimise waste
4. **Partial fulfillment**: Allocates whatever is available; DB trigger updates status automatically
5. **Transactional**: Full rollback on error — no data corruption

---

## Pages

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Dashboard — alerts, shortage forecast, expiring bags, stock ticker, inventory, history, audit |
| `/donor` | GET/POST | Register donors, log donations (whole-blood or component-split), loyalty leaderboard, deactivate |
| `/hospital` | GET/POST | Add hospitals, submit blood requests (with component + urgency), view prioritised waitlist |
| `/allocate_all` | POST | Run the smart allocation algorithm |
| `/audit` | GET | Full audit trail with action type badges |

---

## Author

**Abdul Ahad**

---

## License

This project is for educational purposes (DBMS course project).
