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
            doctorSearch: '',
            doctorDepartmentFilter: '',
            doctorDepartmentQuery: '',
            patients: [],
            editingDoctorId: null,
            editingPatientId: null,
            adminAppointments: [],
            adminAppointmentFilters: {
                date: '',
                patient: '',
                doctor: '',
                status: '',
                payment: '',
                type: ''
            },
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
            doctorProfile: null,
            availabilityForm: {
                availability_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                availability_start: '09:00',
                availability_end: '17:00',
                slot_minutes: 30
            },
            selectedAppointment: null,
            appointmentDetails: null,
            treatmentForm: { diagnosis: '', prescription: '', notes: '', next_visit_date: '' },
            treatmentEditForm: { diagnosis: '', prescription: '', notes: '' },
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
        selectedDepartmentByQuery() {
            const needle = (this.doctorDepartmentQuery || '').trim().toLowerCase();
            if (!needle) {
                return null;
            }
            return this.departments.find((department) => (department.name || '').toLowerCase() === needle) || null;
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
            if (this.adminTab === 'stats') {
                this.$nextTick(() => this.renderAdminCharts());
            }
        },
        doctorTab() {
            this.closeAppointmentDetails();
            if (this.doctorTab === 'appointments') {
                this.$nextTick(() => this.renderDoctorCharts());
            }
        },
        patientTab() {
            this.closeAppointmentDetails();
            if (this.patientTab === 'appointments') {
                this.$nextTick(() => this.renderPatientCharts());
            }
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
            this.editingDoctorId = null;
            this.editingPatientId = null;
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
                await this.loadDoctorProfile();
            }
            if (this.hasRole('patient')) {
                await this.loadDoctorsForBooking();
                await this.loadPatientAppointments();
                await this.loadPayments();
            }
            await this.loadProfile();
        },
        buildQueryString(filters) {
            const params = new URLSearchParams();
            Object.entries(filters || {}).forEach(([key, value]) => {
                if (value !== null && value !== undefined && String(value).trim() !== '') {
                    params.append(key, String(value).trim());
                }
            });
            const qs = params.toString();
            return qs ? `?${qs}` : '';
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
            if (document.getElementById('adminStatsChart')) {
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
            }

            if (document.getElementById('adminPaymentsChart')) {
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
            }
        },

        // Render doctor charts from appointment statuses and earnings summary.
        renderDoctorCharts() {
            if (typeof Plotly === 'undefined') {
                return;
            }
            const booked = this.doctorAppointments.filter((a) => a.status === 'Booked').length;
            const completed = this.doctorAppointments.filter((a) => a.status === 'Completed').length;
            const cancelled = this.doctorAppointments.filter((a) => a.status === 'Cancelled').length;

            if (document.getElementById('doctorAppointmentsChart')) {
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
            }

            if (document.getElementById('doctorEarningsChart')) {
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
            }
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

            if (document.getElementById('patientAppointmentsChart')) {
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
            }

            if (document.getElementById('patientPaymentsChart')) {
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
            }
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
        syncDoctorDepartmentQueryFromId() {
            const selected = this.departments.find((department) => String(department.id) === String(this.newDoctor.department_id));
            this.doctorDepartmentQuery = selected ? selected.name : '';
        },
        onDoctorDepartmentInput() {
            const exact = this.selectedDepartmentByQuery;
            this.newDoctor.department_id = exact ? exact.id : '';
        },
        openCreateDoctor() {
            this.editingDoctorId = null;
            this.showAddDoctor = true;
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
            this.doctorDepartmentQuery = '';
        },
        openEditDoctor(doctor) {
            this.editingDoctorId = doctor.id;
            this.showAddDoctor = true;
            this.newDoctor = {
                name: doctor.name || '',
                username: doctor.username || '',
                password: '',
                email: doctor.email || '',
                phone: doctor.phone || '',
                department_id: doctor.department_id || '',
                availability_days: doctor.availability_days || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                availability_start: doctor.availability_start || '09:00',
                availability_end: doctor.availability_end || '17:00',
                slot_minutes: doctor.slot_minutes || 30,
                bio: doctor.bio || ''
            };
            this.syncDoctorDepartmentQueryFromId();
        },
        async loadDoctors() {
            try {
                const query = this.buildQueryString({
                    search: this.doctorSearch,
                    department_id: this.doctorDepartmentFilter
                });
                this.doctors = await apiCall('/admin/doctors' + query, 'GET');
            } catch (error) {
                await this.logError(error, 'loadDoctors');
            }
        },
        // Creates or updates doctor with structured availability fields.
        async saveDoctor() {
            try {
                this.onDoctorDepartmentInput();
                if (!this.newDoctor.department_id) {
                    return;
                }
                if (this.editingDoctorId) {
                    await apiCall(`/admin/doctors/${this.editingDoctorId}`, 'PUT', this.newDoctor);
                    this.showSuccess('Doctor updated.');
                } else {
                    await apiCall('/admin/doctors', 'POST', this.newDoctor);
                    this.showSuccess('Doctor added.');
                }
                this.showAddDoctor = false;
                this.editingDoctorId = null;
                await this.loadDoctors();
                await this.loadStats();
            } catch (error) {
                await this.logError(error, 'saveDoctor');
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
        openEditPatient(patient) {
            this.editingPatientId = patient.id;
            this.profileForm.name = patient.name || '';
            this.profileForm.email = patient.email || '';
            this.profileForm.phone = patient.phone || '';
            this.profileForm.history = patient.medical_history || '';
            this.profileForm.notification_pref = patient.notification_pref || 'email';
        },
        async updatePatient() {
            if (!this.editingPatientId) {
                return;
            }
            try {
                await apiCall(`/admin/patients/${this.editingPatientId}`, 'PUT', {
                    name: this.profileForm.name,
                    email: this.profileForm.email,
                    phone: this.profileForm.phone,
                    medical_history: this.profileForm.history,
                    notification_pref: this.profileForm.notification_pref
                });
                this.editingPatientId = null;
                await this.loadPatients();
                this.showSuccess('Patient updated.');
            } catch (error) {
                await this.logError(error, 'updatePatient');
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
                const query = this.buildQueryString(this.adminAppointmentFilters);
                this.adminAppointments = await apiCall('/admin/appointments' + query, 'GET');
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
        async loadDoctorProfile() {
            try {
                this.doctorProfile = await apiCall('/doctor/profile', 'GET');
                this.availabilityForm = {
                    availability_days: this.doctorProfile.availability_days || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                    availability_start: this.doctorProfile.availability_start || '09:00',
                    availability_end: this.doctorProfile.availability_end || '17:00',
                    slot_minutes: this.doctorProfile.slot_minutes || 30
                };
            } catch (error) {
                await this.logError(error, 'loadDoctorProfile');
            }
        },
        toggleAvailabilityDay(day) {
            const days = new Set(this.availabilityForm.availability_days || []);
            if (days.has(day)) {
                days.delete(day);
            } else {
                days.add(day);
            }
            this.availabilityForm.availability_days = Array.from(days);
        },
        async saveDoctorAvailability() {
            try {
                await apiCall('/doctor/availability', 'PUT', this.availabilityForm);
                await this.loadDoctorProfile();
                await this.loadDoctorsForBooking();
                this.showSuccess('Availability updated.');
            } catch (error) {
                await this.logError(error, 'saveDoctorAvailability');
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
            this.treatmentForm = { diagnosis: '', prescription: '', notes: '', next_visit_date: '' };
        },
        // Completes appointment and refreshes list.
        async completeAppointment() {
            try {
                const response = await apiCall(`/appointments/${this.selectedAppointment.id}/complete`, 'POST', this.treatmentForm);
                this.selectedAppointment = null;
                await this.loadDoctorAppointments();
                await this.loadDoctorPayments();
                if (response && response.follow_up) {
                    this.showSuccess(`Appointment completed. Follow-up booked: ${response.follow_up.date} ${response.follow_up.time}`);
                } else {
                    this.showSuccess('Appointment completed.');
                }
            } catch (error) {
                await this.logError(error, 'completeAppointment');
            }
        },
        startEditTreatment(appointment) {
            this.selectedAppointment = appointment;
            this.treatmentEditForm = {
                diagnosis: appointment.treatment ? appointment.treatment.diagnosis : '',
                prescription: appointment.treatment ? appointment.treatment.prescription : '',
                notes: appointment.treatment ? appointment.treatment.notes : ''
            };
        },
        async updateTreatment() {
            if (!this.selectedAppointment) {
                return;
            }
            try {
                await apiCall(`/doctor/appointments/${this.selectedAppointment.id}/treatment`, 'PUT', this.treatmentEditForm);
                this.selectedAppointment = null;
                this.closeAppointmentDetails();
                await this.loadDoctorAppointments();
                this.showSuccess('Treatment updated.');
            } catch (error) {
                await this.logError(error, 'updateTreatment');
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
                const profile = this.hasRole('doctor') ? await apiCall('/doctor/profile', 'GET') : await apiCall('/profile', 'GET');
                this.syncProfileForm(profile);
                this.profileForm.history = profile.medical_history || '';
                this.profileForm.notification_pref = profile.notification_pref || 'email';
            } catch (error) {
                await this.logError(error, 'loadProfile');
            }
        },
        // Persists profile edits and reloads current user identity data.
        async saveProfile() {
            if (this.hasRole('doctor')) {
                return;
            }
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