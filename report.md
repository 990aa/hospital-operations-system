# Hospital Management System Project Report

## Student Details
**Name:** Abdul Ahad
**ID:** [Student ID]

## Project Details

### Problem Statement
Hospitals require efficient systems to manage patients, doctors, and appointments to avoid manual errors and disconnects. The goal was to build a Hospital Management System (HMS) web application allowing Admins, Doctors, and Patients to interact based on their roles.

### Approach
The solution was architected as a web application with a clear separation of concerns:
- **Backend:** Python Flask was used to create a RESTful API. This handles all business logic, database interactions, and authentication.
- **Frontend:** Vue.js (via CDN) was used for a dynamic and responsive User Interface. It communicates with the backend via API calls.
- **Database:** SQLite was used for data persistence, managed via Flask-SQLAlchemy for an ORM-based approach.

The application follows a simplistic but professional design using Bootstrap/solid colours. The database logic ensures relationships between Users, Doctors, Patients, Appointments, and Treatments.

## Frameworks and Libraries Used
1.  **Flask:** A lightweight WSGI web application framework for Python.
2.  **Flask-SQLAlchemy:** For database interactions using Python objects.
3.  **Flask-Login:** For managing user sessions.
4.  **Vue.js (v3):** For building the client-side interface.
5.  **Bootstrap (v5):** For responsive styling and layout.
6.  **SQLite:** Lightweight disk-based database.

## ER Diagram (Text Description)
- **User:** `id`, `username`, `password`, `role`, `name`
- **Department:** `id`, `name`, `description`
- **Doctor:** `id`, `user_id` (FK), `department_id` (FK), `availability`
- **Patient:** `id`, `user_id` (FK), `medical_history`
- **Appointment:** `id`, `patient_id` (FK), `doctor_id` (FK), `date`, `time`, `status`
- **Treatment:** `id`, `appointment_id` (FK), `diagnosis`, `prescription`, `notes`

## API Resource Endpoints

### Authentication
- `POST /api/login`: Authenticate user.
- `POST /api/logout`: End session.
- `POST /api/register`: Register new patient.
- `GET /api/current-user`: Get logged-in user info.

### Admin
- `GET /api/admin/stats`: Dashboard statistics.
- `GET /api/admin/doctors`: List doctors.
- `POST /api/admin/doctors`: Add doctor.
- `DELETE /api/admin/doctors/<id>`: Remove doctor.
- `GET /api/admin/patients`: List patients.
- `DELETE /api/admin/patients/<id>`: Remove patient.

### Patient & General
- `GET /api/departments`: List departments.
- `GET /api/doctors`: Search/List doctors.
- `POST /api/appointments`: Book appointment.
- `POST /api/appointments/<id>/cancel`: Cancel appointment.
- `GET /api/my-appointments`: Get user history.
- `POST /api/profile`: Update profile.

### Doctor
- `GET /api/doctor/appointments`: Get assigned appointments.
- `POST /api/appointments/<id>/complete`: Complete appointment & Add treatment.
