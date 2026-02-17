import pytest
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, user_datastore
from flask_security import hash_password

@pytest.fixture(scope='module')
def test_client():
    # Configure app for testing
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # Use in-memory DB
    app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for API tests
    app.config['SECURITY_PASSWORD_SALT'] = 'testsalt'
    app.config['SECRET_KEY'] = 'testkey'

    with app.app_context():
        db.create_all()
        
        # Setup Roles
        user_datastore.find_or_create_role(name='admin', description='Administrator')
        user_datastore.find_or_create_role(name='doctor', description='Doctor')
        user_datastore.find_or_create_role(name='patient', description='Patient')
        db.session.commit()

        # Create Admin
        user_datastore.create_user(
            username='admin', 
            email='admin@example.com',
            password=hash_password('admin'), 
            roles=['admin'], 
            active=True
        )

        # Create Departments
        from models.database import Department
        dept1 = Department(name='General')
        dept2 = Department(name='Neurology')
        db.session.add(dept1)
        db.session.add(dept2)
        db.session.commit()
        
        # Create Doctor - Assign to dept1
        user_datastore.create_user(
            username='doctor', 
            email='doctor@example.com',
            password=hash_password('docpassword'), 
            roles=['doctor'], 
            active=True,
            department_id=dept1.id,
            name='Dr. Test'
        )

        db.session.commit()
    
    testing_client = app.test_client()
    
    with app.app_context():
        yield testing_client
        db.session.remove()
        db.drop_all()

@pytest.fixture
def admin_token(test_client):
    """Helper to login as admin and get context if needed"""
    # Since we use session based auth with Flask-Security, we just log in via client
    test_client.post('/api/login', json={
        'username': 'admin',
        'password': 'admin'
    })
    return test_client

@pytest.fixture
def doctor_token(test_client):
    test_client.post('/api/login', json={
        'username': 'doctor',
        'password': 'docpassword'
    })
    return test_client
