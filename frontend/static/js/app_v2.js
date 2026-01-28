const { createApp, ref, reactive, onMounted, computed, inject } = Vue;

// --- API Helper ---
async function apiCall(url, method = 'GET', body = null) {
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
            </div>

            <!-- Doctors Tab -->
            <div v-if="tab === 'doctors'">
                <div class="d-flex justify-content-between mb-3">
                    <button class="btn btn-secondary" @click="showAddDoctor = !showAddDoctor">Add New Doctor</button>
                    <input v-model="searchDoc" placeholder="Search Doctor..." class="form-control w-25">
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
                        <tr><th>ID</th><th>Name</th><th>Dept</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="doc in filteredDoctors" :key="doc.id">
                            <td>{{ doc.id }}</td>
                            <td>{{ doc.name }}</td>
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
                <input v-model="searchPatient" placeholder="Search Patient..." class="form-control mb-3 w-50">
                <table class="table table-bordered">
                     <thead><tr><th>ID</th><th>Name</th><th>History (Summary)</th><th>Action</th></tr></thead>
                     <tbody>
                        <tr v-for="p in filteredPatients" :key="p.id">
                            <td>{{ p.id }}</td>
                            <td>{{ p.name }}</td>
                            <td>{{ p.medical_history || 'N/A' }}</td>
                            <td>
                                <button class="btn btn-danger btn-sm" @click="deletePatient(p.id)">Delete</button>
                            </td>
                        </tr>
                     </tbody>
                </table>
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
                            <td>{{ appt.status }}</td>
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
        
        const showAddDoctor = ref(false);
        const newDoctor = reactive({ name: '', username: '', password: '', department_id: '' });
        
        const searchDoc = ref('');
        const searchPatient = ref('');

        async function loadData() {
            stats.value = await apiCall('/admin/stats');
            doctors.value = await apiCall('/admin/doctors');
            departments.value = await apiCall('/departments');
            appointments.value = await apiCall('/my-appointments');
            
            try {
                patients.value = await apiCall('/admin/patients');
            } catch (e) { patients.value = []; }
        }

        async function addDoctor() {
            try {
                await apiCall('/admin/doctors', 'POST', newDoctor);
                alert('Doctor added!');
                showAddDoctor.value = false;
                loadData();
            } catch (e) { alert(e.message); }
        }

        async function deleteDoctor(id) {
            if(confirm('Are you sure?')) {
                await apiCall('/admin/doctors/' + id, 'DELETE');
                loadData();
            }
        }

        async function deletePatient(id) {
             if(confirm('Are you sure?')) {
                await apiCall('/admin/patients/' + id, 'DELETE');
                loadData();
            }
        }

        const filteredDoctors = computed(() => {
            if (!searchDoc.value) return doctors.value;
            const q = searchDoc.value.toLowerCase();
            return doctors.value.filter(d => d.name.toLowerCase().includes(q) || d.department.toLowerCase().includes(q));
        });

        const filteredPatients = computed(() => {
             if (!searchPatient.value) return patients.value;
             const q = searchPatient.value.toLowerCase();
             return patients.value.filter(p => p.name.toLowerCase().includes(q));
        });

        onMounted(loadData);
        return { 
            tab, stats, doctors, patients, departments, appointments, 
            showAddDoctor, newDoctor, addDoctor, deleteDoctor, deletePatient,
            searchDoc, searchPatient, filteredDoctors, filteredPatients 
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
            
            <div v-if="!selectedAppointment">
                <h5>My Appointments</h5>
                <table class="table table-striped">
                    <thead><tr><th>Date/Time</th><th>Patient</th><th>Status</th><th>Action</th></tr></thead>
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
        const treatment = reactive({ diagnosis: '', prescription: '', notes: '' });

        async function load() {
            appointments.value = await apiCall('/doctor/appointments');
        }

        function openComplete(appt) {
            selectedAppointment.value = appt;
            treatment.diagnosis = ''; treatment.prescription = ''; treatment.notes = '';
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
        return { appointments, selectedAppointment, treatment, openComplete, completeAppt, cancelAppt };
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
                </div>
                <div class="row">
                    <div class="col-md-4 mb-3" v-for="doc in doctors" :key="doc.id">
                        <div class="card h-100">
                            <div class="card-body">
                                <h5 class="card-title">{{ doc.name }}</h5>
                                <h6 class="card-subtitle mb-2 text-muted">{{ doc.department }}</h6>
                                <p class="card-text small">{{ doc.availability }}</p>
                                <button class="btn btn-outline-primary btn-sm" @click="promptBook(doc)">Book Now</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Booking Modal (Simple Div) -->
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
                <div v-for="appt in appointments" :key="appt.id" class="card mb-3">
                    <div class="card-header d-flex justify-content-between">
                        <span>{{ appt.date }} {{ appt.time }} - {{ appt.doctor_name }} ({{ appt.department }})</span>
                        <span class="badge bg-secondary">{{ appt.status }}</span>
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
            
            <!-- Profile Tab -->
            <div v-if="tab === 'profile'">
                <div class="card p-3">
                    <form @submit.prevent="updateProfile">
                        <div class="mb-3">
                             <label>Name</label>
                             <input v-model="profile.name" class="form-control">
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
        const bookingDoc = ref(null);
        const bookForm = reactive({ date: '', time: '' });
        
        const profile = reactive({ name: '', history: '' });

        async function loadInit() {
            departments.value = await apiCall('/departments');
            loadDoctors();
            loadHistory();
            if (props.user) {
                profile.name = props.user.name;
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
            doctors.value = await apiCall(url);
        }

        async function loadHistory() {
            appointments.value = await apiCall('/my-appointments');
        }

        function promptBook(doc) {
            bookingDoc.value = doc;
            bookForm.date = ''; bookForm.time = '';
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
            } catch (e) { alert(e.message); }
        }

        async function cancelAppt(id) {
            if(confirm('Cancel appointment?')) {
                await apiCall('/appointments/' + id + '/cancel', 'POST');
                loadHistory();
            }
        }
        
        onMounted(loadInit);
        return { tab, departments, doctors, appointments, selectedDept, bookingDoc, bookForm, profile, loadDoctors, promptBook, confirmBook, cancelAppt, updateProfile };
    }
};

// --- Main App ---
const MainApp = {
    setup() {
        const user = ref(null);
        const authMode = ref('login'); // login or register
        const authForm = reactive({ username: '', password: '', name: '' });
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
            authForm.username = ''; authForm.password = '';
        }

        onMounted(checkUser);

        return { user, authMode, authForm, message, messageType, authSubmit, logout };
    }
};

const app = createApp(MainApp);
app.component('admin-dashboard', AdminDashboard);
app.component('doctor-dashboard', DoctorDashboard);
app.component('patient-dashboard', PatientDashboard);
app.mount('#app');
