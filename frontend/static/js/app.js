const { createApp, ref, reactive, onMounted, computed, inject } = Vue;

// --- API Helper ---
async function apiCall(url, method = 'GET', body = null) {
    """
    Make an API call to the backend.

    Args:
        url: API endpoint path (without /api prefix)
        method: HTTP method (GET, POST, PUT, DELETE)
        body: Request body object (optional)

    Returns:
        Response data as JSON or throws error
    """
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
        }
    };
    if (body) options.body = JSON.stringify(body);

    try {
        const response = await fetch('/api' + url, options);
        if (response.status === 401) {
            return { error: 'Unauthorized', status: 401 };
        }
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'API Error');
        return data;
    } catch (err) {
        throw err;
    }
}

// --- Admin Dashboard Component ---
const AdminDashboard = {
    template: `
        <div class="container">
            <h3>Admin Dashboard</h3>
            <ul class="nav nav-tabs mb-3">
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'stats'}" @click="tab='stats'" href="#">Stats</a></li>
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'doctors'}" @click="tab='doctors'" href="#">Doctors</a></li>
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'patients'}" @click="tab='patients'" href="#">Patients</a></li>
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'appointments'}" @click="tab='appointments'" href="#">Appointments</a></li>
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'exports'}" @click="tab='exports'" href="#">Export Jobs</a></li>
            </ul>

            <!-- Stats Tab -->
            <div v-if="tab === 'stats'">
                <div class="row">
                    <div class="col-md-4">
                        <div class="card bg-secondary text-white mb-3">
                            <div class="card-body">
                                <h5 class="card-title">Doctors</h5>
                                <p class="card-text display-4">{{ stats.total_doctors }}</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card bg-secondary text-white mb-3">
                            <div class="card-body">
                                <h5 class="card-title">Patients</h5>
                                <p class="card-text display-4">{{ stats.total_patients }}</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card bg-secondary text-white mb-3">
                            <div class="card-body">
                                <h5 class="card-title">Appointments</h5>
                                <p class="card-text display-4">{{ stats.total_appointments }}</p>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-8">
                        <div class="card p-3 shadow-sm mb-3">
                            <h5>Appointment Distribution</h5>
                            <div id="statusPlot"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card bg-success text-white mb-3">
                            <div class="card-body">
                                <h5 class="card-title">Completed</h5>
                                <p class="card-text display-4">{{ stats.completed_appointments }}</p>
                            </div>
                        </div>
                        <div class="card bg-primary text-white mb-3">
                            <div class="card-body">
                                <h5 class="card-title">Booked</h5>
                                <p class="card-text display-4">{{ stats.booked_appointments }}</p>
                            </div>
                        </div>
                        <div class="card bg-danger text-white mb-3">
                            <div class="card-body">
                                <h5 class="card-title">Cancelled</h5>
                                <p class="card-text display-4">{{ stats.cancelled_appointments }}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Doctors Tab -->
            <div v-if="tab === 'doctors'">
                <div class="d-flex justify-content-between mb-3">
                    <button class="btn btn-secondary" @click="showAddDoctor = !showAddDoctor">Add New Doctor</button>
                    <div class="d-flex gap-2">
                        <input v-model="searchDoc" @input="searchDoctors" placeholder="Search Doctor..." class="form-control w-25">
                        <button class="btn btn-outline-primary" @click="loadDoctors">Refresh</button>
                    </div>
                </div>

                <div v-if="showAddDoctor" class="card mb-3 p-3">
                    <h5>Add Doctor</h5>
                    <form @submit.prevent="addDoctor">
                        <div class="row">
                            <div class="col-md-6 mb-2">
                                <input v-model="newDoctor.name" placeholder="Full Name" class="form-control" required>
                            </div>
                            <div class="col-md-6 mb-2">
                                <input v-model="newDoctor.username" placeholder="Username" class="form-control" required>
                            </div>
                            <div class="col-md-6 mb-2">
                                <input type="password" v-model="newDoctor.password" placeholder="Password" class="form-control" required>
                            </div>
                            <div class="col-md-6 mb-2">
                                <input v-model="newDoctor.email" placeholder="Email" class="form-control">
                            </div>
                            <div class="col-md-6 mb-2">
                                <input v-model="newDoctor.phone" placeholder="Phone" class="form-control">
                            </div>
                            <div class="col-md-6 mb-2">
                                <select v-model="newDoctor.department_id" class="form-select" required>
                                    <option value="" disabled>Select Department</option>
                                    <option v-for="dept in departments" :value="dept.id">{{ dept.name }}</option>
                                </select>
                            </div>
                            <div class="col-12">
                                <button type="submit" class="btn btn-success">Save Doctor</button>
                            </div>
                        </div>
                    </form>
                </div>

                <table class="table table-bordered table-striped">
                    <thead>
                        <tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>Dept</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="doc in filteredDoctors" :key="doc.id">
                            <td>{{ doc.id }}</td>
                            <td>{{ doc.name }}</td>
                            <td>{{ doc.email || 'N/A' }}</td>
                            <td>{{ doc.phone || 'N/A' }}</td>
                            <td>{{ doc.department }}</td>
                            <td>
                                <button class="btn btn-danger btn-sm" @click="deleteDoctor(doc.id)">Delete</button>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Patients Tab -->
            <div v-if="tab === 'patients'">
                <div class="d-flex justify-content-between mb-3">
                    <input v-model="searchPatient" @input="searchPatients" placeholder="Search by Name, ID, Email, Phone..." class="form-control w-50">
                    <button class="btn btn-outline-primary" @click="loadPatients">Refresh</button>
                </div>
                <table class="table table-bordered">
                    <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>History</th><th>Action</th></tr></thead>
                    <tbody>
                        <tr v-for="p in filteredPatients" :key="p.id">
                            <td>{{ p.id }}</td>
                            <td>{{ p.name }}</td>
                            <td>{{ p.email || 'N/A' }}</td>
                            <td>{{ p.phone || 'N/A' }}</td>
                            <td>{{ p.medical_history || 'N/A' }}</td>
                            <td>
                                <button class="btn btn-danger btn-sm" @click="deletePatient(p.id)">Delete</button>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <div v-if="patientPagination.pages > 1" class="d-flex justify-content-center">
                    <button class="btn btn-sm btn-outline-secondary me-2" :disabled="patientPagination.page === 1" @click="changePatientPage(-1)">Prev</button>
                    <span>Page {{ patientPagination.page }} of {{ patientPagination.pages }}</span>
                    <button class="btn btn-sm btn-outline-secondary ms-2" :disabled="patientPagination.page >= patientPagination.pages" @click="changePatientPage(1)">Next</button>
                </div>
            </div>

            <!-- Appointments Tab -->
            <div v-if="tab === 'appointments'">
                <table class="table table-bordered">
                    <thead><tr><th>ID</th><th>Pt. Name</th><th>Dr. Name</th><th>Date</th><th>Status</th></tr></thead>
                    <tbody>
                        <tr v-for="appt in appointments" :key="appt.id">
                            <td>{{ appt.id }}</td>
                            <td>{{ appt.patient_name }}</td>
                            <td>{{ appt.doctor_name }}</td>
                            <td>{{ appt.date }} {{ appt.time }}</td>
                            <td>
                                <span :class="statusBadgeClass(appt.status)">{{ appt.status }}</span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Export Jobs Tab -->
            <div v-if="tab === 'exports'">
                <h5>Export Job Monitor</h5>
                <table class="table table-bordered">
                    <thead>
                        <tr><th>Job ID</th><th>Patient</th><th>Status</th><th>Created</th><th>Completed</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="job in exportJobs" :key="job.id">
                            <td>{{ job.id }}</td>
                            <td>{{ job.patient_name }}</td>
                            <td><span :class="exportStatusClass(job.status)">{{ job.status }}</span></td>
                            <td>{{ formatDate(job.created_at) }}</td>
                            <td>{{ job.completed_at ? formatDate(job.completed_at) : '-' }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `,
    setup() {
        const tab = ref('stats');
        const stats = ref({});
        const doctors = ref([]);
        const patients = ref([]);
        const departments = ref([]);
        const appointments = ref([]);
        const exportJobs = ref([]);

        const showAddDoctor = ref(false);
        const newDoctor = reactive({ name: '', username: '', password: '', email: '', phone: '', department_id: '' });

        const searchDoc = ref('');
        const searchPatient = ref('');
        const patientPagination = reactive({ page: 1, pages: 1, per_page: 50 });

        // Load dashboard data
        async function loadData() {
            try {
                stats.value = await apiCall('/admin/stats');
                await loadDoctors();
                departments.value = await apiCall('/departments');
                appointments.value = await apiCall('/my-appointments');
                
                // Wait for next tick to ensure DOM is updated
                setTimeout(() => renderPlot(), 100);
            } catch (e) {
                console.error('Failed to load admin data:', e);
            }
        }

        function renderPlot() {
            if (!stats.value || !document.getElementById('statusPlot')) return;

            const data = [{
                x: ['Booked', 'Completed', 'Cancelled'],
                y: [
                    stats.value.booked_appointments,
                    stats.value.completed_appointments,
                    stats.value.cancelled_appointments
                ],
                type: 'bar',
                marker: {
                    color: ['#0d6efd', '#198754', '#dc3545'] // Blue, Green, Red (Bootstrap colors)
                }
            }];

            const layout = {
                height: 300,
                margin: { t: 20, b: 40, l: 40, r: 20 },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { family: 'Arial, sans-serif' }
            };

            Plotly.newPlot('statusPlot', data, layout, {responsive: true, displayModeBar: false});
        }

        async function loadDoctors() {
            try {
                doctors.value = await apiCall('/admin/doctors');
            } catch (e) {
                console.error('Failed to load doctors:', e);
            }
        }

        async function searchDoctors() {
            try {
                if (searchDoc.value) {
                    doctors.value = await apiCall(`/admin/doctors?search=${encodeURIComponent(searchDoc.value)}`);
                } else {
                    await loadDoctors();
                }
            } catch (e) {
                console.error('Search failed:', e);
            }
        }

        async function loadPatients() {
            try {
                const response = await apiCall(`/admin/patients?page=${patientPagination.page}&per_page=${patientPagination.per_page}`);
                patients.value = response.patients;
                patientPagination.pages = response.pages;
            } catch (e) {
                console.error('Failed to load patients:', e);
            }
        }

        async function searchPatients() {
            try {
                if (searchPatient.value) {
                    const response = await apiCall(`/admin/patients?search=${encodeURIComponent(searchPatient.value)}`);
                    patients.value = response.patients;
                    patientPagination.pages = response.pages;
                } else {
                    await loadPatients();
                }
            } catch (e) {
                console.error('Patient search failed:', e);
            }
        }

        async function loadExportJobs() {
            try {
                const response = await apiCall('/admin/export-jobs');
                exportJobs.value = response.jobs;
            } catch (e) {
                console.error('Failed to load export jobs:', e);
            }
        }

        async function addDoctor() {
            try {
                await apiCall('/admin/doctors', 'POST', newDoctor);
                alert('Doctor added!');
                showAddDoctor.value = false;
                await loadDoctors();
            } catch (e) {
                alert(e.message);
            }
        }

        async function deleteDoctor(id) {
            if(confirm('Are you sure?')) {
                try {
                    await apiCall('/admin/doctors/' + id, 'DELETE');
                    await loadDoctors();
                } catch (e) {
                    alert(e.message);
                }
            }
        }

        async function deletePatient(id) {
            if(confirm('Are you sure?')) {
                try {
                    await apiCall('/admin/patients/' + id, 'DELETE');
                    await loadPatients();
                } catch (e) {
                    alert(e.message);
                }
            }
        }

        function changePatientPage(direction) {
            patientPagination.page += direction;
            loadPatients();
        }

        const filteredDoctors = computed(() => {
            return doctors.value;
        });

        const filteredPatients = computed(() => {
            return patients.value;
        });

        function statusBadgeClass(status) {
            return {
                'badge bg-success': status === 'Completed',
                'badge bg-primary': status === 'Booked',
                'badge bg-danger': status === 'Cancelled'
            };
        }

        function exportStatusClass(status) {
            return {
                'badge bg-success': status === 'completed',
                'badge bg-warning': status === 'pending',
                'badge bg-info': status === 'processing',
                'badge bg-danger': status === 'failed'
            };
        }

        function formatDate(dateStr) {
            if (!dateStr) return '-';
            return new Date(dateStr).toLocaleString();
        }

        // Watch for tab changes
        onMounted(() => {
            loadData();
            loadPatients();
        });

        return {
            tab, stats, doctors, patients, departments, appointments, exportJobs,
            showAddDoctor, newDoctor, addDoctor, deleteDoctor, deletePatient,
            searchDoc, searchPatient, filteredDoctors, filteredPatients,
            statusBadgeClass, exportStatusClass, formatDate,
            patientPagination, changePatientPage, searchDoctors, searchPatients, loadDoctors, loadPatients
        };
    }
};

// --- Doctor Dashboard Component ---
const DoctorDashboard = {
    props: ['user'],
    template: `
        <div class="container">
            <h3>Doctor Dashboard</h3>
            <div class="card p-3 mb-3">
                 <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="availabilitySwitch" disabled checked>
                    <label class="form-check-label" for="availabilitySwitch">Available: {{ user.doctor_profile?.availability || 'Mon-Fri 9AM-5PM' }}</label>
                 </div>
                 <small class="text-muted">Contact Admin to change availability schedule.</small>
            </div>

            <!-- Patient Summary Modal -->
            <div v-if="selectedPatient" class="card mb-3 p-3 bg-light">
                <div class="d-flex justify-content-between">
                    <h5>Patient Summary</h5>
                    <button class="btn btn-sm btn-outline-secondary" @click="selectedPatient = null">Close</button>
                </div>
                <div v-if="patientSummary">
                    <p><strong>Name:</strong> {{ patientSummary.patient.name }}</p>
                    <p><strong>Email:</strong> {{ patientSummary.patient.email }}</p>
                    <p><strong>Phone:</strong> {{ patientSummary.patient.phone }}</p>
                    <p><strong>Total Visits:</strong> {{ patientSummary.total_visits }}</p>
                    <p><strong>Medical History:</strong> {{ patientSummary.medical_history_summary || 'None recorded' }}</p>
                    <h6>Recent Appointments</h6>
                    <ul>
                        <li v-for="a in patientSummary.recent_appointments" :key="a.id">
                            {{ a.date }} - {{ a.doctor_name }} ({{ a.status }})
                        </li>
                    </ul>
                    <button class="btn btn-primary" @click="viewFullHistory(selectedPatient)">View Full History</button>
                </div>
            </div>

            <!-- Full History Modal -->
            <div v-if="showFullHistory" class="card mb-3 p-3 bg-light">
                <div class="d-flex justify-content-between">
                    <h5>Full Treatment History</h5>
                    <button class="btn btn-sm btn-outline-secondary" @click="showFullHistory = false">Close</button>
                </div>
                <div v-if="patientHistory">
                    <p><strong>Patient:</strong> {{ patientHistory.patient.name }}</p>
                    <p><strong>Total Appointments:</strong> {{ patientHistory.total_appointments }}</p>
                    <table class="table table-bordered table-sm">
                        <thead>
                            <tr><th>Date</th><th>Doctor</th><th>Diagnosis</th><th>Treatment</th></tr>
                        </thead>
                        <tbody>
                            <tr v-for="record in patientHistory.appointments" :key="record.appointment_id">
                                <td>{{ record.date }} {{ record.time }}</td>
                                <td>{{ record.doctor.name }}</td>
                                <td>{{ record.treatment?.diagnosis || 'N/A' }}</td>
                                <td>{{ record.treatment?.prescription || 'N/A' }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div v-if="!selectedAppointment">
                <div class="row mb-4">
                    <div class="col-md-12">
                        <div class="card p-3 shadow-sm">
                            <h5>My Appointment Statistics</h5>
                            <div id="doctorStatsPlot"></div>
                        </div>
                    </div>
                </div>
                <h5>My Appointments</h5>
                <table class="table table-striped">
                    <thead><tr><th>Date/Time</th><th>Patient</th><th>Status</th><th>Medical History</th><th>Action</th></tr></thead>
                    <tbody>
                        <tr v-for="appt in appointments" :key="appt.id">
                            <td>{{ appt.date }} {{ appt.time }}</td>
                            <td>{{ appt.patient_name }}</td>
                            <td>
                                <span :class="{'text-success': appt.status==='Completed', 'text-danger': appt.status==='Cancelled'}">
                                    {{ appt.status }}
                                </span>
                            </td>
                            <td>
                                <button class="btn btn-info btn-sm" @click="viewPatientSummary(appt.patient_id)">View History</button>
                            </td>
                            <td>
                                <button v-if="appt.status === 'Booked'" class="btn btn-primary btn-sm me-2" @click="openComplete(appt)">Complete</button>
                                <button v-if="appt.status === 'Booked'" class="btn btn-danger btn-sm" @click="cancelAppt(appt.id)">Cancel</button>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Complete Appointment Form -->
            <div v-else class="card p-3">
                <h5>Information about Patient: {{ selectedAppointment.patient_name }}</h5>
                <p class="text-muted">Medical History: {{ selectedAppointment.patient_medical_history || 'None recorded' }}</p>
                <form @submit.prevent="completeAppt">
                    <div class="mb-3">
                        <label>Diagnosis</label>
                        <textarea v-model="treatment.diagnosis" class="form-control" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label>Prescription</label>
                        <textarea v-model="treatment.prescription" class="form-control" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label>Notes</label>
                        <textarea v-model="treatment.notes" class="form-control"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Save & Complete</button>
                    <button type="button" class="btn btn-secondary ms-2" @click="selectedAppointment = null">Cancel</button>
                </form>
            </div>
        </div>
    `,
    setup() {
        const appointments = ref([]);
        const selectedAppointment = ref(null);
        const selectedPatient = ref(null);
        const patientSummary = ref(null);
        const patientHistory = ref(null);
        const showFullHistory = ref(false);
        const treatment = reactive({ diagnosis: '', prescription: '', notes: '' });

        async function load() {
            appointments.value = await apiCall('/doctor/appointments');
            setTimeout(() => renderDoctorPlot(), 100);
        }

        function renderDoctorPlot() {
            if (!appointments.value.length || !document.getElementById('doctorStatsPlot')) return;

            const counts = { 'Booked': 0, 'Completed': 0, 'Cancelled': 0 };
            appointments.value.forEach(a => {
                counts[a.status] = (counts[a.status] || 0) + 1;
            });

            const data = [{
                values: Object.values(counts),
                labels: Object.keys(counts),
                type: 'pie',
                marker: {
                    colors: ['#0d6efd', '#198754', '#dc3545']
                },
                hole: 0.4
            }];

            const layout = {
                height: 300,
                margin: { t: 20, b: 20, l: 20, r: 20 },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)'
            };

            Plotly.newPlot('doctorStatsPlot', data, layout, {responsive: true, displayModeBar: false});
        }

        async function viewPatientSummary(patientId) {
            selectedPatient.value = patientId;
            patientSummary.value = await apiCall(`/doctor/patients/${patientId}/summary`);
        }

        async function viewFullHistory(patientId) {
            patientHistory.value = await apiCall(`/doctor/patients/${patientId}/history`);
            showFullHistory.value = true;
        }

        function openComplete(appt) {
            selectedAppointment.value = appt;
            treatment.diagnosis = '';
            treatment.prescription = '';
            treatment.notes = '';
        }

        async function completeAppt() {
            try {
                await apiCall('/appointments/' + selectedAppointment.value.id + '/complete', 'POST', treatment);
                alert('Saved!');
                selectedAppointment.value = null;
                load();
            } catch (e) { alert(e.message); }
        }

        async function cancelAppt(id) {
            if(confirm('Cancel this appointment?')) {
                await apiCall('/appointments/' + id + '/cancel', 'POST');
                load();
            }
        }

        onMounted(load);
        return { appointments, selectedAppointment, selectedPatient, patientSummary, patientHistory, showFullHistory, treatment, openComplete, completeAppt, cancelAppt, viewPatientSummary, viewFullHistory };
    }
};

// --- Patient Dashboard Component ---
const PatientDashboard = {
    props: ['user'],
    template: `
        <div class="container">
            <h3>Patient Dashboard</h3>
            <ul class="nav nav-tabs mb-3">
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'book'}" @click="tab='book'" href="#">Book Appointment</a></li>
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'history'}" @click="tab='history'" href="#">My History</a></li>
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'exports'}" @click="tab='exports'" href="#">My Exports</a></li>
                <li class="nav-item"><a class="nav-link" :class="{active: tab === 'profile'}" @click="tab='profile'" href="#">Profile</a></li>
            </ul>

            <!-- Book Tab -->
            <div v-if="tab === 'book'">
                <div class="row mb-3">
                    <div class="col-md-6">
                        <select v-model="selectedDept" class="form-select" @change="loadDoctors">
                            <option value="">All Departments</option>
                            <option v-for="dept in departments" :value="dept.id">{{ dept.name }}</option>
                        </select>
                    </div>
                    <div class="col-md-6">
                        <input v-model="searchDoctor" @input="searchDoctors" class="form-control" placeholder="Search doctors by name or specialization...">
                    </div>
                </div>
                <div class="row">
                    <div class="col-md-4 mb-3" v-for="doc in doctors" :key="doc.id">
                        <div class="card h-100">
                            <div class="card-body">
                                <h5 class="card-title">{{ doc.name }}</h5>
                                <h6 class="card-subtitle mb-2 text-muted">{{ doc.department }}</h6>
                                <p class="card-text small">{{ doc.availability }}</p>
                                <p class="card-text small" v-if="doc.email">Email: {{ doc.email }}</p>
                                <p class="card-text small" v-if="doc.phone">Phone: {{ doc.phone }}</p>
                                <button class="btn btn-outline-primary btn-sm" @click="promptBook(doc)">Book Now</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Booking Modal -->
                <div v-if="bookingDoc" class="card mt-3 border-primary p-3">
                    <h5>Book with {{ bookingDoc.name }}</h5>
                    <form @submit.prevent="confirmBook">
                        <div class="row">
                            <div class="col-md-5">
                                <label>Date</label>
                                <input type="date" v-model="bookForm.date" class="form-control" required>
                            </div>
                            <div class="col-md-5">
                                <label>Time</label>
                                <input type="time" v-model="bookForm.time" class="form-control" required>
                            </div>
                            <div class="col-md-2 d-flex align-items-end">
                                <button type="submit" class="btn btn-primary w-100">Confirm</button>
                            </div>
                        </div>
                        <button type="button" class="btn btn-link text-danger mt-2" @click="bookingDoc = null">Cancel</button>
                    </form>
                </div>
            </div>

            <!-- History Tab -->
            <div v-if="tab === 'history'">
                <div class="card p-3 mb-4 shadow-sm">
                    <h5>Visit History Analytics</h5>
                    <div id="visitPlot"></div>
                </div>
                <div v-for="appt in appointments" :key="appt.id" class="card mb-3">
                    <div class="card-header d-flex justify-content-between">
                        <span>{{ appt.date }} {{ appt.time }} - {{ appt.doctor_name }} ({{ appt.department }})</span>
                        <span class="badge" :class="statusClass(appt.status)">{{ appt.status }}</span>
                    </div>
                    <div class="card-body" v-if="appt.treatment">
                        <h6><strong>Diagnosis:</strong> {{ appt.treatment.diagnosis }}</h6>
                        <p><strong>Prescription:</strong> {{ appt.treatment.prescription }}</p>
                        <p class="small text-muted">Notes: {{ appt.treatment.notes }}</p>
                    </div>
                    <div class="card-body" v-else>
                        <p class="text-muted">No details yet or appointment pending.</p>
                        <button v-if="appt.status === 'Booked'" class="btn btn-danger btn-sm" @click="cancelAppt(appt.id)">Cancel Appointment</button>
                    </div>
                </div>
            </div>

            <!-- Exports Tab -->
            <div v-if="tab === 'exports'">
                <div class="d-flex justify-content-between mb-3">
                    <h5>My Treatment Exports</h5>
                    <button class="btn btn-primary" @click="triggerExport" :disabled="exportLoading">
                        {{ exportLoading ? 'Exporting...' : 'Export Treatment History' }}
                    </button>
                </div>
                <div v-if="exportMessage" class="alert" :class="exportMessageType" role="alert">
                    {{ exportMessage }}
                </div>
                <table class="table table-bordered">
                    <thead>
                        <tr><th>Job ID</th><th>Status</th><th>Created</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="job in exportJobs" :key="job.id">
                            <td>{{ job.id }}</td>
                            <td><span :class="exportStatusClass(job.status)">{{ job.status }}</span></td>
                            <td>{{ formatDate(job.created_at) }}</td>
                            <td>
                                <button v-if="job.status === 'completed'" class="btn btn-success btn-sm" @click="downloadExport(job.id)">Download</button>
                                <span v-else-if="job.status === 'pending'">Processing...</span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Profile Tab -->
            <div v-if="tab === 'profile'">
                <div class="card p-3">
                    <form @submit.prevent="updateProfile">
                        <div class="mb-3">
                            <label>Name</label>
                            <input v-model="profile.name" class="form-control">
                        </div>
                        <div class="mb-3">
                            <label>Email</label>
                            <input v-model="profile.email" class="form-control" type="email">
                        </div>
                        <div class="mb-3">
                            <label>Phone</label>
                            <input v-model="profile.phone" class="form-control" type="tel">
                        </div>
                        <div class="mb-3">
                            <label>Notification Preference</label>
                            <select v-model="profile.notification_pref" class="form-select">
                                <option value="email">Email</option>
                                <option value="sms">SMS</option>
                                <option value="chat">Google Chat</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label>Medical History Summary</label>
                            <textarea v-model="profile.history" class="form-control"></textarea>
                        </div>
                        <button class="btn btn-secondary">Update Profile</button>
                    </form>
                </div>
            </div>
        </div>
    `,
    setup(props) {
        const tab = ref('book');
        const departments = ref([]);
        const doctors = ref([]);
        const appointments = ref([]);
        const selectedDept = ref('');
        const searchDoctor = ref('');
        const bookingDoc = ref(null);
        const bookForm = reactive({ date: '', time: '' });
        const profile = reactive({ name: '', email: '', phone: '', history: '', notification_pref: 'email' });

        // Export related
        const exportJobs = ref([]);
        const exportLoading = ref(false);
        const exportMessage = ref('');
        const exportMessageType = ref('alert-info');

        async function loadInit() {
            departments.value = await apiCall('/departments');
            loadDoctors();
            loadHistory();
            loadExportJobs();
            if (props.user) {
                profile.name = props.user.name;
                profile.email = props.user.email;
                profile.phone = props.user.phone;
            }
        }

        async function updateProfile() {
            try {
                await apiCall('/profile', 'POST', profile);
                alert('Profile updated');
            } catch(e) { alert(e.message); }
        }

        async function loadDoctors() {
            let url = '/doctors';
            if (selectedDept.value) url += '?department_id=' + selectedDept.value;
            if (searchDoctor.value) url += (selectedDept.value ? '&' : '?') + 'search=' + encodeURIComponent(searchDoctor.value);
            doctors.value = await apiCall(url);
        }

        async function searchDoctors() {
            await loadDoctors();
        }

        async function loadHistory() {
            appointments.value = await apiCall('/my-appointments');
            setTimeout(() => renderVisitPlot(), 100);
        }

        function renderVisitPlot() {
            if (!appointments.value.length || !document.getElementById('visitPlot')) return;

            // Group appointments by month
            const monthCounts = {};
            appointments.value.forEach(a => {
                const month = a.date.substring(0, 7); // YYYY-MM
                monthCounts[month] = (monthCounts[month] || 0) + 1;
            });

            const months = Object.keys(monthCounts).sort();
            const counts = months.map(m => monthCounts[m]);

            const data = [{
                x: months,
                y: counts,
                type: 'scatter',
                mode: 'lines+markers',
                line: { color: '#6c757d', width: 3 },
                marker: { size: 8, color: '#343a40' }
            }];

            const layout = {
                height: 300,
                margin: { t: 20, b: 40, l: 40, r: 20 },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                xaxis: { title: 'Month', tickformat: '%b %Y' },
                yaxis: { title: 'Visits', dtick: 1 }
            };

            Plotly.newPlot('visitPlot', data, layout, {responsive: true, displayModeBar: false});
        }

        async function loadExportJobs() {
            exportJobs.value = await apiCall('/export/jobs');
        }

        async function triggerExport() {
            exportLoading.value = true;
            exportMessage.value = '';
            try {
                const response = await apiCall('/export/treatments', 'POST');
                exportMessage.value = 'Export job created! You will receive an email when ready.';
                exportMessageType.value = 'alert-success';
                loadExportJobs();
            } catch (e) {
                exportMessage.value = 'Error: ' + e.message;
                exportMessageType.value = 'alert-danger';
            }
            exportLoading.value = false;
        }

        async function downloadExport(jobId) {
            try {
                window.open('/api/export/download/' + jobId, '_blank');
            } catch (e) {
                alert('Download failed: ' + e.message);
            }
        }

        function promptBook(doc) {
            bookingDoc.value = doc;
            bookForm.date = '';
            bookForm.time = '';
        }

        async function confirmBook() {
            try {
                await apiCall('/appointments', 'POST', {
                    doctor_id: bookingDoc.value.id,
                    date: bookForm.date,
                    time: bookForm.time
                });
                alert('Booked!');
                bookingDoc.value = null;
                tab.value = 'history';
                loadHistory();
            } catch (e) {
                alert('Booking failed: ' + e.message);
            }
        }

        async function cancelAppt(id) {
            if(confirm('Cancel appointment?')) {
                await apiCall('/appointments/' + id + '/cancel', 'POST');
                loadHistory();
            }
        }

        function statusClass(status) {
            return {
                'bg-success': status === 'Completed',
                'bg-primary': status === 'Booked',
                'bg-danger': status === 'Cancelled'
            };
        }

        function exportStatusClass(status) {
            return {
                'badge bg-success': status === 'completed',
                'badge bg-warning': status === 'pending',
                'badge bg-info': status === 'processing',
                'badge bg-danger': status === 'failed'
            };
        }

        function formatDate(dateStr) {
            if (!dateStr) return '-';
            return new Date(dateStr).toLocaleString();
        }

        onMounted(loadInit);
        return {
            tab, departments, doctors, appointments, selectedDept, searchDoctor,
            bookingDoc, bookForm, profile, loadDoctors, searchDoctors, promptBook, confirmBook, cancelAppt, updateProfile,
            exportJobs, exportLoading, exportMessage, exportMessageType, triggerExport, downloadExport, statusClass, exportStatusClass, formatDate
        };
    }
};

// --- Main App ---
const MainApp = {
    setup() {
        const user = ref(null);
        const authMode = ref('login'); // login or register
        const authForm = reactive({ username: '', password: '', name: '', email: '', phone: '' });
        const message = ref('');
        const messageType = ref('success');

        async function checkUser() {
            try {
                const data = await apiCall('/current-user');
                if (data) user.value = data;
            } catch (e) {
                // Not logged in
            }
        }

        async function authSubmit() {
            message.value = '';
            try {
                if (authMode.value === 'login') {
                    const res = await apiCall('/login', 'POST', {
                        username: authForm.username,
                        password: authForm.password
                    });
                    user.value = res.user;
                } else {
                    await apiCall('/register', 'POST', authForm);
                    message.value = 'Registration successful! Please login.';
                    messageType.value = 'success';
                    authMode.value = 'login';
                    authForm.password = ''; // Clear password
                }
            } catch (e) {
                message.value = e.message;
                messageType.value = 'error';
            }
        }

        async function logout() {
            await apiCall('/logout', 'POST');
            user.value = null;
            authForm.username = '';
            authForm.password = '';
        }

        function hasRole(role) {
            return user.value && user.value.roles && user.value.roles.includes(role);
        }

        function getRoleDisplay(roles) {
            if (!roles || !roles.length) return '';
            const role = roles[0];
            return role.charAt(0).toUpperCase() + role.slice(1);
        }

        onMounted(checkUser);

        return { user, authMode, authForm, message, messageType, authSubmit, logout, hasRole, getRoleDisplay };
    }
};

const app = createApp(MainApp);
app.component('admin-dashboard', AdminDashboard);
app.component('doctor-dashboard', DoctorDashboard);
app.component('patient-dashboard', PatientDashboard);
app.mount('#app');
