# Hospital Management System — Live Demo Guide

A step-by-step walkthrough for demonstrating every feature, edge case, and vulnerability of the system. All instructions are **Windows-only**.

**Pre-requisites:**

- **Docker Desktop** for Windows (for Redis).
- The `.env` file at the project root is already configured:
  ```
  SMTP_USERNAME=hms238537@gmail.com
  SMTP_PASSWORD=ugkn nhym khpw wzet
  FROM_EMAIL=hms238537@gmail.com
  ```

> **Gmail Alias Trick:** Gmail ignores everything after a `+` sign. So `hms238537+drwilson@gmail.com` still delivers to `hms238537@gmail.com`. We use this to give each demo user a unique email while receiving everything in one inbox.

---

## Start the System

Open **four separate PowerShell terminals** and run these commands:

1. **Redis (Docker):**
   ```powershell
   docker run --name hms-redis -p 6379:6379 -d redis
   ```
2. **Web App (Terminal 1):**
   ```powershell
   uv run python app.py
   ```
3. **Celery Worker (Terminal 2):**
   ```powershell
   uv run celery -A backend.celery_config worker --loglevel=info --pool=solo
   ```
4. **Celery Beat Scheduler (Terminal 3):**
   ```powershell
   uv run celery -A backend.celery_config beat --loglevel=info
   ```

Open your browser to **http://localhost:5000**.

---

## Phase 1: Admin Infrastructure & Doctor Setup

**Goal:** Build the hospital structure, create departments and doctors. Demonstrate Admin-only capabilities.

### 1.1 Login as Admin

- **URL:** `http://localhost:5000`
- **Credentials:** `admin` / `admin`
- **Expected:** Dashboard loads showing 0 Doctors, 0 Patients.

### 1.2 Create Departments

Navigate to **Doctors** tab → **Departments**.

| Name             | Description                  |
| ---------------- | ---------------------------- |
| Neurology        | Brain and nervous system     |
| General Surgery  | Surgical interventions       |

Click **Save** for each. Both should appear in the department list.

### 1.3 Create Dr. Marcus Wilson (The "Standard" Doctor)

Navigate to **Add Doctor**.

| Field            | Value                                 |
| ---------------- | ------------------------------------- |
| Name             | `Dr. Marcus Wilson`                   |
| Username         | `drwilson`                            |
| Password         | `password`                            |
| Email            | `hms238537+drwilson@gmail.com`        |
| Phone            | `5551234567`                          |
| Department       | Neurology                             |
| Availability     | Mon, Tue, Wed, Thu, Fri               |
| Start Time       | `09:00`                               |
| End Time         | `17:00`                               |
| Slot Duration    | `30` minutes                          |
| Fee              | `800`                                 |
| Bio              | `Expert Neurologist with 10 years of experience.` |
| Notifications    | ✅ Checked                            |

Click **Save Doctor**.

### 1.4 Create Dr. Nora Fletcher (The "Restricted" Doctor)

*This limited schedule is crucial for demonstrating slot conflicts later.*

| Field            | Value                                 |
| ---------------- | ------------------------------------- |
| Name             | `Dr. Nora Fletcher`                   |
| Username         | `drnora`                              |
| Password         | `password`                            |
| Email            | `hms238537+drnora@gmail.com`          |
| Phone            | `5559876543`                          |
| Department       | General Surgery                       |
| Availability     | **Mon, Wed only**                     |
| Start Time       | `10:00`                               |
| End Time         | `12:00` (only 2 hours!)               |
| Slot Duration    | `60` minutes                          |
| Fee              | `1500`                                |
| Notifications    | ✅ Checked                            |

Click **Save Doctor**.

### 1.5 Admin Edit Capability

- Find **Dr. Marcus Wilson** in the list. Click **Edit**.
- Change **Fee** to `900`.
- Change **Phone** to `5554443322`.
- Click **Save**.
- **Expected:** Table reflects fee `₹900` and the updated phone number.

### 1.6 Edge Case — Duplicate Department Name

- Try adding another department named `Neurology`.
- **Expected:** Error message — department name must be unique.

### 1.7 Edge Case — Delete Department with Attached Doctor

- Try deleting the `Neurology` department.
- **Expected:** Error — cannot delete a department that has doctors assigned to it.

**Logout.**

---

## Phase 2: Patient Journey (Oliver Grant)

**Goal:** Complete patient flow — Registration, Booking, Payment, Profile Update, CSV Export.

### 2.1 Registration

- Click **"Register here"** on the login page.
- Fill in:

| Field    | Value                            |
| -------- | -------------------------------- |
| Name     | `Oliver Grant`                   |
| Username | `oliver`                         |
| Email    | `hms238537+oliver@gmail.com`     |
| Password | `password`                       |

- Click **Register**.
- **Expected:** Redirected to Login or shown "Registration Successful". Login as `oliver`.

### 2.2 Book Appointment with Dr. Wilson

- Go to **Book Appointment**.
- Filter by `Neurology`. Select **Dr. Marcus Wilson**.
- Select **tomorrow's date** (must be a weekday Mon–Fri).
- Pick the **10:00 AM** slot.
- Click **Confirm Booking**.
- **Expected:** Success message.

### 2.3 Payment

- Go to **My Appointments**. Status shows "Booked".
- Click **Pay** (₹900).
- Select **Credit Card**, enter `4242424242424242`, click **Submit**.
- **Expected:** Status changes to "Paid".

### 2.4 Profile Update

- Go to **Profile**.
- Change **Address** to `47 Elm Street`.
- **Notice:** Email notification is always on (checkbox is disabled, checked).
- Click **Save Changes**.
- **Expected:** Page reflects the updated address on refresh.

### 2.5 CSV Export

- Go to **Export** tab (or click **Request CSV Export**).
- Click **Export Treatments**.
- **Expected:** Export job appears with status "processing" → "completed".
- Click **Download** to get the CSV file.
- Open it — it should list all appointments for Oliver.

### 2.6 Edge Case — Duplicate Registration

- Logout. Try registering another account with username `oliver`.
- **Expected:** Error — username already exists.

### 2.7 Edge Case — Duplicate Email

- Try registering with a different username but email `hms238537+oliver@gmail.com`.
- **Expected:** Error — email already registered.

### 2.8 Edge Case — Registration Without Email

- Try registering without providing an email.
- **Expected:** Error — email is required.

---

## Phase 3: Conflict & Availability Edge Cases

**Goal:** Demonstrate that the system blocks double-booking and respects schedule changes.

### 3.1 Register Second Patient (Clara Bishop)

- Register:

| Field    | Value                            |
| -------- | -------------------------------- |
| Name     | `Clara Bishop`                   |
| Username | `clara`                          |
| Email    | `hms238537+clara@gmail.com`      |
| Password | `password`                       |

- Login as `clara`.

### 3.2 The "No Slots" Scenario

- Go to **Book Appointment** → **General Surgery** → **Dr. Nora Fletcher**.
- Select a **Tuesday** or **Thursday** (she only works Mon/Wed).
- **Expected:** "No slots available" or empty slot list.
- Select a **Monday**.
- **Expected:** Only `10:00` and `11:00` slots visible. Book **10:00**.

### 3.3 The "Double Booking" Attempt

- **Setup:** Clara just booked Dr. Nora at Monday 10:00.
- **Action:** Open an **InPrivate/Incognito** window. Login as **Oliver Grant** (`oliver` / `password`).
- Navigate to Book → General Surgery → Dr. Nora Fletcher → same Monday.
- **Expected:** The `10:00` slot is **gone**. Only `11:00` remains.
- Oliver books `11:00`.

### 3.4 Concurrency Stress Test (Race Condition)

*Demonstrate that the system handles concurrent booking attempts for the same slot.*

- Open **two separate InPrivate/Incognito windows** side by side.
- In **Window A:** Login as `oliver`. Navigate to Book → Dr. Wilson → pick a future date → select `09:00` slot.
- In **Window B:** Login as `clara`. Navigate to Book → Dr. Wilson → same date → select `09:00` slot.
- **Simultaneously** click **Confirm Booking** in both windows.
- **Expected:** One succeeds, the other gets an error ("Slot no longer available" or "already booked"). The system must not create two appointments for the same slot.
- **Verify:** Login as admin → Appointments → confirm only one `09:00` booking exists for that doctor and date.

### 3.5 The "Doctor Unavailable" Twist

- **Login as Dr. Marcus Wilson** (`drwilson` / `password`).
- Go to **Availability** tab.
- **Scenario:** Oliver booked Dr. Wilson for tomorrow. Dr. Wilson wants to take tomorrow off.
- **Action:** Uncheck tomorrow's weekday.
- Click **Update Availability**.
- **Verification:**
  - Login as **Clara Bishop**. Try to book Dr. Wilson for tomorrow.
  - **Expected:** No slots available for that day.
  - **Crucial Check:** Login as **Oliver Grant**. Go to **My Appointments**.
  - **Expected:** Oliver's existing appointment **still exists**. Existing bookings are honored; only new ones are blocked.

### 3.7 Edge Case — Patient Cancellation

- Login as **Oliver Grant**.
- Go to **My Appointments**. Find a "Booked" appointment.
- Click **Cancel**.
- **Expected:** Status changes to "Cancelled". The slot should become available again for other patients.

### 3.8 Edge Case — Cancel a Paid Appointment

- Login as **Oliver Grant** (or book + pay for a new appointment first).
- Try cancelling an appointment that has already been paid.
- **Expected:** Cancellation should succeed — a refund record is created automatically.

---

## Phase 4: Clinical Workflow & Record Management

**Goal:** Complete a care cycle and demonstrate treatment record creation and editing.

### 4.1 Complete Appointment (Dr. Wilson)

- Login as `drwilson`.
- Go to **Appointments**. See **Oliver Grant** (upcoming).
- Click **Complete**.
- Fill in:

| Field        | Value                       |
| ------------ | --------------------------- |
| Diagnosis    | `Migraine`                  |
| Prescription | `Paracetamol 500mg`         |
| Notes        | `Rest advised for 2 days.`  |

- Click **Save**.
- **Expected:** Appointment status changes to "Completed".

### 4.2 Edit Treatment Record (The "Correction")

*Scenario: Doctor realises they made a mistake.*

- Go to **My Patients** tab.
- Search `Oliver`. Click **View History**.
- Click **Edit Treatment** on the record.
- Update:

| Field        | Value                                          |
| ------------ | ---------------------------------------------- |
| Diagnosis    | `Chronic Migraine` (changed)                   |
| Prescription | `Sumatriptan 50mg` (changed)                   |
| Notes        | `Rest advised. Avoid bright lights.` (appended) |

- Click **Save**.
- **Expected:** History shows the updated values immediately.

### 4.3 Generate Patient History PDF

- Still logged in as `drwilson`.
- Go to **My Patients** → find Oliver → click **Download PDF**.
- **Expected:** A PDF file downloads containing Oliver's full treatment history in formatted layout (ReportLab-generated).

### 4.4 Verify Patient View

- Login as `oliver`.
- Go to **My Appointments** → expand the Completed appointment.
- **Expected:** Shows "Chronic Migraine" and "Sumatriptan 50mg" (the corrected values).

### 4.5 Edge Case — Doctor Viewing Another Doctor's Patients

- Login as `drnora`. Go to **My Patients**.
- **Expected:** Dr. Nora only sees her own patients, not Dr. Wilson's.

---

## Phase 5: Live Email Delivery Demonstration

**Goal:** Prove background email jobs work by triggering them manually and checking the real inbox.

### 5.1 Force Daily Reminders

*Context: Oliver has a "Booked" appointment for today/tomorrow. We trigger the reminder now.*

- Open a new PowerShell terminal. Run:
  ```powershell
  uv run flask shell
  ```
- Paste this code:
  ```python
  from backend.tasks import send_daily_reminders
  send_daily_reminders.delay()
  ```
- **Watch Terminal 2 (Celery Worker):**
  - **Expected Log:** `Task backend.tasks.send_daily_reminders succeeded`
- **Check Gmail inbox** (hms238537@gmail.com):
  - Look for an email to `hms238537+oliver@gmail.com` with subject "Hospital Appointment Reminder".
  - The email body should contain the doctor name, department, date, and time.

### 5.2 Force Monthly Doctor Report

*Context: Monthly reports run on the 1st of the month for the previous month. Since demo data was created today, a standard run would be empty. We temporarily widen the date range.*

1. Open `backend/tasks.py` in your editor.
2. Find the `send_monthly_reports` function (around line 130).
3. **Temporarily change:**
   ```python
   prev_month_start = first_day_of_previous.strftime("%Y-%m-%d")
   prev_month_end = last_day_of_previous.strftime("%Y-%m-%d")
   ```
   **To:**
   ```python
   # LIVE DEMO HACK — include all dates
   prev_month_start = "2020-01-01"
   prev_month_end = "2030-12-31"
   prev_month_name = "LIVE DEMO REPORT"
   ```
4. Save the file. Restart the Celery worker (Terminal 2) to pick up the change.
5. In the `flask shell` window:
   ```python
   from backend.tasks import send_monthly_reports
   send_monthly_reports.delay()
   ```
6. **Watch Terminal 2:**
   - **Expected Log:** `Task backend.tasks.send_monthly_reports succeeded`
7. **Check Gmail inbox:**
   - Look for an email to `hms238537+drwilson@gmail.com` with subject containing "Monthly Activity Report".
   - The report should list Oliver's treatment details.

> **Important:** Revert the code change in `tasks.py` after the demo.

### 5.3 Email Alias Demonstration

*Show the audience how all emails land in one inbox despite different "To" addresses.*

- Open Gmail (hms238537@gmail.com) → search for `to:hms238537+oliver` and `to:hms238537+drwilson`.
- Demonstrate that different `+alias` suffixes all arrive in the same inbox.
- This proves the system sends emails to individual addresses while keeping the demo simple.

### 5.4 Edge Case — Email Delivery When SMTP Is Not Configured

- Stop the Celery worker. Remove `SMTP_USERNAME` from `.env` (or clear it).
- Restart the app and worker.
- Trigger `send_daily_reminders.delay()` again.
- **Expected:** Emails are logged to the **console** (Terminal 2) instead of actually being sent. The line begins with `[EMAIL] To:`.
- **Point:** The system degrades gracefully — no crash, just a fallback.
- Restore `.env` and restart after demonstrating.

---

## Phase 6: Admin Maintenance & Financial Integrity

**Goal:** Demonstrate payments dashboard, refund flow, and cascading deletions.

### 6.1 Admin Payments Dashboard

- Login as `admin`.
- Go to **Payments** tab.
- **Expected:** See all payment records — amounts, statuses (Completed, Refunded), associated patients and doctors.

### 6.2 Refund Process

- Go to **Appointments**.
- Find **Clara Bishop's** appointment with Dr. Nora Fletcher (status: Booked).
- Click **Cancel**.
- Go to **Payments** tab.
- **Expected:**
  - Original payment `+1500` (Completed).
  - New refund entry `-1500` (Refunded).
  - **Net total** at bottom should decrease by 1500.

### 6.3 Delete a Doctor (Cascading Effect)

- Go to **Doctors**.
- Find **Dr. Nora Fletcher**. Click **Delete**. Confirm.
- **Expected:** Dr. Nora is removed.
- Go to **Appointments** tab. Her appointments should be gone (cascading delete).
- Go to **Departments**. "General Surgery" still exists (department is not deleted).

### 6.4 Delete a Patient

- Go to **Patients**.
- Find a patient. Click **Delete**. Confirm.
- **Expected:** Patient is removed along with their appointments and payment records (cascading).

### 6.5 Admin Edit Patient

- Go to **Patients**. Find **Oliver Grant**. Click **Edit**.
- Change name or phone number. Click **Save**.
- **Expected:** Updated values appear in the table.

---

## Phase 7: Doctor Dashboard Features

**Goal:** Demonstrate doctor-specific features beyond basic appointment management.

### 7.1 Monthly Report View (In-App)

- Login as `drwilson`.
- Navigate to **Monthly Report** tab.
- Select current month/year.
- **Expected:** A summary of appointments, patients seen, and treatments given this month.

### 7.2 Patient Summary

- Go to **My Patients** → click on a patient → **View Summary**.
- **Expected:** An aggregated view of the patient's visit history with this specific doctor.

### 7.3 Payments View

- Go to **Payments** tab.
- **Expected:** Dr. Wilson sees payments for his own appointments only (not other doctors' payments).

---

## Phase 8: Caching & Performance Verification (Redis)

**Goal:** Show the caching layer and demonstrate its effect.

### 8.1 View Cache Keys

```powershell
docker exec -it hms-redis redis-cli KEYS *
```

**Expected:** Keys like `flask_cache_admin_stats`, `flask_cache_all_doctors`, etc.

### 8.2 Inspect a Cached Value

```powershell
docker exec -it hms-redis redis-cli GET flask_cache_admin_stats
```

**Expected:** Binary/pickled data (starts with `\x80\x04...`). This proves the response is being served from cache.

### 8.3 Cache Invalidation Test

```powershell
docker exec -it hms-redis redis-cli FLUSHALL
```

- Go to Admin Dashboard → refresh the page.
- **Expected:** Page loads (slightly slower the first time as it repopulates the cache). Run `KEYS *` again to see keys reappear.

### 8.4 Cache Hit/Miss Observation

- Load the Admin Dashboard.
- Immediately reload without changes.
- **Expected:** Second load is faster (served from Redis cache). You can verify by checking the network tab — response times should be shorter.

---

## Phase 9: Security & Vulnerability Demonstrations

**Goal:** Show that security controls are in place and functioning.

### 9.1 Unauthorized Access — Patient Hits Admin API

- Login as `oliver` (patient).
- Open browser DevTools → Console. Run:
  ```javascript
  fetch('/admin/stats').then(r => r.json()).then(console.log)
  ```
- **Expected:** 403 Forbidden or redirect to login. Patient cannot access admin routes.

### 9.2 Unauthorized Access — Patient Hits Doctor API

- Still logged in as `oliver`. Run:
  ```javascript
  fetch('/doctor/appointments').then(r => r.json()).then(console.log)
  ```
- **Expected:** 403 Forbidden. Patient cannot access doctor routes.

### 9.3 Unauthorized Access — Doctor Hits Admin API

- Login as `drwilson`. Run:
  ```javascript
  fetch('/admin/stats').then(r => r.json()).then(console.log)
  ```
- **Expected:** 403 Forbidden. Doctor cannot access admin routes.

### 9.4 Session Hijacking Attempt

- Login as `oliver`. Copy the session cookie value from DevTools → Application → Cookies.
- Open an InPrivate window. Set the cookie manually.
- **Expected:** Flask-Security validates the session server-side. The session cookie has `HttpOnly` and `SameSite` flags.

### 9.5 CSRF-Like Request Without Session

- Open an InPrivate window (not logged in). Try:
  ```javascript
  fetch('/appointments', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({doctor_id:1, date:'2025-01-01', time:'10:00'})}).then(r => r.json()).then(console.log)
  ```
- **Expected:** 401 Unauthorized or login required.

### 9.6 SQL Injection Attempt

- On the login page, try:
  - Username: `admin' OR '1'='1`
  - Password: `anything`
- **Expected:** Login fails. SQLAlchemy uses parameterised queries — injection does not work.

### 9.7 XSS Attempt

- Login as a patient. Go to **Profile**.
- Set Address to: `<script>alert('XSS')</script>`
- Save and reload.
- **Expected:** The script tag is rendered as plain text (escaped), not executed. Vue.js escapes output by default.

### 9.8 Integer Overflow / Invalid ID

- Try accessing: `http://localhost:5000/doctors/99999/availability`
- **Expected:** 404 or empty result — no crash, no stack trace exposed.

### 9.9 Empty / Malformed Request Bodies

- From DevTools console:
  ```javascript
  fetch('/appointments', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}).then(r=>r.json()).then(console.log)
  ```
- **Expected:** 400 Bad Request with a descriptive error listing missing fields.

### 9.10 Password Not Exposed in API Responses

- Login as admin. Go to **Doctors** or **Patients** tab.
- Open DevTools → Network. Inspect the JSON response for `/admin/doctors` or `/admin/patients`.
- **Expected:** No `password` or `password_hash` field in the response JSON.

---

## Phase 10: Stress Test (Optional)

**Goal:** Verify the system handles load gracefully.

### 10.1 Run the Built-In Stress Test

```powershell
uv run python scripts/stress_test.py
```

- This script fires concurrent requests at the booking endpoint.
- **Expected:** The system responds without crashing. Some requests may be rejected (slot conflicts), which is correct behaviour.
- Check that no duplicate bookings were created afterwards.

---

## Demo Summary Checklist

- [ ] Emails received in real Gmail inbox (reminder + monthly report)
- [ ] Gmail alias trick demonstrated (multiple users, one inbox)
- [ ] Email fallback to console when SMTP not configured
- [ ] "No Slots" on wrong weekday for restricted doctor
- [ ] "Double Booking" blocked — taken slot disappears
- [ ] Concurrency race condition handled (only one booking wins)
- [ ] Doctor availability change blocks new bookings but preserves existing
- [ ] Past date booking rejected
- [ ] Patient cancellation and refund flow working
- [ ] Medical record created, edited, and verified by patient
- [ ] Patient history PDF generated
- [ ] CSV export completed and downloadable
- [ ] Redis cache keys visible, cache flush and repopulation demonstrated
- [ ] RBAC enforced — patient/doctor/admin cannot cross-access
- [ ] SQL injection blocked
- [ ] XSS attempt escaped
- [ ] Empty/malformed requests return descriptive errors
- [ ] Passwords not exposed in API responses
- [ ] Admin can create, edit, delete doctors and patients
- [ ] Duplicate department name rejected
