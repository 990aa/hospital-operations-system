"""Application-level configuration values."""

# Safety rules
DONATION_SAFETY_DAYS = 56

# Inventory/forecast thresholds
SHORTAGE_ALERT_DAYS_THRESHOLD = 3.0
EXPIRING_SOON_DAYS = 5

# Request validation
MIN_DONATION_QUANTITY_ML = 50.0
MIN_REQUEST_QUANTITY_ML = 50.0

# UI pagination
AUDIT_PAGE_SIZE = 50

# Split ratios from the historical 450ml component split:
# Red Blood Cells: 200ml, Platelets: 50ml, Plasma: 200ml
COMPONENT_SPLIT_RATIO = {
    "Red Blood Cells": 200 / 450,
    "Platelets": 50 / 450,
    "Plasma": 200 / 450,
}
