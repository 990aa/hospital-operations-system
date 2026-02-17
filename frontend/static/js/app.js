/**
 * Hospital Management System - Frontend Application
 * 
 * This file contains all the Vue.js logic for the single-page application.
 * It handles authentication, role-based dashboards, and API communications.
 * 
 * Structure:
 * - API Helper Function
 * - Vue App Setup with Data and Methods
 * - Dashboard-specific logic (Admin, Doctor, Patient)
 */


// API HELPER FUNCTION

/**
 * Makes an HTTP request to the backend API
 * @param {string} url - API endpoint (e.g., '/login', '/admin/stats')
 * @param {string} method - HTTP method ('GET', 'POST', 'PUT', 'DELETE')
 * @param {object} body - Request body for POST/PUT requests
 * @returns {Promise} Response data or error
 */
async function apiCall(url, method = 'GET', body = null) {
    const options = {
        method: method,
        headers: { 'Content-Type': 'application/json' }
    };
    
    // Add body for POST/PUT requests
    if (body) {
        options.body = JSON.stringify(body);
    }
    
    try {
        // Make the fetch request
        const response = await fetch('/api' + url, options);
        const data = await response.json();
        
        // Handle errors
        if (!response.ok) {
            throw new Error(data.message || 'Request failed');
        }
        
        return data;
    } catch (error) {
        throw error;
    }
}


// VUE.JS APPLICATION

const { createApp } = Vue;

createApp({
    /**
     * Data function - defines all reactive state variables
     */
    data() {
        return {
            // ========== Authentication State ==========
            currentUser: null,              // Logged-in user object
            isLogin: true,                  // Toggle between login/register forms
            selectedRole: 'patient',        // Selected role for login
            authForm: {                     // Form data for login/register
                username: '',
                password: '',
                name: '',
                email: ''
            },
            
            // ========= Alert Messages ==========
            alertMsg: '',                   // Alert message text
            alertType: 'success',           // Alert type: 'success', 'danger', 'warning'
            
            // ========== Admin Dashboard Data ==========
            adminTab: 'stats',              // Current tab in admin dashboard
            stats: {},                      // Statistics data
            doctors: [],                    // List of doctors
            departments: [],                // List of departments
            patients: [],                   // List of patients
            showAddDoctor: false,           // Show/hide add doctor form
            newDoctor: {                    // Form data for new doctor
                name: '',
                username: '',
                password: '',
                email: '',
                phone: '',
                department_id: ''
            },
            patientSearch: '',              // Patient search query
            
            // ========== Doctor Dashboard Data ==========
            doctorTab: 'appointments',      // Current tab in doctor dashboard
            doctorAppointments: [],         // Doctor's appointments list
            selectedAppointment: null,      // Currently selected appointment for completion
            treatmentForm: {                // Form data for completing appointment
                diagnosis: '',
                prescription: '',
                notes: ''
            },
            reportMonth: new Date().getMonth() + 1,  // Month for PDF report
            reportYear: new Date().getFullYear(),    // Year for PDF report
            
            // ========== Patient Dashboard Data ==========
            patientTab: 'book',             // Current tab in patient dashboard
            patientAppointments: [],        // Patient's appointments list
            availableDoctors: [],           // List of doctors for booking
            bookingForm: {                  // Form data for booking appointment
                doctor_id: '',
                date: '',
                time: ''
            },
            paymentAppointment: null,       // Currently selected appointment for payment
            paymentForm: {                  // Form data for payment
                amount: 100.00,
                payment_method: 'credit_card',
                card_number: ''
            },
            payments: []                    // List of patient payments
        };
    },
    
    /**
     * Mounted lifecycle hook - runs when component is mounted
     */
    async mounted() {
        // Check if user is already logged in
        await this.checkLogin();
        
        // Load initial data based on role
        if (this.currentUser) {
            if (this.hasRole('admin')) {
                await this.loadStats();
                await this.loadDepartments();
            }
        }
    },
    
    /**
     * Methods - all functions for the application
     */
    methods: {
        // ========================================
        // AUTHENTICATION METHODS
        // ========================================
        
        /**
         * Check if user is logged in by calling /current-user endpoint
         */
        async checkLogin() {
            try {
                const data = await apiCall('/current-user', 'GET');
                if (data && data.id) {
                    this.currentUser = data;
                }
            } catch (error) {
                // User not logged in, stay on login page
                console.log('Not logged in');
            }
        },
        
        /**
         * Handle login or registration form submission
         */
        async handleAuth() {
            try {
                if (this.isLogin) {
                    // LOGIN
                    const response = await apiCall('/login', 'POST', {
                        username: this.authForm.username,
                        password: this.authForm.password
                    });
                    
                    // Set current user and load appropriate data
                    this.currentUser = response.user;
                    this.showAlert('Login successful!', 'success');
                    
                    // Load data based on role
                    if (this.hasRole('admin')) {
                        await this.loadStats();
                        await this.loadDepartments();
                    }
                } else {
                    // REGISTER (Patient only)
                    await apiCall('/register', 'POST', {
                        username: this.authForm.username,
                        password: this.authForm.password,
                        name: this.authForm.name,
                        email: this.authForm.email || ''
                    });
                    
                    this.showAlert('Registration successful! Please login.', 'success');
                    this.isLogin = true;
                    
                    // Clear form
                    this.authForm = { username: '', password: '', name: '', email: '' };
                }
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        /**
         * Logout the current user
         */
        async logout() {
            try {
                await apiCall('/logout', 'POST');
                this.currentUser = null;
                this.authForm = { username: '', password: '', name: '', email: '' };
                this.isLogin = true;
                this.showAlert('Logged out successfully', 'success');
            } catch (error) {
                this.showAlert('Logout failed', 'danger');
            }
        },
        
        /**
         * Check if current user has a specific role
         * @param {string} role - Role name ('admin', 'doctor', 'patient')
         * @returns {boolean}
         */
        hasRole(role) {
            return this.currentUser && this.currentUser.roles && this.currentUser.roles.includes(role);
        },
        
        /**
         * Get formatted role name for display
         * @returns {string} Capitalized role name
         */
        getUserRole() {
            if (!this.currentUser || !this.currentUser.roles) return '';
            const role = this.currentUser.roles[0];
            return role.charAt(0).toUpperCase() + role.slice(1);
        },
        
        // ========================================
        // ALERT METHODS
        // ========================================
        
        /**
         * Show alert message
         * @param {string} message - Alert message text
         * @param {string} type - Alert type ('success', 'danger', 'warning', 'info')
         */
        showAlert(message, type = 'success') {
            this.alertMsg = message;
            this.alertType = type;
            
            // Auto-hide after 5 seconds
            setTimeout(() => {
                this.alertMsg = '';
            }, 5000);
        },
        
        // ========================================
        // ADMIN METHODS
        // ========================================
        
        /**
         * Load admin statistics from backend
         */
        async loadStats() {
            try {
                this.stats = await apiCall('/admin/stats', 'GET');
            } catch (error) {
                this.showAlert('Failed to load statistics', 'danger');
            }
        },
        
        /**
         * Load list of departments
         */
        async loadDepartments() {
            try {
                this.departments = await apiCall('/departments', 'GET');
            } catch (error) {
                this.showAlert('Failed to load departments', 'danger');
            }
        },
        
        /**
         * Load list of doctors
         */
        async loadDoctors() {
            try {
                this.doctors = await apiCall('/admin/doctors', 'GET');
            } catch (error) {
                this.showAlert('Failed to load doctors', 'danger');
            }
        },
        
        /**
         * Add a new doctor
         */
        async addDoctor() {
            try {
                await apiCall('/admin/doctor', 'POST', this.newDoctor);
                this.showAlert('Doctor added successfully', 'success');
                
                // Reset form and reload doctors
                this.newDoctor = { name: '', username: '', password: '', email: '', phone: '', department_id: '' };
                this.showAddDoctor = false;
                await this.loadDoctors();
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        /**
         * Delete a doctor
         * @param {number} doctorId - Doctor ID to delete
         */
        async deleteDoctor(doctorId) {
            if (!confirm('Are you sure you want to delete this doctor?')) return;
            
            try {
                await apiCall(`/admin/doctor/${doctorId}`, 'DELETE');
                this.showAlert('Doctor deleted successfully', 'success');
                await this.loadDoctors();
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        /**
         * Load list of patients with search
         */
        async loadPatients() {
            try {
                const query = this.patientSearch ? `?search=${this.patientSearch}` : '';
                this.patients = await apiCall('/admin/patients' + query, 'GET');
            } catch (error) {
                this.showAlert('Failed to load patients', 'danger');
            }
        },
        
        /**
         * Delete a patient
         * @param {number} patientId - Patient ID to delete
         */
        async deletePatient(patientId) {
            if (!confirm('Are you sure you want to delete this patient?')) return;
            
            try {
                await apiCall(`/admin/patient/${patientId}`, 'DELETE');
                this.showAlert('Patient deleted successfully', 'success');
                await this.loadPatients();
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        // ========================================
        // DOCTOR METHODS
        // ========================================
        
        /**
         * Load doctor's appointments
         */
        async loadDoctorAppointments() {
            try {
                this.doctorAppointments = await apiCall('/doctor/appointments', 'GET');
            } catch (error) {
                this.showAlert('Failed to load appointments', 'danger');
            }
        },
        
        /**
         * Show complete appointment form
         * @param {object} appointment - Appointment object
         */
        showCompleteAppointment(appointment) {
            this.selectedAppointment = appointment;
            this.treatmentForm = { diagnosis: '', prescription: '', notes: '' };
        },
        
        /**
         * Complete an appointment with treatment details
         */
        async completeAppointment() {
            try {
                await apiCall(`/appointments/${this.selectedAppointment.id}/complete`, 'POST', this.treatmentForm);
                this.showAlert('Appointment completed successfully', 'success');
                
                // Reset and reload
                this.selectedAppointment = null;
                await this.loadDoctorAppointments();
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        /**
         * Download monthly PDF report
         */
        async downloadMonthlyReport() {
            try {
                // Open PDF in new window
                window.open(`/api/doctor/monthly-report/${this.reportMonth}/${this.reportYear}`, '_blank');
                this.showAlert('Downloading report...', 'success');
            } catch (error) {
                this.showAlert('Failed to download report', 'danger');
            }
        },
        
        // ========================================
        // PATIENT METHODS
        // ========================================
        
        /**
         * Load list of doctors for booking
         */
        async loadDoctorsForBooking() {
            try {
                this.availableDoctors = await apiCall('/doctors', 'GET');
            } catch (error) {
                this.showAlert('Failed to load doctors', 'danger');
            }
        },
        
        /**
         * Book a new appointment
         */
        async bookAppointment() {
            try {
                await apiCall('/patient/appointment', 'POST', this.bookingForm);
                this.showAlert('Appointment booked successfully!', 'success');
                
                // Reset form
                this.bookingForm = { doctor_id: '', date: '', time: '' };
                
                // Switch to appointments tab
                this.patientTab = 'appointments';
                await this.loadPatientAppointments();
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        /**
         * Load patient's appointments
         */
        async loadPatientAppointments() {
            try {
                this.patientAppointments = await apiCall('/patient/appointments', 'GET');
            } catch (error) {
                this.showAlert('Failed to load appointments', 'danger');
            }
        },
        
        /**
         * Cancel an appointment
         * @param {number} appointmentId - Appointment ID to cancel
         */
        async cancelAppointment(appointmentId) {
            if (!confirm('Are you sure you want to cancel this appointment?')) return;
            
            try {
                await apiCall(`/patient/appointment/${appointmentId}`, 'DELETE');
                this.showAlert('Appointment cancelled successfully', 'success');
                await this.loadPatientAppointments();
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        /**
         * Show payment form for an appointment
         * @param {object} appointment - Appointment object
         */
        showPaymentForm(appointment) {
            this.paymentAppointment = appointment;
            this.paymentForm = {
                amount: 100.00,
                payment_method: 'credit_card',
                card_number: ''
            };
        },
        
        /**
         * Process payment for an appointment
         */
        async processPayment() {
            try {
                await apiCall(`/patient/payment/appointment/${this.paymentAppointment.id}`, 'POST', this.paymentForm);
                this.showAlert('Payment processed successfully!', 'success');
                
                // Reset and reload
                this.paymentAppointment = null;
                await this.loadPatientAppointments();
            } catch (error) {
                this.showAlert(error.message, 'danger');
            }
        },
        
        /**
         * Load patient's payment history
         */
        async loadPayments() {
            try {
                this.payments = await apiCall('/patient/payments', 'GET');
            } catch (error) {
                this.showAlert('Failed to load payments', 'danger');
            }
        }
    }
}).mount('#app');  // Mount the Vue app to the #app div
