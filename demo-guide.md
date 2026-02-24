# Hospital Management System — Demo & Testing Guide

This document provides step-by-step instructions for demonstrating and manually testing every feature of the Hospital Management System. Each section specifies exact values to enter in every field, which buttons to click, and what to verify at each stage.

---

## Table of Contents

1. [Pre-Demo Setup](#1-pre-demo-setup)
2. [Admin Walkthrough](#2-admin-walkthrough)
   - 2.1 Login as Admin
   - 2.2 Manage Departments
   - 2.3 Create a Doctor
   - 2.4 Edit a Doctor's Consultation Fee
   - 2.5 View All Appointments
   - 2.6 View All Payments
   - 2.7 Admin Statistics Dashboard
   - 2.8 Manage Patients
3. [Patient Walkthrough](#3-patient-walkthrough)
   - 3.1 Register a Patient Account
   - 3.2 Login as Patient
   - 3.3 Browse Doctors and Book an Appointment
   - 3.4 Pay for the Appointment
   - 3.5 View Appointment and Treatment History
   - 3.6 Update Profile and Notification Preferences
   - 3.7 Export Treatment History
   - 3.8 Cancel an Appointment
4. [Doctor Walkthrough](#4-doctor-walkthrough)
   - 4.1 Login as Doctor
   - 4.2 View Upcoming Appointments
   - 4.3 Complete a Consultation
   - 4.4 Add a Follow-Up Appointment
   - 4.5 Edit a Past Treatment Record
   - 4.6 View My Patients
   - 4.7 Update Availability
   - 4.8 Download Monthly Report
   - 4.9 View Earnings
5. [Cross-Role Feature Verification](#5-cross-role-feature-verification)
6. [Error and Edge Case Testing](#6-error-and-edge-case-testing)

---

## 1. Pre-Demo Setup

### 1.1 Start Redis (Docker)

```
docker run --name hms-redis -p 6379:6379 -d redis
```

Or if already created:

```
docker start hms-redis
```

### 1.2 Start the Flask Application

Open a terminal in the project root and run:

```bash
uv run python app.py
```

Expected output: `Running on http://127.0.0.1:5000`

The application automatically:
- Creates `instance/hospital.db` (SQLite database)
- Creates default departments: Cardiology, Neurology, Orthopaedics, General Medicine, Paediatrics
- Creates admin user (username: `admin`, password: `admin`)

### 1.3 (Optional) Start Background Workers

For email reminders and CSV export notifications:

```bash
# Terminal 2
uv run celery -A backend.celery_config worker --loglevel=info

# Terminal 3
uv run celery -A backend.celery_config beat --loglevel=info
```

### 1.4 Open the Application

Navigate to: **http://localhost:5000**

You should see the Hospital Management System login page with Admin / Doctor / Patient role tabs.

---

## 2. Admin Walkthrough

### 2.1 Login as Admin

1. On the login page, click the **Admin** tab.
2. Enter credentials:
   - **Username:** `admin`
   - **Password:** `admin`
3. Click **Login**.
4. **Verify:** Admin dashboard loads with tabs: Stats, Doctors, Patients, Appointments, Payments.

---

### 2.2 Manage Departments

1. Click the **Doctors** tab.
2. Scroll down to the **Departments** section.
3. Click **Add Department**.
4. Enter:
   - **Department Name:** `Dermatology`
5. Click **Save**.
6. **Verify:** "Dermatology" appears in the department list.

---

### 2.3 Create a Doctor

1. Still on the **Doctors** tab, click **Add Doctor**.
2. Fill in the form with these exact values:

   | Field | Value |
   |---|---|
   | Full Name | `Dr. Aisha Sharma` |
   | Username | `aisha` |
   | Password | `aisha123` |
   | Email | `aisha@hospital.com` |
   | Phone | `9876543210` |
   | Department | Select `Cardiology` from dropdown |
   | Availability Days | Select: Mon, Tue, Wed, Thu, Fri (all checked) |
   | Start Time | `09:00` |
   | End Time | `17:00` |
   | Slot Duration (minutes) | `30` |
   | Consultation Fee (₹) | `750` |
   | Bio | `Specialist in cardiac care with 10 years of experience.` |

3. Click **Save Doctor**.
4. **Verify:** "Dr. Aisha Sharma" appears in the doctors table with department "Cardiology".

---

### 2.4 Edit a Doctor's Consultation Fee

1. Find "Dr. Aisha Sharma" in the doctors table.
2. Click the **Edit** button in her row.
3. Locate the **Consultation Fee (₹)** field — it should show `750`.
4. Change it to: `1000`
5. Click **Save Doctor**.
6. **Verify:** The doctor row shows the updated details. Patients will now be charged ₹1000 for appointments with this doctor.

---

### 2.5 View All Appointments

1. Click the **Appointments** tab.
2. All appointments across all patients and doctors are visible.
3. Try filtering:
   - **Date filter:** Enter today's date in `YYYY-MM-DD` format.
   - **Status filter:** Select `Booked` from the dropdown.
4. **Verify:** Table updates to show only matching appointments.
5. **Upcoming appointments** (Booked + future date) are highlighted in **light green**.

---

### 2.6 View All Payments

1. Click the **Payments** tab.
2. Payment records appear with patient name, doctor name, amount in ₹, method, and status.
3. Try filtering by:
   - **Status:** `completed`
   - **Method:** `credit_card`
4. **Verify:** Amounts are shown in ₹ (Indian Rupees), not $.

---

### 2.7 Admin Statistics Dashboard

1. Click the **Stats** tab.
2. **Verify:**
   - Summary cards show total doctors, total patients, total appointments.
   - A Plotly bar chart shows monthly appointment counts.
   - A pie chart shows appointment status distribution.

---

### 2.8 Manage Patients

1. Click the **Patients** tab.
2. All registered patients are listed.
3. Click the **Edit** button on any patient row.
4. Change:
   - **Phone:** `1111111111`
5. Click **Save Patient**.
6. **Verify:** Updated phone number displays in the patient table.

**View Doctor's Patients:**
1. Click the **Doctors** tab.
2. Find any doctor row, click the **Patients** button.
3. **Verify:** A panel expands below showing all patients who have booked with that doctor, with an Edit button for each.

---

## 3. Patient Walkthrough

### 3.1 Register a Patient Account

1. On the login page, click the **Patient** tab.
2. Click the **"Register here"** link below the login form.
3. Fill in the registration form:

   | Field | Value |
   |---|---|
   | Full Name | `Rahul Mehta` |
   | Username | `rahul` |
   | Email | `rahul@example.com` |
   | Password | `rahul123` |

4. Click **Register**.
5. **Verify:** Success message "Registration successful. Please login." appears.

**Test unregistered login message:**
1. On the Patient login tab, enter username `unknownuser` and any password.
2. Click **Login**.
3. **Verify:** The form switches to the registration view with the message: *"No account found for that username. Please register below, then log in."*

---

### 3.2 Login as Patient

1. Click **Patient** tab on the login page.
2. Enter:
   - **Username:** `rahul`
   - **Password:** `rahul123`
3. Click **Login**.
4. **Verify:** Patient dashboard loads with tabs: Book Appointment, My Appointments, Payments, Profile.

---

### 3.3 Browse Doctors and Book an Appointment

1. The **Book Appointment** tab is active by default.
2. Doctor profile cards are displayed for all available doctors.
3. **Filter by Department:**
   - Click the **Cardiology** department button.
   - **Verify:** Only cardiologists (including Dr. Aisha Sharma) remain visible.
4. **Search by Name:**
   - Type `aisha` in the **Search doctor by name** field.
   - **Verify:** Only Dr. Aisha Sharma's card is shown.
5. **Select the Doctor:**
   - Click on **Dr. Aisha Sharma's card**.
   - **Verify:** The card gets a green border indicating selection. The doctor details panel below shows: Name, Department, Email, Phone, Availability, Hours, Slot Duration, **Consultation Fee: ₹1000**, Bio.
6. **Pick a Date:**
   - In the **Appointment Date** field, enter tomorrow's date (e.g., `2026-04-15`).
7. Click **Book Appointment**.
8. **Verify:** Success message appears. Navigate to **My Appointments** tab — the new appointment is listed with status **Booked** and doctor **Dr. Aisha Sharma**.

---

### 3.4 Pay for the Appointment

1. In the **My Appointments** tab, find the Booked appointment.
2. Click the **Pay** button in that row.
3. **Verify:** A payment panel appears showing:
   - **Amount: ₹1000** (fixed, read-only — cannot be edited)
   - **Payment Method** dropdown with only: Credit Card, Debit Card (no Insurance)
4. Fill in the payment form:

   | Field | Value |
   |---|---|
   | Payment Method | `Credit Card` |
   | Card Number | `4111111111111111` |

5. Click **Submit Payment**.
6. **Verify:** Success message "Payment completed." appears. The appointment's payment status changes to **Paid**.

---

### 3.5 View Appointment and Treatment History

*(Treatment is added by the doctor in Section 4.3 — complete that section first, then return here.)*

1. In the **My Appointments** tab, find the Completed appointment.
2. Click **View Treatment** (or expand the row).
3. **Verify:** Treatment details are shown — Diagnosis, Prescription, Notes.
4. **Verify:** Medical history is displayed in the **Profile** tab as read-only text (no edit button or textarea).

---

### 3.6 Update Profile and Notification Preferences

1. Click the **Profile** tab.
2. Update the following fields:

   | Field | Value |
   |---|---|
   | Full Name | `Rahul K. Mehta` |
   | Email | `rahul.mehta@example.com` |
   | Phone | `9000000001` |

3. In the **Notification Preferences** section:
   - Check **Email** checkbox ✓
   - Check **SMS** checkbox ✓
   - (Both channels can be selected simultaneously)
4. Click **Save Profile**.
5. **Verify:** Success message appears. Click Profile again to confirm updated name and both checkboxes are still checked.

**Verify medical history is read-only:**
- Look at the **Medical History** field.
- **Verify:** It is a read-only display box — no cursor, no editing possible. Content shows summaries appended after completed appointments.

---

### 3.7 Export Treatment History

1. Click the **My Appointments** tab.
2. Click the **Export CSV** button.
3. **Verify:** A message indicates the export is processing.
4. After a few seconds, click **Check Status** (or the export status updates automatically).
5. **Verify:** Status changes to "completed" and a **Download** link appears.
6. Click **Download** — a `.csv` file downloads with columns: Date, Doctor, Diagnosis, Prescription, Notes.

---

### 3.8 Cancel an Appointment

*(Book a second appointment first, following Section 3.3.)*

1. In **My Appointments**, find a **Booked** appointment that has NOT been paid.
2. Click **Cancel**.
3. Confirm in the dialog prompt.
4. **Verify:** Appointment status changes to **Cancelled**.

*(For a paid appointment cancellation:)*
1. Find a **Booked + Paid** appointment.
2. Click **Cancel** and confirm.
3. **Verify:** A refund entry appears in the **Payments** tab with a **negative amount** and status `refunded`.

---

## 4. Doctor Walkthrough

### 4.1 Login as Doctor

1. Click the **Doctor** tab on the login page.
2. Enter:
   - **Username:** `aisha`
   - **Password:** `aisha123`
3. Click **Login**.
4. **Verify:** Doctor dashboard loads with tabs: Appointments, My Patients, Reports, Payments, Availability, Profile.

---

### 4.2 View Upcoming Appointments

1. The **Appointments** tab is active by default.
2. **Verify:** Appointments with status **Booked** and a future date are highlighted in **light green** for easy identification.
3. Upcoming appointments appear at the top of the list (sorted by date/time ascending).
4. Past or completed appointments are not highlighted.

---

### 4.3 Complete a Consultation

1. In the **Appointments** tab, find the Booked appointment from Rahul Mehta (must be **paid** before completion).
2. Click **Complete**.
3. A form appears. Fill in:

   | Field | Value |
   |---|---|
   | Diagnosis | `Mild hypertension detected` |
   | Prescription | `Amlodipine 5mg once daily` |
   | Notes | `Patient advised to reduce salt intake and exercise regularly.` |
   | Next Visit Date | *(leave blank or enter a date 2 weeks from today)* |

4. Click **Save**.
5. **Verify:** Appointment status changes to **Completed**. The row is no longer highlighted green.
6. **Switch to patient view** (login as `rahul`) and verify:
   - The appointment shows "Completed" status.
   - Treatment details are visible.
   - Medical history in Profile tab has an auto-appended summary.

---

### 4.4 Add a Follow-Up Appointment

1. Open a completed appointment (click **View Details** if available).
2. Click **Schedule Follow-Up**.
3. Select a follow-up date (e.g., 2 weeks from now).
4. Click **Confirm Follow-Up**.
5. **Verify:** A new Booked appointment appears in the list linked to the original, shown with the same patient.

---

### 4.5 Edit a Past Treatment Record

1. Click the **My Patients** tab.
2. Find `Rahul K. Mehta` in the list.
3. Click **View History**.
4. Find the treatment record from the completed appointment.
5. Click **Edit** on that record.
6. Change:
   - **Prescription:** `Amlodipine 5mg once daily; follow-up ECG recommended`
7. Click **Save**.
8. **Verify:** Updated prescription appears in the treatment history.

---

### 4.6 View My Patients

1. Click the **My Patients** tab.
2. All patients who have booked with this doctor are listed.
3. Type `rahul` in the search box.
4. **Verify:** List filters to show only Rahul Mehta.
5. Click **View History** to see all appointments and treatments for that patient.

---

### 4.7 Update Availability

1. Click the **Availability** tab.
2. Change the form:

   | Field | Value |
   |---|---|
   | Availability Days | Uncheck **Saturday** (leave Mon–Fri) |
   | Start Time | `10:00` |
   | End Time | `16:00` |
   | Slot Duration | `45` |

3. Click **Save Availability**.
4. **Verify:** Success message appears.
5. **Switch to patient view** and try booking with Dr. Aisha Sharma — available slots should now reflect 10:00–16:00 with 45-minute intervals.

---

### 4.8 Download Monthly Report

1. Click the **Reports** tab.
2. Select:
   - **Month:** Previous month (e.g., `3` for March)
   - **Year:** Current year (e.g., `2026`)
3. Click **Download PDF Report**.
4. **Verify:** A PDF downloads containing:
   - Doctor name and period
   - Total appointments, completions, cancellations
   - Unique patients treated
   - Earnings summary in ₹

---

### 4.9 View Earnings

1. Click the **Payments** tab.
2. **Verify:** A summary card shows total earnings in ₹.
3. All payment rows show amounts in ₹ (Indian Rupees).
4. Filter by date or patient name to narrow results.

---

## 5. Cross-Role Feature Verification

### 5.1 Fixed Fee Consistency

| Step | User | Action | Expected |
|---|---|---|---|
| 1 | Admin | Set Dr. Aisha's fee to ₹1200 | Fee updated |
| 2 | Patient | Open Pay button for appointment with Dr. Aisha | Amount shows ₹1200, read-only |
| 3 | Patient | Attempt to submit with different amount | Not possible — amount field is read-only |

### 5.2 Medical History Read-Only

| Step | User | Action | Expected |
|---|---|---|---|
| 1 | Doctor | Complete appointment with diagnosis "Flu" | Medical history updated automatically |
| 2 | Patient | Go to Profile tab | "Flu" summary visible in read-only history box |
| 3 | Patient | Try to edit medical history | No edit control available — display only |

### 5.3 Notification Preferences

| Step | User | Action | Expected |
|---|---|---|---|
| 1 | Patient | Check both Email and SMS in Profile | Saved as `email,sms` |
| 2 | Patient | Uncheck Email, keep SMS only | Saved as `sms` |
| 3 | Patient | Check Email, uncheck SMS | Saved as `email` |
| 4 | Celery | Daily reminder task runs | Patient receives via all opted-in channels |

### 5.4 Upcoming Row Highlighting

- Login as **Admin** → Appointments tab → Upcoming rows are in light green.
- Login as **Doctor** → Appointments tab → Upcoming rows are in light green.
- Login as **Patient** → My Appointments tab → Upcoming rows are in light green.

---

## 6. Error and Edge Case Testing

### 6.1 Login with Wrong Password

1. Patient tab → username `rahul`, password `wrongpassword`.
2. Click **Login**.
3. **Verify:** Error message "Invalid credentials" (or similar) shown.

### 6.2 Unregistered Patient Login

1. Patient tab → username `doesnotexist`, password `anything`.
2. Click **Login**.
3. **Verify:** Form switches to registration view with message prompting to register first.

### 6.3 Completing Appointment Without Payment

1. Login as doctor.
2. Find a **Booked but unpaid** appointment.
3. Click **Complete**.
4. **Verify:** Error message "Payment required before completion" (or 400 response).

### 6.4 Double Booking Prevention

1. As **Patient 1** (rahul), book Dr. Aisha on date `2026-05-10`.
2. Register **Patient 2** (e.g., username `priya`, password `priya123`).
3. As Patient 2, book Dr. Aisha on the same date `2026-05-10`.
4. **Verify:** Both bookings succeed — they get **different time slots** (serial slot assignment).
5. Repeat until all slots for that day are filled.
6. **Verify:** Next booking attempt for that date returns an error: "No available slots for this date."

### 6.5 Invalid Payment Method

Using API directly (curl or Postman):
```
POST /api/patient/payment/appointment/<id>
{ "payment_method": "insurance", "card_number": "4111111111111111" }
```
**Verify:** Returns 400 with message about invalid payment method.

### 6.6 Notification Preference Validation

Using API directly:
```
POST /api/profile
{ "notification_pref": "whatsapp" }
```
**Verify:** Returns 400 with message about invalid notification preference.

### 6.7 Cancelling an Already Cancelled Appointment

1. Cancel a Booked appointment.
2. Try to cancel it again.
3. **Verify:** Error message "Cannot cancel a non-Booked appointment."

---

## Quick Reference — Test Accounts

| Role | Username | Password | Notes |
|---|---|---|---|
| Admin | `admin` | `admin` | Pre-created on first run |
| Doctor | `aisha` | `aisha123` | Created in Section 2.3 |
| Patient | `rahul` | `rahul123` | Created in Section 3.1 |

---

## Quick Reference — Key Behaviour Summary

| Feature | Behaviour |
|---|---|
| Consultation fee | Set by Admin per doctor; fixed, read-only during payment |
| Currency | ₹ Indian Rupees throughout |
| Payment methods | Credit Card and Debit Card only |
| Medical history | Read-only to patients; auto-updated after completed appointments |
| Notification channels | Email and/or SMS (checkboxes); both can be selected |
| Upcoming highlights | Light green row highlight in all three dashboards |
| Doctor booking UI | Profile cards with department filter + name search |
| Unregistered login | Redirects to registration form with explanation message |
