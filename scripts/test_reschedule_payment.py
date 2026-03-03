"""Test that rescheduling transfers payment correctly."""

import requests

BASE = "http://localhost:5000/api"
s = requests.Session()

# 1. Login as patient
r = s.post(f"{BASE}/login", json={"username": "emma.taylor", "password": "password"})
assert r.status_code == 200, f"Login failed: {r.text}"
print("Patient login OK")

# 2. Book appointment - find a date with available slots
# Use doctor 3 (dr.brooks) who has more availability (Mon-Sat, 20-min slots)
doctor_id = 3
r = s.get(f"{BASE}/doctors/{doctor_id}/availability")
avail = r.json().get("availability", [])
book_date = None
reschedule_date = None
dates_with_slots = [d["date"] for d in avail if d["remaining_slots"] > 1]
print(f"Dates with >1 slots: {dates_with_slots}")
if len(dates_with_slots) >= 2:
    book_date = dates_with_slots[0]
    reschedule_date = dates_with_slots[1]
else:
    print("Not enough available dates!")
    exit(1)

r = s.post(f"{BASE}/appointments", json={"doctor_id": doctor_id, "date": book_date})
print(f"Book: {r.status_code} {r.json()}")

apt_id = r.json().get("appointment_id")
assert apt_id, "Failed to book appointment"

# 3. Pay for it
r = s.post(
    f"{BASE}/patient/payment/appointment/{apt_id}",
    json={"payment_method": "credit_card", "card_number": "4111111111111234"},
)
print(f"Payment: {r.status_code} {r.json().get('message')}")
assert r.status_code == 201

# 4. Verify it shows as paid
r = s.get(f"{BASE}/my-appointments")
for a in r.json():
    if a["id"] == apt_id:
        print(
            f"  Old apt {apt_id}: paid={a['paid']}, payment_status={a['payment_status']}"
        )
        assert a["paid"] is True, "Appointment should be paid"
        break

# 5. Login as doctor and reschedule
s.post(f"{BASE}/logout")
r = s.post(f"{BASE}/login", json={"username": "dr.brooks", "password": "password"})
assert r.status_code == 200

# Reschedule to a different date
r = s.post(
    f"{BASE}/doctor/appointments/{apt_id}/reschedule",
    json={"new_date": reschedule_date},
)
print(f"Reschedule: {r.status_code} {r.json()}")
assert r.status_code == 200, f"Reschedule failed: {r.text}"
new_apt_id = r.json().get("new_appointment_id")
assert new_apt_id, "No new appointment ID returned"

# 6. Login back as patient and verify payment transferred
s.post(f"{BASE}/logout")
s.post(f"{BASE}/login", json={"username": "emma.taylor", "password": "password"})
r = s.get(f"{BASE}/my-appointments")
for a in r.json():
    if a["id"] == new_apt_id:
        print(
            f"  New apt {new_apt_id}: paid={a['paid']}, payment_status={a['payment_status']}"
        )
        assert a["paid"] is True, "NEW appointment should be paid (payment transferred)"
    if a["id"] == apt_id:
        print(
            f"  Old apt {apt_id}: paid={a['paid']}, status={a['status']}, payment_status={a['payment_status']}"
        )
        assert a["status"] == "Cancelled", "Old appointment should be cancelled"

# 7. Check total payments haven't doubled
r = s.get(f"{BASE}/patient/payments")
payments = r.json()
old_payments = [p for p in payments if p["appointment_id"] == apt_id]
new_payments = [p for p in payments if p["appointment_id"] == new_apt_id]
print(f"  Old apt payments: {[(p['status'], p['amount']) for p in old_payments]}")
print(f"  New apt payments: {[(p['status'], p['amount']) for p in new_payments]}")

# Net should be zero for old (paid + refund) and positive for new
old_net = sum(p["amount"] for p in old_payments)
new_net = sum(p["amount"] for p in new_payments)
print(f"  Old net: {old_net}, New net: {new_net}")
assert (
    old_net == 0 or abs(old_net) < 0.01
), f"Old appointment net should be ~0 (paid + refund), got {old_net}"
assert new_net > 0, f"New appointment should have positive payment, got {new_net}"

print("\n=== RESCHEDULE PAYMENT TEST PASSED ===")
