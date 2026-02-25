# Hospital Management System — Ultimate Live Demo Guide

This guide is designed for a **high-stakes live demonstration**. It covers setup, real-world scenarios, edge cases, and "under the hood" technical verification.

**Pre-requisites:**
*   A running **Docker** instance (for Redis).
*   A **Google Account** (Gmail) for testing email delivery.
*   **Python 3.10+** and `uv` installed.

---

## 📧 Setup Phase: Real Email Configuration

To demonstrate that emails are *actually* received, we will use a single Gmail account with **aliases** (e.g., `myname+doctor@gmail.com`). This avoids creating multiple accounts while treating them as unique users.

### 1. Configure Gmail App Password
1.  Go to [Google Account Security](https://myaccount.google.com/security).
2.  Enable **2-Step Verification**.
3.  Search for **"App passwords"**.
4.  Create a new app password named `HMS_Demo`.
5.  **Copy the 16-character password.**

### 2. Configure Environment
Stop any running servers. In your terminal, set these variables (or create a `.env` file):

**Windows (PowerShell):**
```powershell
$env:SMTP_SERVER="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USERNAME="your.real.email@gmail.com"
$env:SMTP_PASSWORD="your-16-char-app-password"
$env:FROM_EMAIL="your.real.email@gmail.com"
```

**Mac/Linux:**
```bash
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your.real.email@gmail.com"
export SMTP_PASSWORD="your-16-char-app-password"
export FROM_EMAIL="your.real.email@gmail.com"
```

### 3. Start the System
Open **three separate terminals** and run these commands:

*   **Terminal 1 (Web App):**
    ```bash
    uv run python app.py
    ```
*   **Terminal 2 (Celery Worker - Email Sender):**
    *   *Windows:* `uv run celery -A backend.celery_config worker --loglevel=info --pool=solo`
    *   *Mac/Linux:* `uv run celery -A backend.celery_config worker --loglevel=info`
*   **Terminal 3 (Celery Scheduler):**
    ```bash
    uv run celery -A backend.celery_config beat --loglevel=info
    ```
*   **Docker (Redis):**
    ```bash
    docker run --name hms-redis -p 6379:6379 -d redis
    ```

---

## 🏥 Phase 1: Admin Infrastructure & Doctor Setup

**Goal:** Create a robust hospital structure and demonstrate Admin capabilities.

### 1.1 Login & Dashboard
*   **URL:** `http://localhost:5000`
*   **Creds:** `admin` / `admin`
*   **Expected Result:** Dashboard loads. 0 Doctors, 0 Patients.

### 1.2 Create Departments
*   Navigate to **Doctors** tab -> **Departments**.
*   **Add "Neurology":**
    *   Name: `Neurology`
    *   Description: `Brain and nervous system`
    *   Click **Save**.
*   **Add "General Surgery":**
    *   Name: `General Surgery`
    *   Description: `Surgical interventions`
    *   Click **Save**.
*   **Expected Result:** Both departments appear in the list.

### 1.3 Create Dr. Raj Malhotra (The "Standard" Doctor)
*   Navigate to **Add Doctor**.
*   **Details:**
    *   Name: `Dr. Raj Malhotra`
    *   Username: `drraj`
    *   Password: `password`
    *   Email: `your.real.email+drraj@gmail.com`  <-- **Use alias!**
    *   Phone: `9876543210`
    *   Department: `Neurology`
    *   **Availability:** Mon, Tue, Wed, Thu, Fri
    *   **Time:** `09:00` - `17:00`
    *   **Slot:** `30` mins
    *   **Fee:** `800`
    *   **Bio:** `Expert Neurologist with 10 years experience.`
    *   **Notifications:** Checked.
*   Click **Save Doctor**.

### 1.4 Create Dr. Emily Chen (The "Restricted" Doctor)
*This setup is crucial for demonstrating slot conflicts later.*
*   Navigate to **Add Doctor**.
*   **Details:**
    *   Name: `Dr. Emily Chen`
    *   Username: `dremily`
    *   Password: `password`
    *   Email: `your.real.email+dremily@gmail.com`
    *   Department: `General Surgery`
    *   **Availability:** **Mon, Wed** (Only!)
    *   **Time:** `10:00` - `12:00` (Only 2 hours!)
    *   **Slot:** `60` mins
    *   **Fee:** `1500`
*   Click **Save Doctor**.

### 1.5 Admin Edit Capability (Modify Dr. Raj)
*   Find **Dr. Raj Malhotra** in the list.
*   Click **Edit**.
*   Change **Fee** to `900`.
*   Change **Phone** to `9998887777`.
*   Click **Save**.
*   **Expected Result:** Table reflects fee `₹900` and updated phone.

*   **Logout**.

---

## 🧑‍🤝‍🧑 Phase 2: Patient Journey (Rahul Sharma)

**Goal:** Regular flow - Registration, Booking, Payment, Profile Update.

### 2.1 Registration
*   Click **"Register here"** (Patient).
*   **Details:**
    *   Name: `Rahul Sharma`
    *   Username: `rahul`
    *   Email: `your.real.email+rahul@gmail.com` <-- **Use alias!**
    *   Password: `password`
*   Click **Register**.
*   **Expected Result:** Auto-redirect to Login or "Registration Successful". Login as `rahul`.

### 2.2 Booking Dr. Raj
*   Go to **Book Appointment**.
*   Filter by `Neurology`. Select **Dr. Raj Malhotra**.
*   Select **Tomorrow's Date**.
*   Pick **10:00 AM**.
*   Click **Confirm Booking**.
*   **Expected Result:** Success message.

### 2.3 Payment
*   Go to **My Appointments**. Status is "Booked".
*   Click **Pay** (₹900).
*   Select **Credit Card**, enter `4242...`, click **Submit**.
*   **Expected Result:** Status becomes "Paid".

### 2.4 Comprehensive Profile Update
*   Go to **Profile**.
*   Change **Address** to `123 Main St, Delhi`.
*   Change **Notification Prefs**: Check **Email** and **SMS**.
*   Click **Save Changes**.
*   **Expected Result:** Page reloads, preferences are persisted (verify by refreshing page).

*   **Logout**.

---

## 🚫 Phase 3: The "Conflict" & Availability Edge Cases

**Goal:** Demonstrate system robustness against double-booking and schedule changes.

### 3.1 Register Patient 2 (Priya Patel)
*   Register new patient:
    *   Name: `Priya Patel`
    *   Username: `priya`
    *   Email: `your.real.email+priya@gmail.com`
*   Login as `priya`.

### 3.2 The "No Slots" Scenario (Dr. Emily)
*   Go to **Book Appointment**.
*   Select **General Surgery** -> **Dr. Emily Chen**.
*   Select a **Tuesday** (She works Mon/Wed).
*   **Expected Result:** "No slots available" message or empty list.
*   Select a **Monday**.
*   **Expected Result:** Only `10:00` and `11:00` slots are visible. Book `10:00`.

### 3.3 The "Double Booking" Attempt
*   *Setup:* Priya just booked Dr. Emily at Mon 10:00.
*   *Action:* **Open an Incognito Window**. Login as **Rahul Sharma**.
*   Go to Book Dr. Emily for the **same Monday**.
*   **Expected Result:** The `10:00` slot is **GONE**. Only `11:00` is left.
*   *Action:* Rahul books `11:00`.

### 3.4 The "Doctor Unavailable" Twist
*   **Login as Dr. Raj Malhotra** (`drraj`/`password`).
*   Go to **Availability** Tab.
*   **Scenario:** Rahul booked Dr. Raj for *Tomorrow*. Dr. Raj wants to take Tomorrow off.
*   **Action:** Uncheck *Tomorrow's weekday*.
*   Click **Update Availability**.
*   **Verification:**
    *   Login as **Priya Patel**.
    *   Try to book Dr. Raj for *Tomorrow*.
    *   **Expected Result:** No slots available for that day.
    *   **Crucial Check:** Login as **Rahul Sharma** (who already booked). Go to **My Appointments**.
    *   **Expected Result:** Rahul's appointment **still exists**. (Existing bookings are honored; only new ones blocked).

---

## 🩺 Phase 4: Clinical Workflow & Record Edits

**Goal:** Complete care cycle and demonstrate record mutability.

### 4.1 Treatment (Dr. Raj)
*   Login as `drraj`.
*   Go to **Appointments**. See **Rahul Sharma** (Green/Upcoming).
*   Click **Complete**.
*   **Initial Entry:**
    *   Diagnosis: `Migraine`
    *   Prescription: `Paracetamol`
    *   Notes: `Rest advised.`
*   Click **Save**.

### 4.2 The "Correction" (Edit Medical Record)
*   *Scenario:* Doctor realizes they made a typo.
*   Go to **My Patients** tab.
*   Search `Rahul`. Click **View History**.
*   See the record. Click **Edit Treatment**.
*   **Update:**
    *   Diagnosis: `Severe Migraine` (Changed)
    *   Prescription: `Sumatriptan 50mg` (Changed)
    *   Notes: `Rest advised. Avoid bright lights.` (Appended)
*   Click **Save**.
*   **Expected Result:** History updates immediately.

### 4.3 Verify Patient View
*   Login as `rahul`.
*   Go to **My Appointments**.
*   Expand the **Completed** appointment.
*   **Expected Result:** Sees "Severe Migraine" and "Sumatriptan".

---

## 📨 Phase 5: LIVE Email & Report Triggering (The "Teacher" Moment)

**Goal:** Prove background jobs work by forcing them to run *now*.

### 5.1 Force Daily Reminders
*   *Context:* Rahul has an appointment tomorrow. We want to send the reminder *now* to prove it works.
*   **Action:** Open a new terminal. Run:
    ```bash
    uv run flask shell
    ```
*   **Paste this code:**
    ```python
    from backend.tasks import send_daily_reminders
    # Force task to run immediately
    send_daily_reminders.delay()
    ```
*   **Watch Terminal 2 (Worker):**
    *   **Expected Log:** `[EMAIL] To: your.real.email+rahul@gmail.com ... Subject: Hospital Appointment Reminder`
*   **Verify Inbox:** Check your real Gmail (Rahul alias). You should see the email.

### 5.2 Force Monthly Report (Code Modification)
*   *Context:* Monthly reports run on the 1st of the month for the *previous* month. Since we just created data *today*, a standard run would be empty. We will hack the code live to include *today*.
*   **Action:** Open `backend/tasks.py` in your editor.
*   **Locate:** `send_monthly_reports` function (around line 110).
*   **Modify:**
    *   *Change this:*
        ```python
        prev_month_start = first_day_of_previous.strftime("%Y-%m-%d")
        prev_month_end = last_day_of_previous.strftime("%Y-%m-%d")
        ```
    *   *To this (Hardcode today's month):*
        ```python
        # LIVE DEMO HACK
        prev_month_start = "2023-01-01" # Set to way back
        prev_month_end = "2030-12-31"   # Set to future
        prev_month_name = "LIVE DEMO REPORT"
        ```
*   **Action:** Save the file. (Celery worker usually auto-reloads, but restart Terminal 2 if unsure).
*   **Trigger:** In your `flask shell` window:
    ```python
    from backend.tasks import send_monthly_reports
    send_monthly_reports.delay()
    ```
*   **Watch Terminal 2:**
    *   **Expected Log:** `[EMAIL] To: your.real.email+drraj@gmail.com ... Monthly Activity Report`
*   **Verify Inbox:** Check Dr. Raj's email. You should see a PDF/HTML report listing Rahul's treatment.

---

## 🔧 Phase 6: Admin Maintenance & Cleanup

**Goal:** Financial integrity and data removal.

### 6.1 Refund Process
*   Login as `admin`.
*   Go to **Appointments**.
*   Filter Status: `Booked`. Find **Priya Patel's** appointment with Dr. Emily.
*   Click **Cancel**.
*   Go to **Payments** tab.
*   **Expected Result:**
    *   See original `+1500` payment (Completed).
    *   See new `-1500` payment (Refunded).
    *   **Net Total** at bottom should decrease.

### 6.2 Delete Doctor (Cascading)
*   Go to **Doctors**.
*   Find **Dr. Emily Chen**.
*   Click **Delete**. Confirm.
*   **Expected Result:** Dr. Emily is gone.
*   *Verification:* Go to **Appointments**. Her appointments should be gone (or archived/nullified depending on DB cascade settings).

---

## 🕵️ Phase 7: Technical Verification (Redis)

**Goal:** Show the "Engine Room".

1.  Open terminal.
2.  **View All Cache Keys:**
    ```bash
    docker exec -it hms-redis redis-cli KEYS *
    ```
    *   **Expected Output:** List of keys like `flask_cache_admin_stats`, `flask_cache_all_doctors`.
3.  **Inspect Specific Cache (e.g., Admin Stats):**
    ```bash
    docker exec -it hms-redis redis-cli GET flask_cache_admin_stats
    ```
    *   **Expected Output:** Binary/Pickled string (starts with `\x80\x04...`). This proves data is cached.
4.  **Flush Cache (Live Test):**
    ```bash
    docker exec -it hms-redis redis-cli FLUSHALL
    ```
    *   Go to Admin Dashboard -> Refresh.
    *   **Result:** It loads slightly slower (re-fetching from DB) and keys reappear in Redis.

---

## ✅ Demo Summary Checklist
- [ ] Emails received in real Gmail inbox.
- [ ] "No Slots" / "Double Booking" blocked successfully.
- [ ] Doctor availability update respected (new bookings blocked, old kept).
- [ ] Medical record edited and verified by patient.
- [ ] Monthly Report force-sent via code hack.
- [ ] Redis keys inspected and flushed.
