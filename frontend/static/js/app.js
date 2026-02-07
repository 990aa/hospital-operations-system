const { createApp, ref, reactive, onMounted, computed, defineAsyncComponent } = Vue;

const apiCall = async (url, method = 'GET', body = null) => {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);
    try {
        const response = await fetch('/api' + url, options);
        if (response.status === 401) return { error: 'Unauthorized', status: 401 };
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'API Error');
        return data;
    } catch (err) {
        throw err;
    }
};

const loadComponent = (path, setupFn) => {
    return defineAsyncComponent(() =>
        fetch(path)
            .then(res => {
                if (!res.ok) throw new Error("Failed to load template: " + path);
                return res.text();
            })
            .then(template => ({
                template: template,
                props: ['user'], 
                setup: setupFn
            }))
            .catch(err => {
                console.error(err);
                return { template: '<div>Error loading component</div>' };
            })
    );
};

// --- Admin Setup ---
const adminSetup = () => {
    const tab = ref('stats');
    const stats = ref({ total_doctors: 0, total_patients: 0, total_appointments: 0 });
    const doctors = ref([]);
    const patients = ref([]); 
    const appointments = ref([]);
    const departments = ref([]);
    
    // UI States
    const showAddDoctor = ref(false);
    const searchDoc = ref('');
    const searchPatient = ref('');
    const newDoctor = reactive({ name: '', username: '', password: '', department_id: '' });

    async function loadData() {
        try {
            stats.value = await apiCall('/admin/stats');
            doctors.value = await apiCall('/admin/doctors');
            try { patients.value = await apiCall('/admin/patients'); } catch(e) { patients.value = []; }
            departments.value = await apiCall('/departments');
            appointments.value = await apiCall('/my-appointments'); 
        } catch (e) { console.error(e); }
    }

    const filteredDoctors = computed(() => {
        if (!searchDoc.value) return doctors.value;
        return doctors.value.filter(d => d.name.toLowerCase().includes(searchDoc.value.toLowerCase()));
    });
    
    const filteredPatients = computed(() => {
        if (!searchPatient.value) return patients.value;
        return patients.value.filter(p => p.name.toLowerCase().includes(searchPatient.value.toLowerCase()));
    });

    async function addDoctor() {
        try {
            await apiCall('/admin/doctors', 'POST', newDoctor);
            alert('Doctor added!');
            showAddDoctor.value = false;
            Object.assign(newDoctor, { name: '', username: '', password: '', department_id: '' });
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
         if(confirm('Delete Patient? This cannot be undone.')) {
            try {
                await apiCall('/admin/patients/' + id, 'DELETE');
                loadData();
            } catch (e) { alert(e.message); }
        }
    }

    onMounted(loadData);

    return { 
        tab, stats, doctors, appointments, departments, patients,
        searchDoc, searchPatient, showAddDoctor, newDoctor,
        filteredDoctors, filteredPatients,
        addDoctor, deleteDoctor, deletePatient
    };
};

// --- Doctor Setup ---
const doctorSetup = (props) => {
    const tab = ref('appointments');
    const appointments = ref([]);
    const patients = ref([]); 
    const activeAppt = ref(null); 

    async function load() {
        try {
            appointments.value = await apiCall('/doctor/appointments');
            // Mock or real call for patients
            // patients.value = await apiCall('/doctor/patients'); 
        } catch(e) { console.error(e); }
    }

    function statusBadge(status) {
        if (status === 'Completed') return 'bg-success';
        if (status === 'Cancelled') return 'bg-danger';
        return 'bg-warning text-dark';
    }

    function completeAppointment(appt) {
        activeAppt.value = { ...appt, newNotes: '' };
    }

    async function submitCompletion() {
        if (!activeAppt.value) return;
        try {
            await apiCall('/appointments/' + activeAppt.value.id + '/complete', 'POST', {
                notes: activeAppt.value.newNotes,
                diagnosis: 'See notes', 
                prescription: 'See notes'
            });
            alert('Appointment Completed');
            activeAppt.value = null;
            load();
        } catch (e) { alert(e.message); }
    }

    onMounted(load);
    return { tab, appointments, patients, activeAppt, completeAppointment, submitCompletion, statusBadge, user: props.user };
};

// --- Patient Setup ---
const patientSetup = (props) => {
    // Note: Patient HTML uses side-by-side layout, no tabs needed mostly.
    const appointments = ref([]);
    const departments = ref([]);
    const availableDoctors = ref([]);
    
    // The HTML uses 'booking' object for v-models
    const booking = reactive({
        department_id: '',
        doctor_id: '',
        date: '',
        time: '',
        reason: ''
    });

    const today = new Date().toISOString().split('T')[0];

    async function load() {
        departments.value = await apiCall('/departments');
        appointments.value = await apiCall('/my-appointments'); 
    }

    async function fetchDoctors() {
        if (!booking.department_id) return;
        availableDoctors.value = await apiCall('/doctors?department_id=' + booking.department_id);
    }

    async function bookAppointment() {
        try {
            await apiCall('/appointments', 'POST', { ...booking });
            alert('Booked Successfully!');
            // Reset form
            Object.assign(booking, { department_id: '', doctor_id: '', date: '', time: '', reason: '' });
            availableDoctors.value = [];
            load();
        } catch (e) { alert(e.message); }
    }
    
    function statusBadge(status) {
        if (status === 'Completed') return 'bg-success';
        if (status === 'Cancelled') return 'bg-danger';
        return 'bg-primary';
    }

    onMounted(load);
    return { appointments, departments, availableDoctors, booking, today, fetchDoctors, bookAppointment, statusBadge };
};

// --- Login/Register Setup ---
const loginSetup = (props, { emit }) => {
    const isLogin = ref(true);
    const error = ref('');
    const form = reactive({ email: '', password: '', name: '' });

    async function submitForm() {
        error.value = '';
        try {
            if (isLogin.value) {
                const res = await apiCall('/login', 'POST', { username: form.email, password: form.password });
                // Ensure we pass back the full user object including role if possible
                emit('login-success', { ...res.user, role: res.role }); 
            } else {
                await apiCall('/register', 'POST', { username: form.email, password: form.password, name: form.name });
                alert('Registration successful! Please login.');
                isLogin.value = true;
            }
        } catch (e) {
            error.value = e.message;
        }
    }

    return { isLogin, error, form, submitForm };
};


// --- Components Registration ---
const AdminDashboard = loadComponent('/static/components/admin_dashboard.html', adminSetup);
const DoctorDashboard = loadComponent('/static/components/doctor_dashboard.html', doctorSetup);
const PatientDashboard = loadComponent('/static/components/patient_dashboard.html', patientSetup);
const LoginRegister = loadComponent('/static/components/login_register.html', loginSetup);

// --- Main App ---
const MainApp = {
    setup() {
        const user = ref(null);
        
        async function checkUser() {
            try {
                const res = await apiCall('/current-user');
                if (res && res.user) user.value = { ...res.user, role: res.role };
            } catch (e) { /* Not logged in */ }
        }

        function onLoginSuccess(u) {
            user.value = u;
        }

        async function logout() {
            await apiCall('/logout', 'POST');
            user.value = null;
        }
        
        const currentDashboard = computed(() => {
            if (!user.value) return 'login-register';
            const role = user.value.role; // Using the 'role' property we added
            if (role === 'admin') return 'admin-dashboard';
            if (role === 'doctor') return 'doctor-dashboard';
            return 'patient-dashboard';
        });

        onMounted(checkUser);
        return { user, onLoginSuccess, logout, currentDashboard };
    }
};

const app = createApp(MainApp);
app.component('admin-dashboard', AdminDashboard);
app.component('doctor-dashboard', DoctorDashboard);
app.component('patient-dashboard', PatientDashboard);
app.component('login-register', LoginRegister);
app.mount('#app');
