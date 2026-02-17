# Hospital Management System Project Report

## Student Details
**Name:** Abdul Ahad
**ID:** [Student ID]

## Project Details

### Problem Statement
Hospitals require efficient systems to manage patients, doctors, and appointments to avoid manual errors and disconnects. The goal was to build a modern Hospital Management System (HMS) web application allowing Admins, Doctors, and Patients to interact securely, while automating routine tasks and ensuring high performance through asynchronous processing and caching.

### Approach
The solution is architected as a full-stack web application with a robust backend and a dynamic frontend:
- **Backend:** Python Flask was used to create a RESTful API. Business logic, database interactions, and authorization are handled here.
- **Background Jobs:** Celery with a Redis broker handles scheduled tasks (daily reminders, monthly reports) and user-triggered long-running tasks (CSV exports) to keep the API responsive.
- **Frontend:** Vue.js 3 (via CDN) provides a dynamic, single-page application experience. Data visualization is handled exclusively by **Plotly.js**.
- **Caching:** Redis is integrated via Flask-Caching to store frequently accessed data (like dashboard stats and doctor listings) with automatic expiry.
- **Security:** Flask-Security-Too handles authentication, session management, and role-based access control (RBAC). Passwords are securely hashed using Argon2.

### Performance and Reliability
- **Conflict Prevention:** Logic was implemented to prevent overlapping appointments for doctors at the same time and date.
- **Database Indexing:** Foreign key relationships and proper indexing ensure efficient queries for history and search.
- **Asynchronous Processing:** CSV exports are handled in the background, preventing the application from hanging during data-heavy operations.

## Frameworks and Libraries Used
1.  **Flask:** Core backend framework.
2.  **Flask-SQLAlchemy:** ORM for SQLite database management.
3.  **Flask-Security-Too:** Robust authentication and RBAC.
4.  **Celery & Redis:** Background task management and scheduling.
5.  **Flask-Caching:** Redis-based caching for performance.
6.  **Vue.js (v3):** Reactive frontend framework.
7.  **Plotly.js:** Professional data visualization.
8.  **Bootstrap (v5):** Responsive UI design.
9.  **Pandas:** Efficient data handling for CSV exports.

## Database Schema (Refined)
- **User:** Authentication details, roles, and profile info.
- **Department:** Specializations like Cardiology, Neurology, etc.
- **Doctor:** Profile linked to User and Department, includes availability settings.
- **Patient:** Profile linked to User, stores medical history and notification preferences.
- **Appointment:** Connects Patient and Doctor with date, time, and status (Booked, Completed, Cancelled).
- **Treatment:** Medical records for completed appointments (diagnosis, prescription, notes).
- **ExportJob:** Tracks the status and results of asynchronous CSV export tasks.

## New Implemented Features

### 1. Scheduled Background Jobs
- **Daily Reminders:** Automatically checks for appointments scheduled for the current day and notifies patients via their preferred method (Email/SMS/Google Chat).
- **Monthly Activity Reports:** Generates a comprehensive HTML activity report for every doctor on the first of each month, summarizing their previous month's treatments.

### 2. User-Triggered Async Jobs
- **CSV Export:** Patients can trigger a full export of their treatment history. The task runs in the background, and the patient is notified once the download is ready.

### 3. Advanced Search & History
- **Unified Search:** Admins and Patients can search doctors by name or specialization. Admins can search patients by name, ID, or contact info.
- **Full History:** Doctors can view the entire medical history of their patients, ensuring informed consultations.

## Conclusion
The HMS provides a scalable and professional platform for hospital operations. By combining Flask's simplicity with Celery's background processing and Redis's caching, the system remains fast and reliable even as data grows.
