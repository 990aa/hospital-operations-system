"""
PDF Report Generation Module.

This module provides functionality to generate professional PDF reports
for doctors and patients using the pymupdf library.

Author: Abdul Ahad
"""

import fitz  # PyMuPDF
from datetime import datetime
from io import BytesIO


def generate_monthly_report_pdf(doctor_name, month, year, appointments_data, stats):
    """
    Generate a professional monthly activity report PDF for a doctor.

    Args:
        doctor_name: Name of the doctor
        month: Month number (1-12)
        year: Year (e.g., 2025)
        appointments_data: List of appointment dictionaries
        stats: Dictionary with summary statistics

    Returns:
        BytesIO object containing the PDF data
    """
    # Create a new PDF document
    doc = fitz.open()

    # Add a page (A4 size)
    page = doc.new_page(width=595, height=842)  # A4 in points

    # Define colors
    primary_blue = (0.05, 0.43, 0.99)  # RGB normalized
    dark_gray = (0.13, 0.14, 0.16)
    light_gray = (0.47, 0.49, 0.53)

    # Header
    page.insert_text(
        (50, 50), "HOSPITAL MANAGEMENT SYSTEM", fontsize=18, color=primary_blue
    )
    page.insert_text((50, 75), "Monthly Activity Report", fontsize=24, color=dark_gray)

    # Doctor Information
    page.insert_text((50, 110), f"Doctor: {doctor_name}", fontsize=14, color=dark_gray)
    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    page.insert_text(
        (50, 130),
        f"Period: {month_names[month - 1]} {year}",
        fontsize=12,
        color=light_gray,
    )
    page.insert_text(
        (50, 150),
        f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        fontsize=10,
        color=light_gray,
    )

    # Draw a separator line
    page.draw_line((50, 165), (545, 165), color=light_gray, width=0.5)

    # Summary Statistics Section
    y_pos = 190
    page.insert_text((50, y_pos), "Summary Statistics", fontsize=16, color=dark_gray)
    y_pos += 25

    # Statistics boxes
    stats_info = [
        ("Total Appointments", stats.get("total_appointments", 0)),
        ("Completed", stats.get("completed", 0)),
        ("Cancelled", stats.get("cancelled", 0)),
        ("Patients Seen", stats.get("unique_patients", 0)),
    ]

    box_width = 115
    box_height = 60
    x_start = 50

    for i, (label, value) in enumerate(stats_info):
        x_pos = x_start + (i % 4) * (box_width + 10)
        box_y = y_pos + (i // 4) * (box_height + 10)

        # Draw box background
        rect = fitz.Rect(x_pos, box_y, x_pos + box_width, box_y + box_height)
        page.draw_rect(rect, color=light_gray, fill=(0.95, 0.95, 0.95), width=0.5)

        # Add text
        page.insert_text((x_pos + 10, box_y + 25), label, fontsize=10, color=light_gray)
        page.insert_text(
            (x_pos + 10, box_y + 45), str(value), fontsize=20, color=primary_blue
        )

    y_pos += box_height + 30

    # Appointments Details Section
    page.insert_text((50, y_pos), "Appointment Details", fontsize=16, color=dark_gray)
    y_pos += 25

    # Table headers
    headers = ["Date", "Patient", "Status", "Diagnosis"]
    col_widths = [90, 150, 80, 175]
    x_positions = [50, 140, 290, 370]

    # Draw header row
    for i, header in enumerate(headers):
        page.insert_text((x_positions[i], y_pos), header, fontsize=10, color=dark_gray)

    y_pos += 5
    page.draw_line((50, y_pos), (545, y_pos), color=light_gray, width=0.5)
    y_pos += 15

    # Table rows (limited to first 15 appointments to fit on one page)
    max_rows = 15
    for idx, apt in enumerate(appointments_data[:max_rows]):
        if y_pos > 750:  # Check if we're running out of page space
            break

        # Format data
        date_str = (
            apt.get("appointment_date", "").split("T")[0]
            if apt.get("appointment_date")
            else "N/A"
        )
        patient_name = apt.get("patient_name", "Unknown")[:20]  # Truncate if too long
        status = apt.get("status", "N/A")
        diagnosis = apt.get("diagnosis", "Pending")[:25]  # Truncate if too long

        # Alternate row background
        if idx % 2 == 0:
            rect = fitz.Rect(50, y_pos - 10, 545, y_pos + 5)
            page.draw_rect(rect, fill=(0.98, 0.98, 0.98))

        # Status color
        status_color = dark_gray
        if status == "completed":
            status_color = (0.1, 0.53, 0.33)  # Green
        elif status == "cancelled":
            status_color = (0.86, 0.21, 0.27)  # Red

        page.insert_text((x_positions[0], y_pos), date_str, fontsize=9, color=dark_gray)
        page.insert_text(
            (x_positions[1], y_pos), patient_name, fontsize=9, color=dark_gray
        )
        page.insert_text(
            (x_positions[2], y_pos), status.capitalize(), fontsize=9, color=status_color
        )
        page.insert_text(
            (x_positions[3], y_pos), diagnosis, fontsize=9, color=light_gray
        )

        y_pos += 18

    if len(appointments_data) > max_rows:
        page.insert_text(
            (50, y_pos + 10),
            f"... and {len(appointments_data) - max_rows} more appointments",
            fontsize=9,
            color=light_gray,
        )

    # Footer
    footer_y = 820
    page.draw_line(
        (50, footer_y - 10), (545, footer_y - 10), color=light_gray, width=0.5
    )
    page.insert_text(
        (50, footer_y),
        "Hospital Management System • Confidential Report",
        fontsize=8,
        color=light_gray,
    )
    page.insert_text((450, footer_y), "Page 1 of 1", fontsize=8, color=light_gray)

    # Save to BytesIO
    pdf_bytes = BytesIO()
    pdf_bytes.write(doc.tobytes())
    pdf_bytes.seek(0)
    doc.close()

    return pdf_bytes


def generate_patient_history_pdf(patient_name, patient_id, appointments_data):
    """
    Generate a patient history report PDF.

    Args:
        patient_name: Name of the patient
        patient_id: Patient ID
        appointments_data: List of appointment dictionaries with treatment info

    Returns:
        BytesIO object containing the PDF data
    """
    # Create a new PDF document
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Define colors
    primary_blue = (0.05, 0.43, 0.99)
    dark_gray = (0.13, 0.14, 0.16)
    light_gray = (0.47, 0.49, 0.53)

    # Header
    page.insert_text(
        (50, 50), "HOSPITAL MANAGEMENT SYSTEM", fontsize=18, color=primary_blue
    )
    page.insert_text((50, 75), "Patient Medical History", fontsize=24, color=dark_gray)

    # Patient Information
    page.insert_text(
        (50, 110), f"Patient: {patient_name}", fontsize=14, color=dark_gray
    )
    page.insert_text(
        (50, 130), f"Patient ID: {patient_id}", fontsize=12, color=light_gray
    )
    page.insert_text(
        (50, 150),
        f"Report Date: {datetime.now().strftime('%B %d, %Y')}",
        fontsize=10,
        color=light_gray,
    )

    page.draw_line((50, 165), (545, 165), color=light_gray, width=0.5)

    # Appointments Section
    y_pos = 190
    page.insert_text(
        (50, y_pos),
        f"Medical History ({len(appointments_data)} visits)",
        fontsize=16,
        color=dark_gray,
    )
    y_pos += 35

    # List appointments
    for idx, apt in enumerate(appointments_data[:8]):  # Limit to first 8
        if y_pos > 750:
            break

        # Box for each appointment
        box_height = 70
        rect = fitz.Rect(50, y_pos, 545, y_pos + box_height)
        page.draw_rect(rect, color=light_gray, fill=(0.97, 0.97, 0.97), width=0.5)

        # Appointment details
        date_str = (
            apt.get("appointment_date", "").split("T")[0]
            if apt.get("appointment_date")
            else "N/A"
        )
        doctor = apt.get("doctor_name", "Unknown Doctor")
        diagnosis = apt.get("diagnosis", "No diagnosis recorded")
        treatment = apt.get("treatment_description", "No treatment recorded")

        page.insert_text(
            (60, y_pos + 20),
            f"Visit {len(appointments_data) - idx}",
            fontsize=11,
            color=primary_blue,
        )
        page.insert_text(
            (60, y_pos + 35), f"Date: {date_str}", fontsize=9, color=dark_gray
        )
        page.insert_text(
            (200, y_pos + 35), f"Doctor: {doctor}", fontsize=9, color=dark_gray
        )
        page.insert_text(
            (60, y_pos + 50),
            f"Diagnosis: {diagnosis[:50]}",
            fontsize=9,
            color=light_gray,
        )
        page.insert_text(
            (60, y_pos + 63),
            f"Treatment: {treatment[:50]}",
            fontsize=9,
            color=light_gray,
        )

        y_pos += box_height + 10

    # Footer
    footer_y = 820
    page.draw_line(
        (50, footer_y - 10), (545, footer_y - 10), color=light_gray, width=0.5
    )
    page.insert_text(
        (50, footer_y),
        "Hospital Management System • Confidential Report",
        fontsize=8,
        color=light_gray,
    )

    # Save to BytesIO
    pdf_bytes = BytesIO()
    pdf_bytes.write(doc.tobytes())
    pdf_bytes.seek(0)
    doc.close()

    return pdf_bytes
