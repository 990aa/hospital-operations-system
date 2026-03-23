# Blood Bank Management System — Demo Guide

This guide walks through a complete demonstration of all 10 enhanced DBMS features, followed by a comprehensive section on edge cases and how the application handles each one.

---

## Prerequisites

Start with a fresh database and seed data:

```
uv sync
uv run python db_init.py
uv run python seed_demo.py
uv run python main.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## 1. Dashboard Overview ( / )

**What to observe:**

- **Critical Alerts Banner (red):** Shows any pending Critical requests with an "ALLOCATE RESOURCES NOW" button.
- **Shortage Forecast Cards:** Each card shows a blood group, projected days of supply, and suggested donors to contact.
- **Expiring Soon Table:** Lists bags expiring within 5 days (seed data includes one set to expire in 2 days).
- **Stock Ticker:** Cards for each blood group showing bag count and total volume in ml.

**Tabs to explore:**

- **Detailed Inventory:** Every bag with status, volume, component type, and expiry date.
- **By Component:** Stock grouped by component type (Whole Blood, RBC, Platelets, Plasma).
- **Donation History:** All donations with donor name, blood group, and volume.
- **Fulfilled Requests:** Requests that have been partially or fully allocated.
- **Audit Trail (inline):** Recent audit log entries.

---

## 2. Donor Portal ( /donor )

### 2a. Register a New Donor

1. Fill in: **Name** = "Test Donor", **Blood Group** = "O-", **Phone** = "03001234567"
2. Click **Register Donor**
3. **Observe:** Green flash message "Donor registered." The donor appears in the leaderboard below with 0 donations.

### 2b. Log a Whole-Blood Donation

1. Select the newly registered donor from the dropdown
2. Enter **Quantity** = 450 ml
3. Leave "Split into components" unchecked
4. Click **Save**
5. **Observe:** Flash message confirms donation. Dashboard stock updates.

### 2c. Log a Component-Split Donation

1. Select any donor (ensure 56+ days since last donation, or use a different donor)
2. Enter **Quantity** = 450 ml
3. Check "Split into components"
4. Click **Save**
5. **Observe:** Flash message shows donation logged and split. Navigate to Dashboard, "By Component" tab to see 3 new bags: RBC (200ml), Platelets (50ml), Plasma (200ml).

### 2d. Demonstrate 56-Day Safety Lock (Trigger)

1. **Immediately** try to log another donation for the same donor used in 2c
2. Click **Save**
3. **Observe:** Red flash message containing "DONATION_SAFETY" — the database trigger rejected the donation.

### 2e. Donor Loyalty Leaderboard

**What to observe:**

- **Score column:** Donors with rare groups (O-, AB-) have a +10 bonus; (A-, B-) have +5; others +0. Score = (donations x 10) + bonus.
- **"Eligible" badge (green):** Appears if 56+ days since last donation.
- **Star icon:** Appears next to rare blood group donors.
- **Sorting:** Highest score first.

### 2f. Soft Delete a Donor

1. Click the "Deactivate" button next to any donor in the leaderboard
2. **Observe:** The donor disappears from the list. Navigate to Dashboard, Detailed Inventory — their previous blood bags are **still present** and usable.

---

## 3. Hospital Portal ( /hospital )

### 3a. Register a Hospital

1. Fill in: **Contact Person** = "Dr. Smith", **Hospital** = "City Hospital", **Contact Info** = "0300-HOSPITAL"
2. Click **Add Hospital**
3. **Observe:** Flash message "Recipient added." Hospital appears in the dropdown.

### 3b. Submit a Blood Request

1. Select the hospital from the dropdown
2. **Blood Group** = "A+", **Urgency** = "Critical", **Component** = "Whole Blood", **Quantity** = 200 ml
3. Click **Submit Request**
4. **Observe:** Request appears in the prioritised waitlist below with status "Pending" and 0% progress bar.

### 3c. Submit Multiple Requests with Different Priorities

1. Add another request: Blood Group = "B+", Urgency = "Normal", Component = "Whole Blood", Quantity = 300 ml
2. **Observe:** The waitlist automatically sorts **Critical first, then by largest quantity**. The A+ Critical request is above the B+ Normal request.

### 3d. Soft Delete a Hospital

1. Click the "Deactivate" button next to any hospital
2. **Observe:** Hospital disappears from the active list. Its pending requests remain visible and can still be allocated.

---

## 4. Smart Allocation — The Core Algorithm

### 4a. Run Allocation

1. Navigate to Dashboard ( / )
2. Click the "ALLOCATE RESOURCES NOW" button (in the red Critical alert banner) or the "Run Allocation Algorithm" button
3. **Observe:** A flash message reports allocation results: how many requests were processed.

### 4b. Verify Allocation Results

- **Dashboard, Fulfilled Requests tab:** Shows which requests were fulfilled/partially fulfilled with specific bag IDs and volumes.
- **Hospital Portal:** Progress bars update — some requests may show partial fulfillment (e.g., 60%) if insufficient stock existed.
- **Dashboard, Detailed Inventory:** Bag volumes have been deducted. Bags that reached 0 ml show status "Empty" (auto-expire trigger).

### 4c. Verify Compatibility Scoring

Check which bags were allocated to requests:

- **Exact matches preferred:** An A+ request should use A+ bags first.
- **Fallback used only when needed:** O- bags (universal donor) should only be used for A+ requests if no A+, A-, O+, or O- bags were available.
- View the Fulfilled Requests tab to see the donor group vs. requested group for each allocation.

### 4d. Partial Fulfillment

1. Create a request for 500ml of a blood group with limited stock (e.g., AB-)
2. Run allocation
3. **Observe:** The request status becomes "Partially Fulfilled" with a progress bar showing the percentage filled. The remaining ml needed is displayed.
4. Add more blood of that group (via donation), run allocation again
5. **Observe:** The request progresses further or becomes "Fulfilled".

---

## 5. Audit Trail ( /audit )

1. Navigate to **/audit**
2. **Observe:** A chronological table of all database changes:
   - Green INSERT badges for new donations, bags, requests, fulfillments
   - Blue UPDATE badges for bag volume deductions, status changes
   - Old Value and New Value columns showing exactly what changed
   - Timestamps in ISO format
   - Performed By column (currently "SYSTEM" for trigger-generated entries)

**Key things to demonstrate:**

- Find a BLOOD_BAG UPDATE entry showing volume change (e.g., "vol=450.0" to "vol=250.0")
- Find a TRANSFUSION_REQ UPDATE showing status change ("Pending" to "Partially Fulfilled" to "Fulfilled")
- Note that audit entries are created **automatically by triggers** — no application code explicitly writes to AUDIT_LOG

---

## 6. Predictive Shortage Alerts

1. Navigate to Dashboard
2. Look at the **Shortage Forecast** section
3. **Observe:** Cards show each blood group with:
   - Current stock in ml
   - Average daily consumption (computed from last 30 days of FULFILLMENT_LOG)
   - Projected days of supply remaining
   - Red warning for groups with under 3 days of stock
   - Suggested donors to contact (from the loyalty module)

**To demonstrate a shortage:**

- Create multiple large requests for a specific blood group
- Run allocation to deplete stock
- Dashboard will show that group with low projected supply and suggest eligible donors

---

## 7. Domain Normalisation

### Demonstrate FK Enforcement

1. Go to Hospital Portal
2. Try to submit a request with an invalid blood group (this is prevented by the dropdown, but the DB would reject it)
3. **For a technical demo:** Open the database directly and try:
   ```
   INSERT INTO DONOR (name, blood_group, phone) VALUES ('Bad', 'Z+', '000');
   ```
   Result: **FOREIGN KEY constraint failed** — the blood_group must exist in BLOOD_GROUP_MASTER.

### Show Master Table Contents

All dropdowns in the UI are populated from master tables, ensuring consistency across the application.

---

## 8. Component Tracking

1. Log a **component-split donation** (see step 2c above)
2. Navigate to Dashboard, "By Component" tab
3. **Observe:** Three separate entries for the single donation:
   - Red Blood Cells: 200ml, expiry = collection + 42 days
   - Platelets: 50ml, expiry = collection + 5 days
   - Plasma: 200ml, expiry = collection + 365 days
4. Create a request specifically for "Red Blood Cells" component
5. Run allocation
6. **Observe:** Only RBC bags are allocated — Platelets and Plasma bags are not used for an RBC request.

---

## 9. Expiring Soon Warning (View)

1. Dashboard displays an "Expiring in 5 Days" table
2. The seed data includes a bag set to expire in 2 days
3. **Observe:** The table shows bag ID, blood group, component, volume, and days until expiry
4. This data comes from the vw_expiring_soon view — a real-time computed query

---

## 10. Edge Cases and Error Handling

This section demonstrates every edge case the application handles, grouped by feature. For each case, the expected behaviour and the mechanism that enforces it are documented.

---

### 10.1 Donation Edge Cases

#### Case: 56-Day Donation Safety Lock
- **Trigger:** Donor attempts to donate again within 56 days of their last donation.
- **How to reproduce:** Select any donor who donated today from the dropdown, enter 450 ml, click Save.
- **Expected result:** Red flash message: "DONATION_SAFETY: Donor must wait X more days before donating again."
- **Enforcement mechanism:** Two layers: (1) Application-level Python check in process_donation() catches the condition and shows a human-readable message. (2) Even if the Python check is bypassed, the database trigger trg_donation_safety_lock fires a BEFORE INSERT ABORT on DONATION_LOG, making it impossible to insert a violation.

#### Case: Donation Exactly After 56 Days
- **Trigger:** Donor's last donation was exactly 56 days ago.
- **Expected result:** Donation succeeds normally and creates bag(s).
- **Enforcement mechanism:** The trigger uses julianday difference >= 56 as the safe threshold.

#### Case: Inactive (Soft-Deleted) Donor Attempts to Donate
- **Trigger:** A deactivated donor's ID is submitted for donation.
- **Expected result:** Error "Donor not found or inactive."
- **Enforcement mechanism:** process_donation() queries WHERE is_active = 1, so soft-deleted donors are excluded.

#### Case: Nonexistent Donor ID
- **Trigger:** A donation form submission references a donor_id that does not exist.
- **Expected result:** Error "Donor not found or inactive."
- **Enforcement mechanism:** The SQL query returns no rows, and the code raises ValueError.

#### Case: Very Small Donation Volume (1 ml)
- **Trigger:** Donor donates just 1 ml.
- **Expected result:** Donation succeeds. A single Whole Blood bag of 1 ml is created.
- **Notes:** The system does not enforce a minimum volume — all ml-level tracking works correctly.

#### Case: Very Large Donation Volume (5000 ml)
- **Trigger:** Donor donates 5000 ml.
- **Expected result:** Donation succeeds. The system tracks volume precisely at any scale.
- **Notes:** In a production system, UI-level validation would restrict realistic volumes.

---

### 10.2 Allocation Edge Cases

#### Case: No Stock Available
- **Trigger:** All blood bags are Empty/Expired and a request is pending.
- **How to reproduce:** Deplete all stock by running allocation on a large Critical request, then create a new request and run allocation.
- **Expected result:** The request stays "Pending" with 0% fulfillment. Flash message says "Allocation complete — processed 0 request(s)."
- **Enforcement mechanism:** The bag query returns no rows and the loop does not execute.

#### Case: Partial Stock Available
- **Trigger:** Request for 500 ml but only 200 ml of compatible blood exists.
- **How to reproduce:** Create a request for 500 ml of a group with limited stock, run allocation.
- **Expected result:** Request becomes "Partially Fulfilled" at 40% (200/500 ml). The remaining 300 ml stays as the unfulfilled portion.
- **Enforcement mechanism:** The trg_update_req_allocated trigger sums all fulfillment log entries and sets "Partially Fulfilled" when total is between 0 and requested.

#### Case: Multiple Bags Needed for One Request
- **Trigger:** A request for 800 ml but the largest bag is 450 ml.
- **Expected result:** The system draws from multiple bags: takes 450 ml from the first, 350 ml from the second. Both bags show volume deductions in the audit trail.
- **Enforcement mechanism:** The allocation loop iterates through sorted bags until needed volume is fully allocated or bags are exhausted.

#### Case: Volume Guard — Over-Allocation Attempt
- **Trigger:** An attempt to allocate more volume than a bag contains (can only happen with direct SQL, not through the UI).
- **Expected result:** ABORT with message "VOLUME_GUARD."
- **Enforcement mechanism:** trg_fulfillment_volume_guard BEFORE INSERT trigger compares allocated amount against bag's current_volume_ml.

#### Case: Bag Auto-Expires When Fully Drained
- **Trigger:** Allocation takes the last remaining ml from a bag.
- **How to reproduce:** Observe a bag before and after allocation in the Detailed Inventory tab.
- **Expected result:** Bag status changes from "Available" to "Empty." The audit trail shows two entries: volume update and status update.
- **Enforcement mechanism:** trg_auto_expire_bag AFTER UPDATE trigger fires when current_volume_ml reaches 0.

#### Case: Repeated Allocation on Already-Fulfilled Requests
- **Trigger:** Click "Run Allocation Algorithm" multiple times after all requests are fulfilled.
- **Expected result:** Flash message says "Allocation complete — processed 0 request(s)." No data changes. The operation is idempotent.
- **Enforcement mechanism:** The query filters WHERE status IN ('Pending', 'Partially Fulfilled'), so fulfilled requests are skipped.

#### Case: Compatibility Fallback
- **Trigger:** A patient needs A+ blood but no A+ bags exist. A-, O+, and O- are available.
- **Expected result:** The allocation engine uses A- first (preference_rank 2), then O+ (rank 3), then O- (rank 4) — conserving rare O- blood.
- **Enforcement mechanism:** COMPATIBILITY_MATRIX table with preference_rank ordering.

#### Case: Incompatible Blood Group — No Match
- **Trigger:** A patient needs AB- blood but only A+, B+, O+ bags are in stock.
- **Expected result:** No allocation occurs. Request remains "Pending."
- **Enforcement mechanism:** The JOIN with COMPATIBILITY_MATRIX returns no rows because those donor groups are not compatible with AB-.

---

### 10.3 Component Tracking Edge Cases

#### Case: Component-Type Mismatch in Allocation
- **Trigger:** A request for "Red Blood Cells" when only "Whole Blood" bags exist.
- **Expected result:** No allocation occurs for this request.
- **Enforcement mechanism:** The allocation query filters AND bb.component_type = ? for the requested component.

#### Case: Split Donation Creates Correct Shelf Lives
- **Trigger:** A component-split donation is logged.
- **Expected result:** Red Blood Cells = 42 days, Platelets = 5 days, Plasma = 365 days.
- **How to verify:** Check the expiry dates in Detailed Inventory. A donation today should show Platelets expiring in 5 days and Plasma expiring in 365 days.

#### Case: Split Volumes Sum to Original
- **Trigger:** A 450 ml donation is split.
- **Expected result:** RBC (200) + Platelets (50) + Plasma (200) = 450 ml total across three bags, matching the original donation volume.

---

### 10.4 Domain Normalisation Edge Cases

#### Case: Invalid Blood Group Insertion
- **Trigger:** Attempt to INSERT a donor with blood_group = "Z+" directly via SQL.
- **Expected result:** "FOREIGN KEY constraint failed."
- **Enforcement mechanism:** BLOOD_GROUP_MASTER foreign key constraint on DONOR.blood_group.

#### Case: Invalid Urgency Level
- **Trigger:** Attempt to INSERT a request with urgency_level = "Emergency" via SQL.
- **Expected result:** "FOREIGN KEY constraint failed."
- **Enforcement mechanism:** URGENCY_LEVEL_MASTER foreign key constraint. Only "Normal" and "Critical" exist.

#### Case: Invalid Bag Status
- **Trigger:** Attempt to UPDATE a bag's status to "Destroyed" via SQL.
- **Expected result:** "FOREIGN KEY constraint failed."
- **Enforcement mechanism:** BAG_STATUS_MASTER foreign key. Valid statuses: Available, Empty, Expired, Quarantined.

#### Case: Invalid Component Type
- **Trigger:** Attempt to create a bag with component_type = "White Blood Cells" via SQL.
- **Expected result:** "FOREIGN KEY constraint failed."
- **Enforcement mechanism:** COMPONENT_MASTER foreign key constraint.

---

### 10.5 Soft Delete Edge Cases

#### Case: Deactivated Donor's Bags Remain in Inventory
- **Trigger:** Deactivate a donor who previously donated.
- **How to reproduce:** Click "Deactivate" next to a donor who has blood bags.
- **Expected result:** Donor disappears from the loyalty leaderboard. Their blood bags remain in inventory and can still be allocated to patients.
- **Enforcement mechanism:** Donor.is_active is set to 0. Blood bags are linked by donation_id, not directly filtered by donor status.

#### Case: Deactivated Hospital's Requests Remain Active
- **Trigger:** Deactivate a hospital that has pending requests.
- **Expected result:** The hospital disappears from the dropdown. Its pending requests remain in the waitlist and can still be allocated.

#### Case: Default State is Active
- **Trigger:** Register a new donor or hospital.
- **Expected result:** is_active defaults to 1 (active). No manual activation needed.

---

### 10.6 Audit Trail Edge Cases

#### Case: Audit Captures Old and New Values on Update
- **Trigger:** Any bag volume deduction during allocation.
- **How to verify:** Navigate to /audit after running allocation. Find a BLOOD_BAG UPDATE entry.
- **Expected result:** old_value shows previous status and volume, new_value shows updated status and volume.

#### Case: Cascading Audit from Single Allocation
- **Trigger:** A single allocation event on one bag.
- **Expected result:** Multiple audit entries: FULFILLMENT_LOG INSERT, TRANSFUSION_REQ UPDATE (status change), BLOOD_BAG UPDATE (volume deduction), and possibly a second BLOOD_BAG UPDATE (status to Empty). All from a single user action.

#### Case: Audit Log Grows Under Load
- **Trigger:** Process 50 donations and 30 requests through allocation.
- **Expected result:** Audit log contains hundreds of entries (verified by stress tests). No data loss or truncation.

---

### 10.7 Shortage Alert Edge Cases

#### Case: Zero Stock for a Blood Group
- **Trigger:** No available bags for O- blood exist.
- **Expected result:** Dashboard shows O- with "0 days supply left" and suggests eligible donors to contact.

#### Case: Sufficient Stock
- **Trigger:** Ample stock exists with low consumption.
- **Expected result:** That blood group does NOT appear in shortage alerts (projected days > 3).

#### Case: No Consumption History
- **Trigger:** A blood group has stock but has never been consumed (no FULFILLMENT_LOG entries).
- **Expected result:** Projected days = infinity. No shortage alert for that group.

---

### 10.8 Donor Loyalty Edge Cases

#### Case: Donor with Zero Donations
- **Trigger:** Register a new donor but do not log any donation.
- **Expected result:** Donor appears in leaderboard with 0 donations, 0 ml, but still has rare_bonus if applicable. Score = 0 + bonus.

#### Case: Rare Group Bonus Values
- **Trigger:** Compare donors of different blood groups.
- **Expected result:**
  - O-, AB-: +10 bonus
  - A-, B-: +5 bonus
  - A+, B+, AB+, O+: +0 bonus

#### Case: Eligible Donor Who Never Donated
- **Trigger:** A newly registered donor.
- **Expected result:** Shows green "Eligible" badge — they have no last_donation_date, so they are eligible by default.

#### Case: Inactive Donor Excluded from Eligible List
- **Trigger:** Deactivate a donor, then check shortage alerts for that blood group.
- **Expected result:** The deactivated donor does NOT appear in the "suggested donors to contact" list.

#### Case: get_eligible_donors_for_group Filters Correctly
- **Trigger:** Call with a specific blood group.
- **Expected result:** Only returns donors of that exact blood group who are active and eligible (56+ days since last donation or never donated).

---

### 10.9 Multi-Group Simultaneous Allocation

#### Case: Multiple Blood Groups All Requesting at Once
- **Trigger:** Requests for A+, B+, O-, AB+ all pending simultaneously.
- **Expected result:** Each request is matched independently against compatible bags. Critical requests are processed first regardless of blood group.

---

## Quick Demo Script (5-Minute Version)

For a rapid demonstration hitting all major features:

1. **Start fresh:** Run db_init.py, seed_demo.py, and main.py
2. **Dashboard:** Show Critical alerts, shortage forecast, expiring-soon, stock ticker, tabs
3. **Donor page:** Show loyalty leaderboard, try to donate for a recent donor — safety lock trigger fires
4. **Hospital page:** Show prioritised waitlist with progress bars
5. **Allocate:** Click "ALLOCATE RESOURCES NOW" on dashboard
6. **Results:** Show updated progress bars, fulfilled requests, empty bags
7. **Audit:** Navigate to /audit — show INSERT/UPDATE log entries
8. **Edge case:** Try re-donating (56-day lock), try re-allocating (idempotent), show empty bag auto-expire in audit

---

## Seed Data Summary

The seed_demo.py script creates:

| Entity | Count | Details |
|--------|-------|---------|
| Donors | 12 | All 8 blood groups covered, including duplicates for common groups |
| Hospitals | 4 | City General, Children's, Teaching, Emergency Centre |
| Whole-blood donations | 6 | 400-500ml each |
| Component-split donations | 3 | 450ml each = 3 bags each (RBC + Platelets + Plasma) |
| Transfusion requests | 8 | Mix of Normal and Critical, 150-400ml |
| Allocations | Auto | Smart allocation runs automatically |
| Expiring bag | 1 | One bag backdated to expire in 2 days |
| Soft-deleted donor | 1 | Donor #6 deactivated (bags preserved) |
| Loyalty demo | 1 | Donor #1 has 2 donations (score visible) |
