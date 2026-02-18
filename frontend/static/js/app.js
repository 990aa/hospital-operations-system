// Send frontend/runtime diagnostic logs to backend terminal.
// This keeps user-facing UI clean while preserving full debug context server-side.
async function sendClientLog(payload) {
    try {
        await fetch('/api/client-log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } catch (_) {
        // intentionally ignored
    }
}

// Minimal API wrapper used by all frontend actions.
// Key behaviors:
// 1) Always call /api-prefixed routes.
// 2) Parse response text safely and detect non-JSON server responses.
// 3) Forward all failures to terminal logs through /api/client-log.
async function apiCall(url, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    // Perform request once options are prepared.
    const response = await fetch('/api' + url, options);
    const raw = await response.text();
    let data = null;

    try {
        // Parse explicit JSON payload from server.
        data = raw ? JSON.parse(raw) : null;
    } catch (error) {
        // If backend returns HTML (e.g. route mismatch), log full raw response.
        await sendClientLog({
            type: 'JSON_PARSE_ERROR',
            url,
            method,
            status: response.status,
            raw,
            parseError: error.message
        });
        throw new Error('Request failed');
    }

    // Non-2xx responses are logged in full and converted to thrown Error.
    if (!response.ok) {
        await sendClientLog({
            type: 'API_ERROR',
            url,
            method,
            status: response.status,
            requestBody: body,
            response: data
        });
        throw new Error((data && data.message) || 'Request failed');
    }

    return data;
}

const { createApp } = Vue;

createApp({
    data() {
        return {
            // Authentication and shared UI state.
            currentUser: null,
            isLogin: true,
            selectedRole: 'patient',
            authForm: {
                username: '',
                password: '',
                name: '',
                email: ''
            },
            alertMsg: '',
            alertType: 'success',

            // Admin dashboard state.
            adminTab: 'stats',
            stats: {},
            doctors: [],
            departments: [],
            departmentSearch: '',
            newDepartmentName: '',
            patients: [],
            adminAppointments: [],
            adminPayments: [],
            adminPaymentSummary: {},
            showAddDoctor: false,
            newDoctor: {
                name: '',
                username: '',
                password: '',
                email: '',
                phone: '',
                department_id: '',
                availability_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                availability_start: '09:00',
                availability_end: '17:00',
                slot_minutes: 30,
                bio: ''
            },
            patientSearch: '',

            // Doctor dashboard state.
            doctorTab: 'appointments',
            doctorAppointments: [],
            doctorPayments: [],
            doctorPaymentSummary: {},
            selectedAppointment: null,
            appointmentDetails: null,
            treatmentForm: { diagnosis: '', prescription: '', notes: '' },
            reportMonth: new Date().getMonth() + 1,
            reportYear: new Date().getFullYear(),

            // Patient dashboard state.
            patientTab: 'book',
            patientAppointments: [],
            availableDoctors: [],
            selectedDoctorProfile: null,
            bookingForm: {
                doctor_id: '',
                date: ''
            },
            paymentAppointment: null,
            paymentForm: {
                amount: 500,
                payment_method: 'credit_card',
                card_number: ''
            },
            payments: [],

            // Shared profile editor state used by all roles.
            profileForm: {
                name: '',
                email: '',
                phone: '',
                history: '',
                notification_pref: 'email'
            },
            weekdayOptions: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        };
    },

    computed: {
        // Case-insensitive client-side department filtering for typeahead behavior.
        filteredDepartments() {
            const q = (this.departmentSearch || '').trim().toLowerCase();
            if (!q) {
                return this.departments;
            }
            return this.departments.filter((department) =>
                (department.name || '').toLowerCase().includes(q)
            );
        },
        // Resolve currently selected doctor from dropdown value.
        selectedDoctor() {
            return this.availableDoctors.find((doctor) => String(doctor.id) === String(this.bookingForm.doctor_id)) || null;
        },
        // Date options constrained to next-7-day availability with free slots.
        selectableDates() {
            if (!this.selectedDoctor || !this.selectedDoctor.upcoming_availability) {
                return [];
            }
            return this.selectedDoctor.upcoming_availability.filter((day) => day.remaining_slots > 0);
        }
    },

    watch: {
        // Ensure detail/popup state never leaks across role switches or tab navigation.
        adminTab() {
            this.closeAppointmentDetails();
        },
        doctorTab() {
            this.closeAppointmentDetails();
        },
        patientTab() {
            this.closeAppointmentDetails();
        },
        currentUser() {
            this.closeAppointmentDetails();
        }
    },

    async mounted() {
        // Restore session and load role-specific data if user is already logged in.
        await this.checkLogin();
        if (this.currentUser) {
            await this.loadInitialDataForRole();
        }
    },

    methods: {
        // Reset transient dialogs/forms to avoid stale view state.
        resetTransientState() {
            this.closeAppointmentDetails();
            this.selectedAppointment = null;
            this.paymentAppointment = null;
        },
        // Success-only toast helper; errors are never rendered to UI by design.
        showSuccess(message) {
            this.alertType = 'success';
            this.alertMsg = message;
            setTimeout(() => {
                this.alertMsg = '';
            }, 3000);
        },
        // Centralized frontend error logger.
        // Emits to browser console + backend terminal endpoint.
        async logError(error, context) {
            const payload = {
                type: 'FRONTEND_RUNTIME_ERROR',
                context,
                message: error && error.message ? error.message : String(error),
                stack: error && error.stack ? error.stack : null
            };
            console.error(context, error);
            await sendClientLog(payload);
        },
        // Role helper used for conditional rendering by dashboard sections.
        hasRole(role) {
            return this.currentUser && this.currentUser.roles && this.currentUser.roles.includes(role);
        },
        // Human-friendly role label shown in navbar.
        getUserRole() {
            if (!this.currentUser || !this.currentUser.roles || !this.currentUser.roles.length) {
                return '';
            }
            const role = this.currentUser.roles[0];
            return role.charAt(0).toUpperCase() + role.slice(1);
        },
        // Checks active session without interrupting unauthenticated startup flow.
        async checkLogin() {
            try {
                const data = await apiCall('/current-user', 'GET');
                if (data && data.id) {
                    this.currentUser = data;
                    this.syncProfileForm(data);
                }
            } catch (_) {
                // not logged in
            }
        },
        // Loads only the data required for the current role to keep frontend minimal.
        async loadInitialDataForRole() {
            this.resetTransientState();
            if (this.hasRole('admin')) {
                await this.loadStats();
                await this.loadDepartments();
                await this.loadDoctors();
                await this.loadPatients();
                await this.loadAdminAppointments();
                await this.loadAdminPayments();
            }
            if (this.hasRole('doctor')) {
                await this.loadDoctorAppointments();
                await this.loadDoctorPayments();
            }
            if (this.hasRole('patient')) {
                await this.loadDoctorsForBooking();
                await this.loadPatientAppointments();
                await this.loadPayments();
            }
            await this.loadProfile();
        },
        // Copies user profile fields from API response into local form model.
        syncProfileForm(user) {
            this.profileForm.name = user.name || '';
            this.profileForm.email = user.email || '';
            this.profileForm.phone = user.phone || '';
        },
        // Login/register handler. Registration keeps password visible per requirement.
        async handleAuth() {
            try {
                if (this.isLogin) {
                    const response = await apiCall('/login', 'POST', {
                        username: this.authForm.username,
                        password: this.authForm.password
                    });
                    this.currentUser = response.user;
                    this.resetTransientState();
                    this.syncProfileForm(response.user);
                    await this.loadInitialDataForRole();
                } else {
                    await apiCall('/register', 'POST', {
                        username: this.authForm.username,
                        password: this.authForm.password,
                        name: this.authForm.name,
                        email: this.authForm.email || ''
                    });
                    this.isLogin = true;
                    this.authForm = { username: '', password: '', name: '', email: '' };
                    this.showSuccess('Registration successful. Please login.');
                }
            } catch (error) {
                await this.logError(error, 'handleAuth');
            }
        },
        // Logout always clears local auth state, even if API logout fails.
        async logout() {
            try {
                await apiCall('/logout', 'POST');
            } catch (error) {
                await this.logError(error, 'logout');
            }
            this.resetTransientState();
            this.currentUser = null;
            this.alertMsg = '';
            this.isLogin = true;
            this.authForm = { username: '', password: '', name: '', email: '' };
        },

        // Render admin charts using Plotly from current stats and payment summary.
        renderAdminCharts() {
            if (typeof Plotly === 'undefined') {
                return;
            }
            Plotly.newPlot(
                'adminStatsChart',
                [
                    {
                        type: 'bar',
                        x: ['Doctors', 'Patients', 'Appointments'],
                        y: [
                            this.stats.total_doctors || 0,
                            this.stats.total_patients || 0,
                            this.stats.total_appointments || 0
                        ],
                        marker: { color: ['#388e3c', '#1976d2', '#424242'] }
                    }
                ],
                { margin: { t: 20, r: 10, l: 40, b: 40 }, height: 280 },
                { displayModeBar: false, responsive: true }
            );

            Plotly.newPlot(
                'adminPaymentsChart',
                [
                    {
                        type: 'pie',
                        labels: ['Collected', 'Refunded'],
                        values: [
                            this.adminPaymentSummary.total_collected || 0,
                            this.adminPaymentSummary.total_refunded || 0
                        ],
                        marker: { colors: ['#388e3c', '#d32f2f'] }
                    }
                ],
                { margin: { t: 20, r: 10, l: 10, b: 10 }, height: 280 },
                { displayModeBar: false, responsive: true }
            );
        },

        // Render doctor charts from appointment statuses and earnings summary.
        renderDoctorCharts() {
            if (typeof Plotly === 'undefined') {
                return;
            }
            const booked = this.doctorAppointments.filter((a) => a.status === 'Booked').length;
            const completed = this.doctorAppointments.filter((a) => a.status === 'Completed').length;
            const cancelled = this.doctorAppointments.filter((a) => a.status === 'Cancelled').length;

            Plotly.newPlot(
                'doctorAppointmentsChart',
                [
                    {
                        type: 'bar',
                        x: ['Booked', 'Completed', 'Cancelled'],
                        y: [booked, completed, cancelled],
                        marker: { color: ['#1976d2', '#388e3c', '#d32f2f'] }
                    }
                ],
                { margin: { t: 20, r: 10, l: 40, b: 40 }, height: 260 },
                { displayModeBar: false, responsive: true }
            );

            Plotly.newPlot(
                'doctorEarningsChart',
                [
                    {
                        type: 'pie',
                        labels: ['Earned', 'Refunded'],
                        values: [
                            this.doctorPaymentSummary.total_earned || 0,
                            this.doctorPaymentSummary.total_refunded || 0
                        ],
                        marker: { colors: ['#388e3c', '#d32f2f'] }
                    }
                ],
                { margin: { t: 20, r: 10, l: 10, b: 10 }, height: 260 },
                { displayModeBar: false, responsive: true }
            );
        },

        // Render patient charts from appointment and payment data.
        renderPatientCharts() {
            if (typeof Plotly === 'undefined') {
                return;
            }
            const booked = this.patientAppointments.filter((a) => a.status === 'Booked').length;
            const completed = this.patientAppointments.filter((a) => a.status === 'Completed').length;
            const cancelled = this.patientAppointments.filter((a) => a.status === 'Cancelled').length;
            const paid = this.payments.filter((p) => p.status === 'completed').length;
            const refunded = this.payments.filter((p) => p.status === 'refunded').length;

            Plotly.newPlot(
                'patientAppointmentsChart',
                [
                    {
                        type: 'bar',
                        x: ['Booked', 'Completed', 'Cancelled'],
                        y: [booked, completed, cancelled],
                        marker: { color: ['#1976d2', '#388e3c', '#d32f2f'] }
                    }
                ],
                { margin: { t: 20, r: 10, l: 40, b: 40 }, height: 260 },
                { displayModeBar: false, responsive: true }
            );

            Plotly.newPlot(
                'patientPaymentsChart',
                [
                    {
                        type: 'pie',
                        labels: ['Paid', 'Refunded'],
                        values: [paid, refunded],
                        marker: { colors: ['#388e3c', '#d32f2f'] }
                    }
                ],
                { margin: { t: 20, r: 10, l: 10, b: 10 }, height: 260 },
                { displayModeBar: false, responsive: true }
            );
        },

        // --- Admin methods ---
        async loadStats() {
            try {
                this.stats = await apiCall('/admin/stats', 'GET');
                this.$nextTick(() => this.renderAdminCharts());
            } catch (error) {
                await this.logError(error, 'loadStats');
            }
        },
        // Server-side filtered departments (case-insensitive search).
        async loadDepartments() {
            try {
                const query = this.departmentSearch ? `?search=${encodeURIComponent(this.departmentSearch)}` : '';
                this.departments = await apiCall('/departments' + query, 'GET');
            } catch (error) {
                await this.logError(error, 'loadDepartments');
            }
        },
        // Creates department directly from doctor form flow.
        async createDepartment() {
            const name = (this.newDepartmentName || '').trim();
            if (!name) {
                return;
            }
            try {
                const response = await apiCall('/departments', 'POST', {
                    name,
                    description: ''
                });
                this.newDepartmentName = '';
                await this.loadDepartments();
                if (response && response.department) {
                    this.newDoctor.department_id = response.department.id;
                }
                this.showSuccess('Department saved.');
            } catch (error) {
                await this.logError(error, 'createDepartment');
            }
        },
        // Toggles weekday checkbox in add-doctor availability form.
        toggleDoctorDay(day) {
            const days = new Set(this.newDoctor.availability_days);
            if (days.has(day)) {
                days.delete(day);
            } else {
                days.add(day);
            }
            this.newDoctor.availability_days = Array.from(days);
        },
        async loadDoctors() {
            try {
                this.doctors = await apiCall('/admin/doctors', 'GET');
            } catch (error) {
                await this.logError(error, 'loadDoctors');
            }
        },
        // Creates doctor with structured availability fields.
        async addDoctor() {
            try {
                await apiCall('/admin/doctors', 'POST', this.newDoctor);
                this.newDoctor = {
                    name: '',
                    username: '',
                    password: '',
                    email: '',
                    phone: '',
                    department_id: '',
                    availability_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                    availability_start: '09:00',
                    availability_end: '17:00',
                    slot_minutes: 30,
                    bio: ''
                };
                this.showAddDoctor = false;
                await this.loadDoctors();
                this.showSuccess('Doctor added.');
            } catch (error) {
                await this.logError(error, 'addDoctor');
            }
        },
        async deleteDoctor(doctorId) {
            if (!confirm('Delete this doctor?')) {
                return;
            }
            try {
                await apiCall(`/admin/doctors/${doctorId}`, 'DELETE');
                await this.loadDoctors();
                await this.loadStats();
            } catch (error) {
                await this.logError(error, 'deleteDoctor');
            }
        },
        async loadPatients() {
            try {
                const query = this.patientSearch ? `?search=${encodeURIComponent(this.patientSearch)}` : '';
                const response = await apiCall('/admin/patients' + query, 'GET');
                this.patients = response.patients || [];
            } catch (error) {
                await this.logError(error, 'loadPatients');
            }
        },
        async deletePatient(patientId) {
            if (!confirm('Delete this patient?')) {
                return;
            }
            try {
                await apiCall(`/admin/patients/${patientId}`, 'DELETE');
                await this.loadPatients();
                await this.loadStats();
            } catch (error) {
                await this.logError(error, 'deletePatient');
            }
        },
        // Loads admin appointment visibility table.
        async loadAdminAppointments() {
            try {
                this.adminAppointments = await apiCall('/my-appointments', 'GET');
            } catch (error) {
                await this.logError(error, 'loadAdminAppointments');
            }
        },
        async loadAdminPayments() {
            try {
                const response = await apiCall('/admin/payments', 'GET');
                this.adminPayments = response.payments || [];
                this.adminPaymentSummary = response.summary || {};
                this.$nextTick(() => this.renderAdminCharts());
            } catch (error) {
                await this.logError(error, 'loadAdminPayments');
            }
        },

        // --- Doctor methods ---
        async loadDoctorAppointments() {
            try {
                this.doctorAppointments = await apiCall('/doctor/appointments', 'GET');
                this.$nextTick(() => this.renderDoctorCharts());
            } catch (error) {
                await this.logError(error, 'loadDoctorAppointments');
            }
        },
        async loadDoctorPayments() {
            try {
                const response = await apiCall('/doctor/payments', 'GET');
                this.doctorPayments = response.payments || [];
                this.doctorPaymentSummary = response.summary || {};
                this.$nextTick(() => this.renderDoctorCharts());
            } catch (error) {
                await this.logError(error, 'loadDoctorPayments');
            }
        },
        showAppointmentDetails(appointment) {
            this.appointmentDetails = appointment;
        },
        closeAppointmentDetails() {
            this.appointmentDetails = null;
        },
        // Opens treatment form for selected booked appointment.
        showCompleteAppointment(appointment) {
            this.selectedAppointment = appointment;
            this.treatmentForm = { diagnosis: '', prescription: '', notes: '' };
        },
        // Completes appointment and refreshes list.
        async completeAppointment() {
            try {
                await apiCall(`/appointments/${this.selectedAppointment.id}/complete`, 'POST', this.treatmentForm);
                this.selectedAppointment = null;
                await this.loadDoctorAppointments();
                await this.loadDoctorPayments();
                this.showSuccess('Appointment completed.');
            } catch (error) {
                await this.logError(error, 'completeAppointment');
            }
        },
        // Opens backend PDF report endpoint in new tab.
        downloadMonthlyReport() {
            window.open(`/api/doctor/monthly-report/${this.reportMonth}/${this.reportYear}`, '_blank');
        },

        // --- Patient methods ---
        async loadDoctorsForBooking() {
            try {
                this.availableDoctors = await apiCall('/doctors', 'GET');
            } catch (error) {
                await this.logError(error, 'loadDoctorsForBooking');
            }
        },
        // Auto-select first available date whenever doctor selection changes.
        onDoctorChange() {
            this.selectedDoctorProfile = this.selectedDoctor;
            const firstDate = this.selectableDates.length ? this.selectableDates[0].date : '';
            this.bookingForm.date = firstDate;
        },
        // Books appointment by date only; backend assigns earliest available time slot.
        async bookAppointment() {
            if (!this.bookingForm.doctor_id || !this.bookingForm.date) {
                return;
            }
            try {
                const response = await apiCall('/appointments', 'POST', {
                    doctor_id: Number(this.bookingForm.doctor_id),
                    date: this.bookingForm.date
                });
                await this.loadDoctorsForBooking();
                await this.loadPatientAppointments();
                await this.loadPayments();
                this.showSuccess(`Appointment booked at ${response.assigned_time}`);
            } catch (error) {
                await this.logError(error, 'bookAppointment');
            }
        },
        // Loads unified appointment feed for patient.
        async loadPatientAppointments() {
            try {
                this.patientAppointments = await apiCall('/my-appointments', 'GET');
                this.$nextTick(() => this.renderPatientCharts());
            } catch (error) {
                await this.logError(error, 'loadPatientAppointments');
            }
        },
        // Cancels appointment through shared cancellation endpoint.
        async cancelAppointment(appointmentId) {
            if (!confirm('Cancel this appointment?')) {
                return;
            }
            try {
                await apiCall(`/appointments/${appointmentId}/cancel`, 'POST');
                await this.loadPatientAppointments();
                await this.loadPayments();
            } catch (error) {
                await this.logError(error, 'cancelAppointment');
            }
        },
        showPaymentForm(appointment) {
            this.paymentAppointment = appointment;
            this.paymentForm = {
                amount: 500,
                payment_method: 'credit_card',
                card_number: ''
            };
        },
        async processPayment() {
            if (!this.paymentAppointment) {
                return;
            }
            try {
                await apiCall(
                    `/patient/payment/appointment/${this.paymentAppointment.id}`,
                    'POST',
                    this.paymentForm
                );
                this.paymentAppointment = null;
                await this.loadPatientAppointments();
                await this.loadPayments();
                this.showSuccess('Payment completed.');
            } catch (error) {
                await this.logError(error, 'processPayment');
            }
        },
        // Payment history loader (dummy payment portal backend).
        async loadPayments() {
            try {
                this.payments = await apiCall('/patient/payments', 'GET');
                this.$nextTick(() => this.renderPatientCharts());
            } catch (error) {
                await this.logError(error, 'loadPayments');
            }
        },

        // Profile methods shared by admin/doctor/patient tabs.
        async loadProfile() {
            try {
                const profile = await apiCall('/profile', 'GET');
                this.syncProfileForm(profile);
                this.profileForm.history = profile.medical_history || '';
                this.profileForm.notification_pref = profile.notification_pref || 'email';
            } catch (error) {
                await this.logError(error, 'loadProfile');
            }
        },
        // Persists profile edits and reloads current user identity data.
        async saveProfile() {
            try {
                await apiCall('/profile', 'POST', this.profileForm);
                const user = await apiCall('/current-user', 'GET');
                this.currentUser = user;
                this.showSuccess('Profile updated.');
            } catch (error) {
                await this.logError(error, 'saveProfile');
            }
        }
    }
}).mount('#app');