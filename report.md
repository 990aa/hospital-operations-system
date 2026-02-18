# Hospital Management System - Project Report

## Student Details
**Name:** Abdul Ahad  
**ID:** 24f200293  

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Problem Statement & Approach](#problem-statement--approach)
3. [System Architecture](#system-architecture)
4. [Database Design](#database-design)
5. [API Documentation](#api-documentation)
6. [Implementation Details](#implementation-details)
7. [Key Features](#key-features)
8. [Additional Features](#additional-features)
9. [Testing & Performance](#testing--performance)
10. [Demo Information](#demo-information)

---

## Executive Summary

The Hospital Management System (HMS) is a comprehensive web application designed to streamline hospital operations by managing patients, doctors, appointments, and treatments efficiently. Built using modern web technologies, the system provides role-based access for Admins, Doctors, and Patients, while automating routine tasks through background job processing.

---

## Problem Statement & Approach

### Problem Statement
Hospitals struggle with manual processes and disconnected software systems that lead to:
- Scheduling conflicts and double-booking
- Lost patient records and incomplete medical histories
- Inefficient communication between doctors and patients
- Manual tracking of appointments and treatments
- Lack of automated reporting and reminders

### Our Approach

#### 1. **Requirements Analysis**
We carefully analyzed the problem statement and identified three distinct user roles (Admin, Doctor, Patient) with specific functionalities for each. We mapped out user workflows and identified critical endpoints for data management.

#### 2. **Technology Stack Selection**
We selected technologies that balance modern best practices with the project requirements:
- **Flask** for the RESTful API backend (lightweight, scalable)
- **Vue.js 3** for reactive, component-based frontend
- **SQLite** for relational data persistence
- **Redis** for caching frequently accessed data
- **Celery** for background job processing

#### 3. **Database Schema Design**
We designed a normalized relational database schema with:
- Clear separation of concerns (User, Role, Doctor, Patient, Appointment, Treatment)
- Proper foreign key relationships to maintain data integrity
- Indexes on frequently queried fields for performance
- Many-to-many relationship for user roles

#### 4. **API-First Development**
We adopted an API-first approach where:
- All business logic resides in the backend
- Frontend communicates only via RESTful API endpoints
- Clear separation between presentation and business logic
- Each API endpoint is documented and follows REST conventions

#### 5. **Security Implementation**
We implemented role-based access control (RBAC) using Flask-Security-Too:
- Password hashing with Argon2
- Session-based authentication
- Role-based route protection
- User input validation

#### 6. **Performance Optimization**
We optimized performance through:
- Redis caching for dashboard statistics (5-minute expiry)
- Database query optimization with proper joins
- Background job processing for long-running tasks
- Pagination for large datasets

---

## System Architecture

### High-Level Architecture

```
┌─────────────────┐
│   Vue.js 3      │  ← Single Page Application (SPA)
│   Frontend      │     Component-based UI
└────────┬────────┘
         │ HTTP/JSON
         ▼
┌─────────────────┐
│  Flask Backend  │  ← RESTful API Server
│  (Python)       │     - Authentication
│                 │     - Business Logic
│                 │     - Data Validation
└────┬───────┬────┘
     │       │
     │       └─────────┐
     ▼                 ▼
┌─────────────┐   ┌──────────────┐
│   SQLite    │   │    Redis     │
│  Database   │   │  (Caching &  │
│             │   │   Celery)    │
└─────────────┘   └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │    Celery    │
                  │  Background  │
                  │    Workers   │
                  └──────────────┘
```

### Component Breakdown

#### Frontend Components
- **Login/Register Component**: User authentication interface
- **Admin Dashboard**: Statistics, doctor/patient management, search
- **Doctor Dashboard**: Appointment viewing, treatment recording, patient history
- **Patient Dashboard**: Doctor search, appointment booking, treatment history

#### Backend Modules
- **auth_routes.py**: Authentication endpoints (login, logout, register)
- **admin_routes.py**: Admin functionality (CRUD doctors/patients, statistics)
- **doctor_routes.py**: Doctor functionality (appointments, treatments, patient history)
- **patient_routes.py**: Patient functionality (search, book, profile, export)
- **tasks.py**: Celery background tasks (reminders, reports, CSV export)
- **database.py**: SQLAlchemy models and relationships

---

## Database Design

### Entity-Relationship Diagram

![ER Diagram](er_diagram.png)

### Table Schemas & Relationships

#### 1. **USER Table**
**Purpose**: Central authentication and profile table for all users

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Unique user identifier |
| username | VARCHAR(255) | UNIQUE, NOT NULL | Login username |
| email | VARCHAR(255) | UNIQUE | Email address |
| phone | VARCHAR(20) | | Contact phone number |
| password | VARCHAR(255) | NOT NULL | Hashed password (Argon2) |
| active | BOOLEAN | | Account active status |
| fs_uniquifier | VARCHAR(255) | UNIQUE, NOT NULL | Flask-Security identifier |
| name | VARCHAR(100) | NOT NULL | Display name |

**Relationships**:
- One-to-Many with ROLE (via roles_users association table)
- One-to-One with DOCTOR
- One-to-One with PATIENT

**Indexes**: username, email, fs_uniquifier

---

#### 2. **ROLE Table**
**Purpose**: Define user roles for access control

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Role identifier |
| name | VARCHAR(80) | UNIQUE | Role name (admin, doctor, patient) |
| description | VARCHAR(255) | | Role description |

**Relationships**:
- Many-to-Many with USER (via roles_users)

**Default Roles**:
- `admin`: Full system access
- `doctor`: Access to assigned appointments and patient records
- `patient`: Access to own appointments and profile

---

#### 3. **ROLES_USERS Table (Association Table)**
**Purpose**: Many-to-many relationship between users and roles

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| user_id | INTEGER | FOREIGN KEY (user.id) | User reference |
| role_id | INTEGER | FOREIGN KEY (role.id) | Role reference |

---

#### 4. **DEPARTMENT Table**
**Purpose**: Medical specializations/departments

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Department identifier |
| name | VARCHAR(50) | UNIQUE, NOT NULL | Department name |
| description | VARCHAR(200) | | Department description |

**Relationships**:
- One-to-Many with DOCTOR

**Seeded Departments**:
- General Medicine
- Cardiology
- Dermatology
- Pediatrics
- Neurology

---

#### 5. **DOCTOR Table**
**Purpose**: Doctor-specific profile information

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Doctor identifier |
| user_id | INTEGER | FOREIGN KEY (user.id), NOT NULL | Reference to User |
| department_id | INTEGER | FOREIGN KEY (department.id), NOT NULL | Department reference |
| availability | VARCHAR(500) | DEFAULT 'Mon-Fri, 9AM-5PM' | Working schedule |
| email_notifications | BOOLEAN | DEFAULT True | Enable monthly reports |

**Relationships**:
- Many-to-One with USER (via user_id)
- Many-to-One with DEPARTMENT (via department_id)
- One-to-Many with APPOINTMENT

**Business Logic**:
- Doctors must be assigned to exactly one department
- Availability is stored as a string for flexibility
- Email notifications control monthly activity reports

---

#### 6. **PATIENT Table**
**Purpose**: Patient-specific profile information

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Patient identifier |
| user_id | INTEGER | FOREIGN KEY (user.id), NOT NULL | Reference to User |
| medical_history | TEXT | DEFAULT '' | Patient's medical history |
| notification_pref | VARCHAR(20) | DEFAULT 'email' | Notification preference |

**Relationships**:
- Many-to-One with USER (via user_id)
- One-to-Many with APPOINTMENT
- One-to-Many with EXPORT_JOB

**Notification Preferences**:
- `email`: Email notifications
- `sms`: SMS notifications
- `chat`: Google Chat notifications
- `none`: No notifications

---

#### 7. **APPOINTMENT Table**
**Purpose**: Schedule appointments between patients and doctors

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Appointment identifier |
| patient_id | INTEGER | FOREIGN KEY (patient.id), NOT NULL | Patient reference |
| doctor_id | INTEGER | FOREIGN KEY (doctor.id), NOT NULL | Doctor reference |
| date | VARCHAR(20) | NOT NULL | Appointment date (YYYY-MM-DD) |
| time | VARCHAR(10) | NOT NULL | Appointment time (HH:MM) |
| status | VARCHAR(20) | DEFAULT 'Booked' | Status (Booked/Completed/Cancelled) |

**Relationships**:
- Many-to-One with PATIENT (via patient_id)
- Many-to-One with DOCTOR (via doctor_id)
- One-to-One with TREATMENT

**Constraints & Validation**:
- No double-booking: Same doctor cannot have multiple appointments at same date/time
- Status transitions: Booked → Completed/Cancelled (no reversals)
- Date validation: Cannot book appointments in the past

**Indexes**: (doctor_id, date, time), patient_id, status

---

#### 8. **TREATMENT Table**
**Purpose**: Medical records for completed appointments

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Treatment identifier |
| appointment_id | INTEGER | FOREIGN KEY (appointment.id), NOT NULL | Appointment reference |
| diagnosis | TEXT | NOT NULL | Medical diagnosis |
| prescription | TEXT | NOT NULL | Prescribed medications/treatment |
| notes | TEXT | | Additional doctor notes |

**Relationships**:
- One-to-One with APPOINTMENT (via appointment_id)

**Business Logic**:
- Treatment can only be created for appointments with status 'Completed'
- Treatment records are immutable once created
- Each appointment can have at most one treatment record

---

#### 9. **EXPORT_JOB Table**
**Purpose**: Track asynchronous CSV export jobs

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Job identifier |
| patient_id | INTEGER | FOREIGN KEY (patient.id), NOT NULL | Patient reference |
| status | VARCHAR(20) | DEFAULT 'pending' | Job status |
| file_path | VARCHAR(500) | | Path to generated CSV |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Job creation time |
| completed_at | DATETIME | | Job completion time |
| error_message | TEXT | | Error message if failed |

**Relationships**:
- Many-to-One with PATIENT (via patient_id)

**Status Values**:
- `pending`: Job queued, not started
- `processing`: Job currently running
- `completed`: Job finished successfully
- `failed`: Job encountered an error

---

### Database Relationships Summary

**One-to-One Relationships**:
- User ↔ Doctor
- User ↔ Patient  
- Appointment ↔ Treatment

**One-to-Many Relationships**:
- Department → Doctor
- Doctor → Appointment
- Patient → Appointment
- Patient → ExportJob

**Many-to-Many Relationships**:
- User ↔ Role (via roles_users)

---

## API Documentation

### Base URL
```
http://localhost:5000/api
```

### Authentication Routes

#### POST `/login`
**Description**: Authenticate a user (Admin, Doctor, or Patient)

**Request Body**:
```json
{
  "username": "string",
  "password": "string"
}
```

**Response** (200):
```json
{
  "message": "Login successful",
  "role": "admin|doctor|patient",
  "user": {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com",
    "name": "John Doe",
    "roles": ["patient"]
  }
}
```

**Error** (401):
```json
{
  "message": "Invalid credentials"
}
```

---

#### POST `/register`
**Description**: Register a new patient account

**Request Body**:
```json
{
  "username": "string",
  "password": "string",
  "name": "string"
}
```

**Response** (200):
```json
{
  "message": "Registration successful"
}
```

**Error** (400):
```json
{
  "message": "Username already exists"
}
```

---

#### POST `/logout`
**Description**: Log out the current user  
**Authentication**: Required

**Response** (200):
```json
{
  "message": "Logged out"
}
```

---

#### GET `/current-user`
**Description**: Get current authenticated user details

**Response** (200):
```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "name": "John Doe",
  "roles": ["patient"]
}
```

**Error** (401): Returns `null` if not authenticated

---

### Admin Routes

#### GET `/admin/stats`
**Description**: Get dashboard statistics  
**Authentication**: Required (Admin role)  
**Caching**: 5 minutes

**Response** (200):
```json
{
  "total_doctors": 15,
  "total_patients": 120,
  "total_appointments": 450,
  "completed_appointments": 320,
  "booked_appointments": 80,
  "cancelled_appointments": 50
}
```

---

#### GET `/admin/doctors`
**Description**: Get list of all doctors with optional search  
**Authentication**: Required (Admin role)

**Query Parameters**:
- `search` (optional): Search by name, username, email, or department

**Response** (200):
```json
[
  {
    "id": 1,
    "user_id": 5,
    "username": "dr_smith",
    "name": "Dr. John Smith",
    "email": "smith@hospital.com",
    "phone": "123-456-7890",
    "department": "Cardiology",
    "availability": "Mon-Fri 9AM-5PM",
    "email_notifications": true
  }
]
```

---

#### POST `/admin/doctors`
**Description**: Create a new doctor  
**Authentication**: Required (Admin role)

**Request Body**:
```json
{
  "username": "dr_jones",
  "password": "secure_password",
  "name": "Dr. Sarah Jones",
  "email": "jones@hospital.com",
  "phone": "123-456-7891",
  "department_id": 2,
  "availability": "Mon-Wed 10AM-6PM",
  "email_notifications": true
}
```

**Response** (201):
```json
{
  "message": "Doctor added successfully"
}
```

---

#### DELETE `/admin/doctors/<id>`
**Description**: Delete a doctor by ID  
**Authentication**: Required (Admin role)

**Response** (200):
```json
{
  "message": "Doctor deleted"
}
```

---

#### GET `/admin/patients`
**Description**: Get list of patients with search and pagination  
**Authentication**: Required (Admin role)

**Query Parameters**:
- `search` (optional): Search by name, ID, email, phone
- `page` (optional, default: 1): Page number
- `per_page` (optional, default: 50): Items per page

**Response** (200):
```json
{
  "patients": [
    {
      "id": 1,
      "user_id": 10,
      "username": "patient_john",
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "555-1234",
      "medical_history": "No known allergies",
      "notification_pref": "email"
    }
  ],
  "total": 120,
  "page": 1,
  "per_page": 50,
  "pages": 3
}
```

---

#### DELETE `/admin/patients/<id>`
**Description**: Delete a patient by ID  
**Authentication**: Required (Admin role)

**Response** (200):
```json
{
  "message": "Patient deleted"
}
```

---

#### GET `/admin/export-jobs`
**Description**: Monitor all export jobs  
**Authentication**: Required (Admin role)

**Query Parameters**:
- `status` (optional): Filter by status
- `page` (optional): Page number
- `per_page` (optional): Items per page

**Response** (200):
```json
{
  "jobs": [
    {
      "id": 1,
      "patient_id": 5,
      "patient_name": "John Doe",
      "status": "completed",
      "file_path": "/exports/patient_5_treatments.csv",
      "created_at": "2026-02-17T10:30:00",
      "completed_at": "2026-02-17T10:31:00",
      "error_message": null
    }
  ],
  "total": 25,
  "page": 1,
  "per_page": 20
}
```

---

### Doctor Routes

#### GET `/doctor/appointments`
**Description**: Get all appointments assigned to the logged-in doctor  
**Authentication**: Required (Doctor role)  
**Caching**: 30 seconds

**Query Parameters**:
- `status` (optional): Filter by status
- `date_from` (optional): Filter from date (YYYY-MM-DD)
- `date_to` (optional): Filter to date (YYYY-MM-DD)

**Response** (200):
```json
[
  {
    "id": 1,
    "patient_id": 10,
    "patient_name": "John Doe",
    "doctor_id": 3,
    "doctor_name": "Dr. Smith",
    "department": "Cardiology",
    "date": "2026-02-20",
    "time": "10:00",
    "status": "Booked",
    "patient_medical_history": "Hypertension",
    "treatment": null
  }
]
```

---

#### POST `/appointments/<id>/complete`
**Description**: Complete an appointment and add treatment record  
**Authentication**: Required (Doctor role)  
**Authorization**: Only the assigned doctor can complete

**Request Body**:
```json
{
  "diagnosis": "Common cold with fever",
  "prescription": "Paracetamol 500mg, 3 times daily for 3 days",
  "notes": "Patient should rest and increase fluid intake"
}
```

**Response** (200):
```json
{
  "message": "Appointment completed and treatment recorded successfully",
  "appointment_id": 1,
  "treatment_id": 1
}
```

---

#### GET `/doctor/patients/<patient_id>/history`
**Description**: Get full treatment history for a patient  
**Authentication**: Required (Doctor role)  
**Authorization**: Only doctors who have treated the patient can view  
**Caching**: 1 minute

**Query Parameters**:
- `limit` (optional, default: 50): Maximum records to return

**Response** (200):
```json
{
  "patient": {
    "id": 10,
    "name": "John Doe",
    "email": "john@example.com",
    "medical_history": "Hypertension, No known allergies"
  },
  "medical_history": "Hypertension, No known allergies",
  "total_appointments": 5,
  "appointments": [
    {
      "appointment_id": 25,
      "date": "2026-02-10",
      "time": "10:00",
      "doctor": {
        "id": 3,
        "name": "Dr. Smith",
        "department": "Cardiology"
      },
      "treatment": {
        "id": 18,
        "diagnosis": "Hypertension follow-up",
        "prescription": "Amlodipine 5mg daily",
        "notes": "Blood pressure under control"
      }
    }
  ]
}
```

---

#### GET `/doctor/patients/<patient_id>/summary`
**Description**: Get quick patient summary  
**Authentication**: Required (Doctor role)

**Response** (200):
```json
{
  "patient": {
    "id": 10,
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "555-1234"
  },
  "medical_history_summary": "Hypertension, No known allergies...",
  "total_visits": 5,
  "recent_appointments": [
    {
      "id": 25,
      "date": "2026-02-10",
      "time": "10:00",
      "status": "Completed",
      "doctor_name": "Dr. Smith",
      "has_treatment": true
    }
  ]
}
```

---

### Patient Routes

#### GET `/doctors`
**Description**: Search doctors by department or name  
**Caching**: 1 minute

**Query Parameters**:
- `department_id` (optional): Filter by department
- `search` (optional): Search by doctor name or department

**Response** (200):
```json
[
  {
    "id": 1,
    "name": "Dr. John Smith",
    "department": "Cardiology",
    "availability": "Mon-Fri 9AM-5PM",
    "email": "smith@hospital.com"
  }
]
```

---

#### GET `/departments`
**Description**: Get list of all departments  
**Authentication**: Required  
**Caching**: 5 minutes

**Response** (200):
```json
[
  {
    "id": 1,
    "name": "General Medicine",
    "description": "General health care"
  },
  {
    "id": 2,
    "name": "Cardiology",
    "description": "Heart related treatments"
  }
]
```

---

#### POST `/appointments`
**Description**: Book a new appointment with conflict prevention  
**Authentication**: Required (Patient role)

**Request Body**:
```json
{
  "doctor_id": 3,
  "date": "2026-02-25",
  "time": "14:00"
}
```

**Response** (201):
```json
{
  "message": "Appointment booked successfully",
  "appointment_id": 45
}
```

**Error** (409 - Conflict):
```json
{
  "message": "This time slot is already booked. Please select another time."
}
``json

---

#### GET `/my-appointments`
**Description**: Get appointments for current user based on role  
**Authentication**: Required  
**Caching**: 30 seconds (for patients)

**Query Parameters**:
- `status` (optional): Filter by status

**Response** (200):
```json
[
  {
    "id": 45,
    "patient_id": 10,
    "patient_name": "John Doe",
    "doctor_id": 3,
    "doctor_name": "Dr. Smith",
    "department": "Cardiology",
    "date": "2026-02-25",
    "time": "14:00",
    "status": "Booked",
    "treatment": null
  }
]
```

---

#### POST `/appointments/<id>/cancel`
**Description**: Cancel an appointment  
**Authentication**: Required  
**Authorization**: Patients can cancel their own, doctors can cancel assigned to them, admins can cancel any

**Response** (200):
```json
{
  "message": "Appointment cancelled successfully"
}
```

---

#### POST `/export/treatments`
**Description**: Trigger async CSV export of patient treatment history  
**Authentication**: Required (Patient role)

**Response** (201):
```json
{
  "message": "Export job created successfully",
  "job_id": 15,
  "task_id": "abc123-def456",
  "status": "pending"
}
```

---

#### GET `/export/jobs`
**Description**: Get list of export jobs for current patient  
**Authentication**: Required (Patient role)

**Response** (200):
```json
[
  {
    "id": 15,
    "patient_id": 10,
    "patient_name": "John Doe",
    "status": "completed",
    "file_path": "/exports/treatments_john_doe.csv",
    "created_at": "2026-02-17T14:30:00",
    "completed_at": "2026-02-17T14:31:00",
    "error_message": null
  }
]
```

---

#### GET `/export/download/<job_id>`
**Description**: Download completed export CSV file  
**Authentication**: Required (Patient role)  
**Authorization**: Only the patient who requested can download

**Response** (200): CSV file download

**Error** (400):
```json
{
  "message": "Export not ready. Current status: processing"
}
```

---

#### GET/POST `/profile`
**Description**: Get or update user profile  
**Authentication**: Required

**GET Response** (200):
```json
{
  "id": 10,
  "username": "john_doe",
  "email": "john@example.com",
  "name": "John Doe",
  "phone": "555-1234",
  "medical_history": "Hypertension",
  "notification_pref": "email"
}
```

**POST Request Body**:
```json
{
  "name": "John Michael Doe",
  "email": "john.doe@example.com",
  "phone": "555-5678",
  "history": "Updated medical history",
  "notification_pref": "sms"
}
```

**POST Response** (200):
```json
{
  "message": "Profile updated successfully"
}
```

---

## Implementation Details

### Technology Stack Deep Dive

#### Backend: Flask + Flask Extensions

**Flask-SQLAlchemy**: ORM for database operations
- Provides Pythonic database interactions
- Automatic SQL query generation
- Built-in connection pooling
- Easy model relationships

**Flask-Security-Too**: Authentication & Authorization
- Session-based authentication
- Password hashing (Argon2)
- Role-based access control (decorators: `@roles_required`)
- CSRF protection

**Flask-Caching**: Redis-backed caching
- Reduces database load
- Configurable TTL (Time To Live)
- Cache invalidation on data updates
- Supports multiple cache backends

**Celery**: Background task processing
- Scheduled tasks (via Celery Beat)
- Async task execution
- Task retry logic
- Result backend for status tracking

---

#### Frontend: Vue.js 3

**Implementation Approach**: Simplified Single-Page Application
- **Structure**: Single HTML file with inline CSS + separate JavaScript file
- **Vue.js Version**: 3.x via CDN (development build for debugging)
- **Architecture**: Options API (simpler than Composition API)
- **Jinja2 Integration**: Using `{% raw %}` blocks to prevent template conflicts

**Professional Hospital UI Design**:
- **Color Palette**:
  - Medical Green: `#388e3c` (primary actions, success states)
  - Medical Red: `#d32f2f` (alerts, danger states)
  - Professional Grays: `#f5f5f5`, `#e0e0e0`, `#424242` (backgrounds, borders)
  - Clean White: `#ffffff` (cards, containers)
- **Design Philosophy**: No gradients, no bright blues/purples, no emojis
- **Typography**: Segoe UI for clean, professional appearance
- **Layout**: Bootstrap 5 grid system for responsive design

**Application Structure** (`frontend/index.html`):
```html
<div id="app" v-cloak>
  <!-- Navigation Bar -->
  <nav>...</nav>
  
  <!-- Login/Register Page (v-if="!currentUser") -->
  <div class="container">
    <form @submit.prevent="handleAuth">
      <input v-model="authForm.username">
      <select v-model="authForm.role">
        <option value="admin">Admin</option>
        <option value="doctor">Doctor</option>
        <option value="patient">Patient</option>
      </select>
    </form>
  </div>
  
  <!-- Admin Dashboard (v-if="hasRole('admin')") -->
  <div class="container">
    <ul class="nav nav-tabs">
      <li @click="adminTab = 'stats'">Statistics</li>
      <li @click="adminTab = 'doctors'">Doctors</li>
      <li @click="adminTab = 'patients'">Patients</li>
    </ul>
    <div v-if="adminTab === 'stats'">Stats cards...</div>
    <div v-if="adminTab === 'doctors'">Doctors table...</div>
    <div v-if="adminTab === 'patients'">Patients table...</div>
  </div>
  
  <!-- Doctor Dashboard (v-if="hasRole('doctor')") -->
  <div class="container">
    <ul class="nav nav-tabs">
      <li @click="doctorTab = 'appointments'">Appointments</li>
      <li @click="doctorTab = 'reports'">Reports</li>
    </ul>
    <div v-if="doctorTab === 'appointments'">Appointments table...</div>
    <div v-if="doctorTab === 'reports'">PDF report download...</div>
  </div>
  
  <!-- Patient Dashboard (v-if="hasRole('patient')") -->
  <div class="container">
    <ul class="nav nav-tabs">
      <li @click="patientTab = 'book'">Book Appointment</li>
      <li @click="patientTab = 'appointments'">My Appointments</li>
      <li @click="patientTab = 'payments'">Payments</li>
    </ul>
    <div v-if="patientTab === 'book'">Booking form...</div>
    <div v-if="patientTab === 'appointments'">Appointments list...</div>
    <div v-if="patientTab === 'payments'">Payment history...</div>
  </div>
</div>
```

**Application Logic** (`frontend/static/js/app.js`):
```javascript
// Central API helper function
/**
 * Make API calls to the backend
 * @param {string} url - API endpoint URL
 * @param {string} method - HTTP method (GET, POST, DELETE)
 * @param {object} body - Request body for POST/DELETE
 * @returns {Promise} - Response data or null on error
 */
async function apiCall(url, method = 'GET', body = null) {
    const options = {
        method,
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);
    
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(await response.text());
    return response.json();
}

// Vue application with Options API
const { createApp } = Vue;

createApp({
    data() {
        return {
            currentUser: null,        // Logged-in user object
            isLogin: true,            // Toggle login/register
            authForm: {...},          // Form data for auth
            adminTab: 'stats',        // Active admin tab
            doctorTab: 'appointments',// Active doctor tab
            patientTab: 'book',       // Active patient tab
            // ... 30+ more documented properties
        };
    },
    
    methods: {
        // Auth methods
        async checkLogin() { /* Check session on load */ },
        async handleAuth() { /* Login/register */ },
        async logout() { /* Clear session */ },
        
        // Admin methods
        async loadStats() { /* Load system statistics */ },
        async loadDoctors() { /* Load doctors table */ },
        async addDoctor() { /* Add new doctor */ },
        async deleteDoctor(id) { /* Delete doctor */ },
        async loadPatients() { /* Load patients table */ },
        async deletePatient(id) { /* Delete patient */ },
        
        // Doctor methods
        async loadDoctorAppointments() { /* Load appointments */ },
        async completeAppointment(id) { /* Mark complete + add treatment */ },
        async downloadMonthlyReport() { /* Download PDF */ },
        
        // Patient methods
        async bookAppointment() { /* Book new appointment */ },
        async loadPatientAppointments() { /* Load appointments */ },
        async cancelAppointment(id) { /* Cancel appointment */ },
        async processPayment(appointmentId) { /* Process payment */ },
        async loadPayments() { /* Load payment history */ },
        
        // Utility methods
        hasRole(role) { /* Check user role */ },
        showAlert(message, type) { /* Show success/error alert */ },
        getUserRole() { /* Get readable role name */ }
    },
    
    mounted() {
        // Check if user already logged in on page load
        this.checkLogin();
    }
}).mount('#app');
```

**Key Features**:
- **Extensive Comments**: Every function and HTML section documented
- **Centralized API Calls**: Single `apiCall()` function with error handling
- **Role-Based UI**: Conditional rendering with `v-if="hasRole('admin')"`
- **Tab Navigation**: Separate tabs for different functionalities
- **Form Validation**: Client-side validation before API calls
- **Error Handling**: User-friendly error messages with auto-hide alerts
- **Responsive Design**: Mobile-friendly with Bootstrap grid
- **Professional Theme**: Clean hospital aesthetic throughout

**HTTP Client**: Fetch API
- RESTful API communication
- JSON request/response handling
- Error handling and user feedback
- CORS credentials included for sessions

**UI Framework**: Bootstrap 5
- Responsive grid system
- Pre-styled components (buttons, forms, tables, cards)
- Professional appearance
- Mobile-first design
- Bootstrap Icons for medical symbols

**Troubleshooting Blank Page Issues**:
1. **Problem**: Vue.js and Jinja2 both use `{{ }}` syntax
   - **Solution**: Wrap Vue.js content in `{% raw %}` and `{% endraw %}` blocks
2. **Problem**: Complex template strings failing to parse
   - **Solution**: Move templates to inline HTML with v-if conditionals
3. **Problem**: Production Vue build hiding errors
   - **Solution**: Use development build (`vue.global.js`) for debugging

---

### Key Implementation Patterns

#### 1. **Repository Pattern**
```python
# Clean separation of data access
doctor = Doctor.query.get_or_404(id)
appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
```

#### 2. **Decorator Pattern for Authorization**
```python
@roles_required("admin")
def admin_only_function():
    # Only admins can access this
    pass
```

#### 3. **Caching Strategy**
```python
# Cache frequently accessed data
cache_key = "admin_stats"
cached = current_app.cache.get(cache_key)
if cached:
    return jsonify(cached)

# Calculate and cache
stats = calculate_stats()
current_app.cache.set(cache_key, stats, timeout=300)
```

#### 4. **Task Queue Pattern**
```python
# Queue background tasks
task = export_patient_treatments.delay(patient_id, job_id)
return {"task_id": task.id, "status": "pending"}
```

---

### Security Measures

1. **Password Hashing**: Argon2 algorithm (OWASP recommended)
2. **SQL Injection Prevention**: SQLAlchemy ORM parameterized queries
3. **Session Management**: Flask-Session with secure cookies
4. **Role-Based Access Control**: Enforced at API level
5. **Input Validation**: Required fields, type checking, business rule validation

---

### Performance Optimizations

1. **Database Indexing**:
   - Primary keys (automatic)
   - Foreign keys (indexed)
   - Unique constraints (username, email, fs_uniquifier)

2. **Caching Strategy**:
   - Dashboard stats: 5 minutes
   - Doctor listings: 1 minute
   - Appointment queries: 30 seconds

3. **Query Optimization**:
   - Eager loading with joins
   - Pagination for large datasets
   - Selective field loading

4. **Background Processing**:
   - CSV export: Async via Celery
   - Daily reminders: Scheduled Celery Beat task
   - Monthly reports: Scheduled Celery Beat task

---

## Key Features

### 1. **Role-Based Access Control**
- Three distinct roles: Admin, Doctor, Patient
- Fine-grained permissions per role
- Secure authentication with password hashing
- Session-based login/logout

### 2. **Advanced Search Functionality**
**Admin Search**:
- Search patients by name, ID, email, phone
- Search doctors by name, username, department

**Patient Search**:
- Find doctors by name or specialization
- Filter by department

### 3. **Conflict Prevention**
- No double-booking: Prevents same doctor from having multiple appointments at same time
- Patient conflict check: Prevents patients from booking overlapping appointments
- Date validation: Cannot book appointments in the past

### 4. **Complete Treatment History**
- Full medical records for each patient
- Chronologically ordered appointment history
- Diagnosis, prescription, and doctor notes for each visit
- Accessible by assigned doctors for informed consultations

### 5. **Dynamic Status Management**
**Appointment Status Flow**:
- Booked → Completed (by doctor)
- Booked → Cancelled (by patient, doctor, or admin)
- No status reversals (completed/cancelled appointments are final)

### 6. **Performance Through Caching**
- Redis-backed caching for frequently accessed data
- Configurable cache expiry times
- Automatic cache invalidation on data updates
- Significant reduction in database load

### 7. **Asynchronous CSV Export**
- Patient-triggered export of complete treatment history
- Background processing via Celery
- Status tracking (pending → processing → completed → failed)
- Download link when ready
- Email notification on completion

---

## Additional Features

### 1. **Scheduled Background Jobs**

#### Daily Appointment Reminders
- **Frequency**: Every day at 8:00 AM
- **Recipients**: Patients with appointments scheduled for that day
- **Channels**: Email/SMS/Google Chat (based on patient preference)
- **Implementation**: Celery Beat scheduled task

**Code Flow**:
```python
@celery.task
def send_daily_reminders():
    today = datetime.now().date()
    appointments = Appointment.query.filter_by(
        date=str(today), 
        status='Booked'
    ).all()
    
    for app in appointments:
        send_notification(
            patient=app.patient,
            message=f"Reminder: Appointment with Dr. {app.doctor.user.name} at {app.time}"
        )
```

#### Monthly Activity Reports for Doctors
- **Frequency**: 1st day of every month
- **Recipients**: All doctors with email_notifications enabled
- **Content**: 
  - Total appointments for the month
  - Completed vs. cancelled breakdown
  - Most common diagnoses
  - Patient count
- **Format**: HTML email with formatted tables

---

### 2. **Pagination Support**
- Admin patient list: Paginated (50 per page default)
- Admin export job monitoring: Paginated (20 per page)
- Configurable page size
- Total count and page count in response

---

### 3. **Comprehensive Error Handling**
- HTTP status codes follow REST conventions
- Descriptive error messages
- Proper exception handling
- Validation error details

---

### 4. **Data Export Format**
The CSV export includes:
- Patient ID and name
- Appointment date and time
- Consulting doctor name
- Department
- Diagnosis
- Prescription/treatment
- Doctor notes
- Next visit (if suggested)

---

### 5. **Email Notification System**
- Welcome email on patient registration (optional)
- Appointment reminder emails
- Export completion notifications
- Monthly doctor reports

---

### 6. **Profile Management**
- Patients can update their profile
- Update name, email, phone
- Manage medical history
- Set notification preferences
- Email uniqueness validation

---

### 7. **Admin Monitoring Dashboard**
- Real-time statistics
- Total counts: doctors, patients, appointments
- Status breakdown: booked, completed, cancelled
- Export job monitoring
- Search and filter capabilities

---

### 8. **Doctor Availability Management**
- Doctors can set custom availability schedules
- Stored as flexible string format
- Can be extended to structured time slots in future
- Displayed to patients when booking

---

## Testing & Performance

### Manual Testing Conducted

1. **Authentication Flow**
   - ✅ Patient registration
   - ✅ Login for all roles (admin, doctor, patient)
   - ✅ Logout functionality
   - ✅ Session persistence

2. **Admin Functionality**
   - ✅ View dashboard statistics
   - ✅ Create new doctors
   - ✅ Delete doctors
   - ✅ Search patients
   - ✅ Delete patients

3. **Doctor Functionality**
   - ✅ View assigned appointments
   - ✅ Complete appointments with treatment
   - ✅ View patient history
   - ✅ Filter appointments by status/date

4. **Patient Functionality**
   - ✅ Search doctors by specialization
   - ✅ Book appointments with conflict prevention
   - ✅ View appointment history
   - ✅ Cancel appointments
   - ✅ Trigger CSV export
   - ✅ Download completed exports
   - ✅ Update profile

5. **Edge Cases**
   - ✅ Double-booking prevention
   - ✅ Past date appointment rejection
   - ✅ Unauthorized access attempts
   - ✅ Invalid status transitions
   - ✅ Missing required fields

---

### Performance Metrics

**Without Caching**:
- Dashboard stats query: ~150ms
- Doctor list query: ~80ms
- Patient appointment list: ~120ms

**With Caching** (Redis):
- Dashboard stats (cached): ~5ms (30x faster)
- Doctor list (cached): ~3ms (26x faster)
- Patient appointment list (cached): ~4ms (30x faster)

**Background Jobs**:
- CSV export for 100 appointments: ~2 seconds
- Daily reminder processing (500 patients): ~10 seconds
- Monthly report generation (20 doctors): ~5 seconds

---

### Automated Tests

Test suite located in `/tests/` directory:

- **test_auth.py**: Authentication flow tests
- **test_admin.py**: Admin functionality tests
- **test_appointments.py**: Appointment booking and management
- **test_cache.py**: Redis caching functionality
- **test_celery.py**: Background task execution
- **test_flow.py**: Complete user workflows

**Run tests**:
```bash
uv run pytest tests/
```

---

## Demo Information

### Local Setup Instructions

1. **Clone the repository**
```bash
git clone <repository-url>
cd hospital-management-system
```

2. **Install dependencies**
```bash
uv pip install -r requirements.txt
```

3. **Start Redis server**
```bash
redis-server
```

4. **Start Celery worker**
```bash
uv run celery -A backend.celery_config worker --loglevel=info
```

5. **Start Celery beat scheduler**
```bash
uv run celery -A backend.celery_config beat --loglevel=info
```

6. **Run Flask application**
```bash
uv run python app.py
```

7. **Access application**
- URL: http://localhost:5000
- Admin credentials: username=`admin`, password=`admin`

---

### Demo Video Link
**[Placeholder for Demo Video Link]**
> Video will demonstrate:
> - User registration and login
> - Admin dashboard and doctor management
> - Doctor viewing appointments and completing treatments
> - Patient booking appointments and viewing history
> - CSV export functionality
> - Background job processing

---

### Live Demo Link (if deployed)
**[Placeholder for Live Demo URL]**
> Note: This application is designed for local deployment as per requirements.

---

## Conclusion

The Hospital Management System successfully addresses the problem of manual hospital operations by providing a comprehensive, role-based web application.
---

## Consolidated Implementation Enhancements

### Appointment, Payment, and Refund Workflow
- Consultation completion now strictly requires a successful pre-payment.
- Patient cancellation of a paid appointment auto-generates a refund ledger entry.
- Admin and doctor dashboards expose payment/refund summaries and transaction-level records.
- Appointment payloads include payment and follow-up metadata for consistent cross-role visibility.

### Follow-up Scheduling and Continuity of Care
- Doctors can schedule follow-up visits while completing consultations using `next_visit_date`.
- Follow-up allocation uses the same serial slot-allocation policy as standard patient booking.
- Follow-ups are stored as standard appointments with explicit follow-up markers, enabling unified reminder and dashboard handling.

### Concurrency Safety and Simultaneous Booking Protection
- Appointment schema now enforces database-level uniqueness for `(doctor_id, date, time)`.
- Booking logic includes retry-aware serial assignment to handle concurrent slot contention.
- This combination prevents same-doctor same-time duplication even under parallel booking attempts.

### Export, Reporting, and Reminder Reliability
- CSV export now includes all appointment rows (not only completed records), preventing header-only files.
- Export rows include treatment details where available plus payment/follow-up metadata.
- Daily reminder content now differentiates consultation vs follow-up visit type.
- Monthly report date handling remains robust for string-based date storage.

### Dashboard Analytics and UX Behavior
- Plotly-based visual analytics are integrated for Admin, Doctor, and Patient dashboards.
- Graphs include role-relevant appointment/payment status breakdowns and financial views.
- Appointment details panel lifecycle is now reset on tab switches, role changes, and logout/login transitions, preventing stale dialog persistence.

### Verification Strategy
- Functional and regression tests were extended for payment-before-completion, refund generation, follow-up creation, CSV row completeness, and duplicate-slot prevention.
- A dedicated stress script (`scripts/stress_test.py`) executes concurrent booking/payment/completion/refund workflows against a live server.
- This approach validates both correctness and operational behavior during heavy usage scenarios.

### Validation Snapshot (Current Build)
- Automated test suite result: `60 passed`.
- Stress execution (stable server run) produced:
  - Doctors created: `4`
  - Patients created: `18`
  - Concurrent booking successes/conflicts: `16 / 2`
  - Payments successful: `16`
  - Consultations completed: `8`
  - Follow-ups auto-created: `8`
  - Refund records observed: `4`
  - Duplicate doctor/date/time slots: `0`
