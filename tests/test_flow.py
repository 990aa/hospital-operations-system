import pytest

def test_appointment_flow(test_client):
    """Test full flow: Patient registers -> Books Appt -> Doctor sees it"""
    
    # 1. Register Patient
    client = test_client
    client.post('/api/logout') 
    
    resp = client.post('/api/register', json={
        'username': 'sickpatient',
        'password': 'password',
        'name': 'Sick Patient'
    })
    assert resp.status_code == 200
    
    # Login as patient
    client.post('/api/login', json={'username': 'sickpatient', 'password': 'password'})
    
    # Get Dept and Doctor
    depts = client.get('/api/departments').get_json()
    assert len(depts) > 0
    dept_id = depts[0]['id']
    
    docs_resp = client.get(f'/api/doctors?department_id={dept_id}')
    docs = docs_resp.get_json()
    
    # Depending on which dept 'General' got ID 1, we might find 'Dr. Test'
    # 'Dr. Test' was assigned to logic 'dept1' in conftest.
    # We should search for Dr. Test's dept
    
    target_doc = None
    if docs:
        target_doc = docs[0]
    else:
        # Try other dept
        if len(depts) > 1:
            dept_id = depts[1]['id']
            docs = client.get(f'/api/doctors?department_id={dept_id}').get_json()
            if docs: target_doc = docs[0]
            
    assert target_doc is not None
    
    # Book Appointment
    book_resp = client.post('/api/appointments', json={
        'doctor_id': target_doc['id'],
        'date': '2023-12-25',
        'time': '10:00'
    })
    assert book_resp.status_code == 201
    
    # Logout patient
    client.post('/api/logout')
    
    # Login Doctor
    client.post('/api/login', json={'username': 'doctor', 'password': 'docpassword'})
    
    # Doctor checks appointments
    appt_resp = client.get('/api/doctor/appointments')
    appts = appt_resp.get_json()
    
    assert len(appts) > 0
    assert appts[0]['patient_name'] == 'Sick Patient'
    
    # Complete appointment
    appt_id = appts[0]['id']
    comp_resp = client.post(f'/api/appointments/{appt_id}/complete', json={
        'diagnosis': 'Flu',
        'prescription': 'Rest',
        'notes': 'Take care'
    })
    assert comp_resp.status_code == 200

