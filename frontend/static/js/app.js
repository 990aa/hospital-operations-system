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

async function apiCall(url, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch('/api' + url, options);
    const raw = await response.text();
    let data = null;

    try {
        data = raw ? JSON.parse(raw) : null;
    } catch (error) {
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

            adminTab: 'stats',
            stats: {},
            doctors: [],
            departments: [],
            departmentSearch: '',
            newDepartmentName: '',
            patients: [],
            adminAppointments: [],
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

            doctorTab: 'appointments',
            doctorAppointments: [],
            selectedAppointment: null,
            treatmentForm: { diagnosis: '', prescription: '', notes: '' },
            reportMonth: new Date().getMonth() + 1,
            reportYear: new Date().getFullYear(),

            patientTab: 'book',
            patientAppointments: [],
            availableDoctors: [],
            selectedDoctorProfile: null,
            bookingForm: {
                doctor_id: '',
                date: ''
            },
            payments: [],

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
        filteredDepartments() {
            const q = (this.departmentSearch || '').trim().toLowerCase();
            if (!q) {
                return this.departments;
            }
            return this.departments.filter((department) =>
                (department.name || '').toLowerCase().includes(q)
            );
        },
        selectedDoctor() {
            return this.availableDoctors.find((doctor) => String(doctor.id) === String(this.bookingForm.doctor_id)) || null;
        },
        selectableDates() {
            if (!this.selectedDoctor || !this.selectedDoctor.upcoming_availability) {
                return [];
            }
            return this.selectedDoctor.upcoming_availability.filter((day) => day.remaining_slots > 0);
        }
    },

    async mounted() {
        await this.checkLogin();
        if (this.currentUser) {
            await this.loadInitialDataForRole();
        }
    },

    methods: {
        showSuccess(message) {
            this.alertType = 'success';
            this.alertMsg = message;
            setTimeout(() => {
                this.alertMsg = '';
            }, 3000);
        },
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
        hasRole(role) {
            return this.currentUser && this.currentUser.roles && this.currentUser.roles.includes(role);
        },
        getUserRole() {
            if (!this.currentUser || !this.currentUser.roles || !this.currentUser.roles.length) {
                return '';
            }
            const role = this.currentUser.roles[0];
            return role.charAt(0).toUpperCase() + role.slice(1);
        },
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
        async loadInitialDataForRole() {
            if (this.hasRole('admin')) {
                await this.loadStats();
                await this.loadDepartments();
                await this.loadDoctors();
                await this.loadPatients();
                await this.loadAdminAppointments();
            }
            if (this.hasRole('doctor')) {
                await this.loadDoctorAppointments();
            }
            if (this.hasRole('patient')) {
                await this.loadDoctorsForBooking();
                await this.loadPatientAppointments();
            }
            await this.loadProfile();
        },
        syncProfileForm(user) {
            this.profileForm.name = user.name || '';
            this.profileForm.email = user.email || '';
            this.profileForm.phone = user.phone || '';
        },
        async handleAuth() {
            try {
                if (this.isLogin) {
                    const response = await apiCall('/login', 'POST', {
                        username: this.authForm.username,
                        password: this.authForm.password
                    });
                    this.currentUser = response.user;
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
        async logout() {
            try {
                await apiCall('/logout', 'POST');
            } catch (error) {
                await this.logError(error, 'logout');
            }
            this.currentUser = null;
            this.alertMsg = '';
            this.isLogin = true;
            this.authForm = { username: '', password: '', name: '', email: '' };
        },

        async loadStats() {
            try {
                this.stats = await apiCall('/admin/stats', 'GET');
            } catch (error) {
                await this.logError(error, 'loadStats');
            }
        },
        async loadDepartments() {
            try {
                const query = this.departmentSearch ? `?search=${encodeURIComponent(this.departmentSearch)}` : '';
                this.departments = await apiCall('/departments' + query, 'GET');
            } catch (error) {
                await this.logError(error, 'loadDepartments');
            }
        },
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
            } catch (error) {
                await this.logError(error, 'deletePatient');
            }
        },
        async loadAdminAppointments() {
            try {
                this.adminAppointments = await apiCall('/my-appointments', 'GET');
            } catch (error) {
                await this.logError(error, 'loadAdminAppointments');
            }
        },

        async loadDoctorAppointments() {
            try {
                this.doctorAppointments = await apiCall('/doctor/appointments', 'GET');
            } catch (error) {
                await this.logError(error, 'loadDoctorAppointments');
            }
        },
        showCompleteAppointment(appointment) {
            this.selectedAppointment = appointment;
            this.treatmentForm = { diagnosis: '', prescription: '', notes: '' };
        },
        async completeAppointment() {
            try {
                await apiCall(`/appointments/${this.selectedAppointment.id}/complete`, 'POST', this.treatmentForm);
                this.selectedAppointment = null;
                await this.loadDoctorAppointments();
                this.showSuccess('Appointment completed.');
            } catch (error) {
                await this.logError(error, 'completeAppointment');
            }
        },
        downloadMonthlyReport() {
            window.open(`/api/doctor/monthly-report/${this.reportMonth}/${this.reportYear}`, '_blank');
        },

        async loadDoctorsForBooking() {
            try {
                this.availableDoctors = await apiCall('/doctors', 'GET');
            } catch (error) {
                await this.logError(error, 'loadDoctorsForBooking');
            }
        },
        onDoctorChange() {
            this.selectedDoctorProfile = this.selectedDoctor;
            const firstDate = this.selectableDates.length ? this.selectableDates[0].date : '';
            this.bookingForm.date = firstDate;
        },
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
                this.showSuccess(`Appointment booked at ${response.assigned_time}`);
            } catch (error) {
                await this.logError(error, 'bookAppointment');
            }
        },
        async loadPatientAppointments() {
            try {
                this.patientAppointments = await apiCall('/my-appointments', 'GET');
            } catch (error) {
                await this.logError(error, 'loadPatientAppointments');
            }
        },
        async cancelAppointment(appointmentId) {
            if (!confirm('Cancel this appointment?')) {
                return;
            }
            try {
                await apiCall(`/appointments/${appointmentId}/cancel`, 'POST');
                await this.loadPatientAppointments();
            } catch (error) {
                await this.logError(error, 'cancelAppointment');
            }
        },
        async loadPayments() {
            try {
                this.payments = await apiCall('/patient/payments', 'GET');
            } catch (error) {
                await this.logError(error, 'loadPayments');
            }
        },

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