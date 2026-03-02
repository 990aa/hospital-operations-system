"""
Celery Tasks for Background Jobs.

This module contains all the background tasks for the Hospital Management System:
- Daily appointment reminders for patients (email)
- Monthly activity reports for doctors (email)
- Async CSV export for patient treatment history

All tasks are designed to be idempotent and handle errors gracefully.
Google Chat webhook integration has been intentionally excluded.
SMS support has been removed; all notifications are sent via email only.

Email delivery uses Flask-Mail backed by Gmail SMTP with credentials
loaded from a .env file via python-dotenv.

Author: Abdul Ahad
"""

import os
import csv
from datetime import date, datetime, timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

# Import these inside functions to avoid circular imports
# when Flask app context is needed


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_daily_reminders(self):
    """
    Send daily appointment reminders to patients.

    This task runs every morning at 8:00 AM and sends reminders
    to all patients who have appointments scheduled for today or
    tomorrow, giving them advance notice.

    Reminders are sent via email to the patient's registered email address.

    Args:
        self: The task instance (provided by bind=True)

    Returns:
        dict: Summary of reminders sent with counts
    """
    # Import Flask app and models inside task to ensure proper context
    from flask import current_app
    from models.database import db, Appointment, Patient

    # Include both today and tomorrow so patients receive a reminder
    # the day before their appointment as well as on the day itself.
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Query for today's and tomorrow's appointments with status 'Booked'
    # Join with Patient to get patient details
    appointments = (
        db.session.query(Appointment)
        .join(Patient)
        .filter(
            Appointment.date.in_([today, tomorrow]),
            Appointment.status == "Booked",
        )
        .all()
    )

    results = {
        "total": len(appointments),
        "emails_sent": 0,
        "failed": 0,
    }

    for appointment in appointments:
        patient = appointment.patient
        doctor = appointment.doctor

        # Prepare reminder message
        subject = "Hospital Appointment Reminder"
        visit_type = (
            "Follow-up Consultation"
            if getattr(appointment, "is_follow_up", False)
            else "Consultation"
        )
        message = f"""
Dear {patient.user.name},

This is a friendly reminder that you have an appointment scheduled for today:

    Visit Type: {visit_type}
Doctor: {doctor.user.name}
Department: {doctor.department.name}
Date: {appointment.date}
Time: {appointment.time}

Please arrive 15 minutes before your scheduled time.
If you need to cancel, please contact the hospital.

Best regards,
Hospital Management Team
"""

        try:
            # Send email notification to patient.
            if patient.user.email:
                send_email(patient.user.email, subject, message)
                results["emails_sent"] += 1

        except Exception as e:
            # Log error but continue with other appointments
            current_app.logger.error(
                f"Failed to send reminder to patient {patient.id}: {str(e)}"
            )
            results["failed"] += 1

    return results


@shared_task(bind=True, max_retries=3, default_retry_delay=600)
def send_monthly_reports(self):
    """
    Send monthly activity reports to doctors.

    This task runs on the 1st day of every month at 9:00 AM.
    It generates an HTML report for each doctor containing:
    - Total appointments for the previous month
    - List of patients seen
    - Diagnoses provided
    - Treatments suggested

    Args:
        self: The task instance (provided by bind=True)

    Returns:
        dict: Summary of reports sent with counts
    """
    from flask import current_app
    from models.database import Doctor, Appointment

    # Calculate previous month
    today = datetime.now()
    first_day_of_current = today.replace(day=1)
    last_day_of_previous = first_day_of_current - timedelta(days=1)
    first_day_of_previous = last_day_of_previous.replace(day=1)


    prev_month_start = first_day_of_previous.strftime("%Y-%m-%d")
    prev_month_end = last_day_of_previous.strftime("%Y-%m-%d")
    prev_month_name = first_day_of_previous.strftime("%B %Y")
    

    """
    # Start demo
    from datetime import date
    today = date.today()
    prev_month_start = today.replace(day=1).strftime("%Y-%m-%d")
    prev_month_end = today.strftime("%Y-%m-%d")
    prev_month_name = today.strftime("%B %Y") + " (DEMO)"
    # End demo
    """

    # Get all doctors
    doctors = Doctor.query.all()

    results = {"total_doctors": len(doctors), "reports_sent": 0, "failed": 0}

    for doctor in doctors:
        # Skip if email notifications disabled or no email
        if not doctor.email_notifications or not doctor.user.email:
            continue

        # Get appointments for previous month
        appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.date >= prev_month_start,
            Appointment.date <= prev_month_end,
            Appointment.status == "Completed",
        ).all()

        if not appointments:
            continue  # Skip doctors with no appointments

        # Build HTML report
        html_report = build_monthly_report_html(doctor, appointments, prev_month_name)

        subject = f"Monthly Activity Report - {prev_month_name}"

        try:
            send_email(
                to_email=doctor.user.email,
                subject=subject,
                message=html_report,
                is_html=True,
            )
            results["reports_sent"] += 1
        except Exception as e:
            current_app.logger.error(
                f"Failed to send report to doctor {doctor.id}: {str(e)}"
            )
            results["failed"] += 1

    return results


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def export_patient_treatments(self, patient_id, export_job_id):
    """
    Export patient treatment history to CSV.

    This task is triggered by patients from their dashboard.
    It exports all their completed appointments with treatment details
    to a CSV file and notifies them when complete.

    CSV includes:
    - user_id, username
    - consulting doctor name
    - appointment date and time
    - diagnosis
    - treatment/prescription
    - notes
    - next visit suggestion

    Args:
        self: The task instance (provided by bind=True)
        patient_id: ID of the patient requesting export
        export_job_id: ID of the ExportJob record to update

    Returns:
        dict: Export result with file path or error
    """
    from flask import current_app
    from models.database import db, Patient, Appointment, ExportJob, Payment

    # Get the export job record
    export_job = ExportJob.query.get(export_job_id)
    if not export_job:
        return {"error": "Export job not found"}

    try:
        # Update status to processing
        export_job.status = "processing"
        db.session.commit()

        # Get patient with appointments
        patient = Patient.query.get(patient_id)
        if not patient:
            raise Exception("Patient not found")

        # Export all appointments so users always receive row data,
        # even if no consultation has been completed yet.
        appointments = (
            Appointment.query.filter(Appointment.patient_id == patient_id)
            .order_by(Appointment.date.desc(), Appointment.time.desc())
            .all()
        )

        # Create exports directory if not exists
        exports_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(exports_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"patient_{patient_id}_treatments_{timestamp}.csv"
        file_path = os.path.join(exports_dir, filename)

        # Write CSV
        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "user_id",
                "username",
                "patient_name",
                "patient_email",
                "patient_phone",
                "consulting_doctor",
                "doctor_department",
                "appointment_date",
                "appointment_time",
                "diagnosis",
                "treatment",
                "prescription",
                "notes",
                "next_visit_suggested",
                "appointment_status",
                "is_follow_up",
                "follow_up_source_appointment_id",
                "payment_status",
                "payment_amount",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for appointment in appointments:
                treatment = appointment.treatment
                doctor = appointment.doctor
                latest_payment = (
                    Payment.query.filter_by(appointment_id=appointment.id)
                    .order_by(Payment.payment_date.desc(), Payment.id.desc())
                    .first()
                )

                next_visit = "N/A"
                if treatment and treatment.notes:
                    notes_lower = treatment.notes.lower()
                    if "follow" in notes_lower or "visit" in notes_lower:
                        next_visit = "See notes"

                writer.writerow(
                    {
                        "user_id": patient.user.id,
                        "username": patient.user.username,
                        "patient_name": patient.user.name,
                        "patient_email": patient.user.email or "N/A",
                        "patient_phone": patient.user.phone or "N/A",
                        "consulting_doctor": doctor.user.name,
                        "doctor_department": doctor.department.name,
                        "appointment_date": appointment.date,
                        "appointment_time": appointment.time,
                        "diagnosis": treatment.diagnosis if treatment else "N/A",
                        "treatment": treatment.prescription if treatment else "N/A",
                        "prescription": treatment.prescription if treatment else "N/A",
                        "notes": treatment.notes if treatment else "N/A",
                        "next_visit_suggested": next_visit,
                        "appointment_status": appointment.status,
                        "is_follow_up": bool(
                            getattr(appointment, "is_follow_up", False)
                        ),
                        "follow_up_source_appointment_id": getattr(
                            appointment, "follow_up_source_appointment_id", None
                        ),
                        "payment_status": latest_payment.status
                        if latest_payment
                        else "unpaid",
                        "payment_amount": latest_payment.amount
                        if latest_payment
                        else "N/A",
                    }
                )

        # Update export job with success
        export_job.status = "completed"
        export_job.file_path = file_path
        export_job.completed_at = datetime.now()
        db.session.commit()

        # Send notification to patient with CSV attached
        if patient.user.email:
            subject = "Treatment History Export Complete"
            message = f"""
Dear {patient.user.name},

Your treatment history export has been completed successfully.

Export Details:
- Total Records: {len(appointments)}
- Export Date: {datetime.now().strftime("%Y-%m-%d %H:%M")}

The CSV file is attached to this email.

Best regards,
Hospital Management Team
"""
            try:
                send_email_with_attachment(
                    patient.user.email, subject, message, file_path
                )
            except Exception as e:
                # Fallback: send without attachment
                try:
                    send_email(patient.user.email, subject, message)
                except Exception as e2:
                    current_app.logger.error(f"Failed to send export notification: {e2}")

        return {
            "success": True,
            "file_path": file_path,
            "records_exported": len(appointments),
        }

    except Exception as e:
        # Update export job with failure
        export_job.status = "failed"
        export_job.error_message = str(e)
        export_job.completed_at = datetime.now()
        db.session.commit()

        # Retry on failure
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            return {"success": False, "error": str(e), "file_path": None}


def build_monthly_report_html(doctor, appointments, month_name):
    """
    Build an HTML report for a doctor's monthly activity.

    Args:
        doctor: Doctor object
        appointments: List of completed Appointment objects
        month_name: Name of the month for the report

    Returns:
        str: HTML content for the report
    """
    total_appointments = len(appointments)
    unique_patients = len(set(a.patient_id for a in appointments))

    # Collect diagnoses
    diagnoses = []
    treatments = []
    for appt in appointments:
        if appt.treatment:
            diagnoses.append(appt.treatment.diagnosis)
            treatments.append(appt.treatment.prescription)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #333; }}
            h2 {{ color: #555; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f2f2f2; font-weight: bold; }}
            .summary {{ background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0; }}
            .stat {{ display: inline-block; margin: 10px 20px; }}
            .stat-value {{ font-size: 24px; font-weight: bold; color: #2c5aa0; }}
            .stat-label {{ color: #666; }}
        </style>
    </head>
    <body>
        <h1>Monthly Activity Report - {month_name}</h1>
        <p>Dear {doctor.user.name},</p>

        <div class="summary">
            <h2>Summary</h2>
            <div class="stat">
                <div class="stat-value">{total_appointments}</div>
                <div class="stat-label">Total Appointments</div>
            </div>
            <div class="stat">
                <div class="stat-value">{unique_patients}</div>
                <div class="stat-label">Unique Patients</div>
            </div>
        </div>

        <h2>Appointment Details</h2>
        <table>
            <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Patient</th>
                <th>Diagnosis</th>
                <th>Treatment</th>
            </tr>
    """

    for appt in appointments:
        treatment = appt.treatment
        html += f"""
            <tr>
                <td>{appt.date}</td>
                <td>{appt.time}</td>
                <td>{appt.patient.user.name}</td>
                <td>{treatment.diagnosis if treatment else "N/A"}</td>
                <td>{treatment.prescription if treatment else "N/A"}</td>
            </tr>
        """

    html += """
        </table>
        <p><em>This report was automatically generated by the Hospital Management System.</em></p>
    </body>
    </html>
    """

    return html


def send_email(to_email, subject, message, is_html=False):
    """
    Send an email using Flask-Mail.

    Flask-Mail is configured via the .env file credentials loaded
    in app.py.  When MAIL_USERNAME is not set (e.g. in tests),
    the email is logged to the console instead.

    Args:
        to_email: Recipient email address
        subject: Email subject
        message: Email body (text or HTML)
        is_html: Whether message is HTML (default: False)

    Raises:
        Exception: If email sending fails
    """
    from flask_mail import Message as MailMessage
    from app import mail

    username = os.environ.get("SMTP_USERNAME", "")
    if username:
        # Build the Flask-Mail message
        msg = MailMessage(
            subject=subject,
            recipients=[to_email],
        )
        if is_html:
            msg.html = message
        else:
            msg.body = message

        mail.send(msg)
    else:
        # For development/tests: just log the email
        print(f"[EMAIL] To: {to_email}\nSubject: {subject}\n\n{message}\n---")


def send_email_with_attachment(to_email, subject, message, file_path):
    """Send an email with a file attachment using Flask-Mail.

    Falls back to console logging when SMTP is not configured.

    Args:
        to_email: Recipient email address
        subject: Email subject
        message: Email body (plain text)
        file_path: Absolute path to the file to attach
    """
    from flask_mail import Message as MailMessage
    from app import mail

    username = os.environ.get("SMTP_USERNAME", "")
    if username:
        msg = MailMessage(
            subject=subject,
            recipients=[to_email],
            body=message,
        )
        with open(file_path, "rb") as fp:
            filename = os.path.basename(file_path)
            msg.attach(filename, "text/csv", fp.read())
        mail.send(msg)
    else:
        print(f"[EMAIL+ATTACHMENT] To: {to_email}\nSubject: {subject}\nAttachment: {file_path}\n\n{message}\n---")
