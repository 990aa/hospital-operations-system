def test_admin_stats_access(admin_token):
    """Test admin access to stats."""
    response = admin_token.get('/api/admin/stats')
    assert response.status_code == 200
    data = response.get_json()
    assert 'total_doctors' in data

def test_admin_unauthorized_access(test_client):
    """Test accessing admin route without login."""
    test_client.post('/api/logout') 
    response = test_client.get('/api/admin/stats')
    assert response.status_code in [302, 401] 

def test_add_doctor(admin_token):
    """Test adding a doctor."""
    # Get department ID
    resp = admin_token.get('/api/departments')
    depts = resp.get_json()
    assert len(depts) > 0
    dept_id = depts[0]['id']

    response = admin_token.post('/api/admin/doctors', json={
        'name': 'New Doc',
        'username': 'newdoc',
        'password': 'password',
        'department_id': dept_id
    })
    assert response.status_code == 201
    
    # Verify doctor added
    response = admin_token.get('/api/admin/doctors')
    data = response.get_json()
    assert any(d['username'] == 'newdoc' for d in data)

def test_delete_doctor(admin_token):
    """Test deleting a doctor."""
    # First find the id of username='doctor' (created in conftest)
    resp = admin_token.get('/api/admin/doctors')
    data = resp.get_json()
    # In conftest we created user with username='doctor'
    matching = [d for d in data if d['username'] == 'doctor']
    if not matching: pytest.skip("Doctor not found")
    
    doc_id = matching[0]['id']
    response = admin_token.delete(f'/api/admin/doctors/{doc_id}')
    assert response.status_code == 200
