def test_login_logout(test_client):
    """Test login and logout flow."""
    # Login with valid credentials
    response = test_client.post('/api/login', json={
        'username': 'admin',
        'password': 'admin'
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == 'Login successful'
    assert data['role'] == 'admin'

    # valid logout
    response = test_client.post('/api/logout')
    assert response.status_code == 200

def test_login_invalid(test_client):
    """Test login with invalid credentials."""
    response = test_client.post('/api/login', json={
        'username': 'admin',
        'password': 'wrongpassword'
    })
    assert response.status_code == 401

def test_register_patient(test_client):
    """Test patient registration."""
    response = test_client.post('/api/register', json={
        'username': 'newpatient',
        'password': 'password123',
        'name': 'New Patient'
    })
    assert response.status_code == 200
    
    # Verify login
    response = test_client.post('/api/login', json={
        'username': 'newpatient',
        'password': 'password123'
    })
    assert response.status_code == 200
    assert response.get_json()['role'] == 'patient'
