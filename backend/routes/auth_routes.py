from flask import Blueprint, request, jsonify
from flask_security import login_user, logout_user, login_required, current_user, verify_password
from models.database import db, User, Patient
from flask_security.utils import hash_password

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    """Log in a user (Admin, Doctor, or Patient)."""
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
         return jsonify({"message": "Username and password required"}), 400

    user = User.query.filter_by(username=username).first()
    
    # Using flask-security verify_password/hash_password logic if desired, 
    # but for "simplest codes" if I seeded with plain text, I should stick to plain text?
    # NO. User requirements: "ensure ... flask security". Flask security defaults to hashing.
    # The initial seeder in app.py created users with plain text passwords. 
    # I MUST update the seeder to use hash_password.
    # And here I must use verify_password.
    
    if user and verify_password(password, user.password):
        login_user(user)
        # Identify role for frontend
        role = 'patient'
        if user.has_role('admin'): role = 'admin'
        elif user.has_role('doctor'): role = 'doctor'
        
        return jsonify({"message": "Login successful", "role": role, "user": user.to_dict()})
    
    return jsonify({"message": "Invalid credentials"}), 401

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    return jsonify({"message": "Logged out"})

@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new patient."""
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"message": "Username already exists"}), 400
    
    # Create User
    # Flask Security User creation usually involves user_datastore.create_user if managing roles properly.
    # But direct DB access is "simplest code". I'll manually add the role.
    from app import user_datastore # Circular import? I should pass datastore or use current_app
    from flask import current_app
    
    # Better: use datastore attached to app extensions
    user_datastore = current_app.extensions['security'].datastore
    
    new_user = user_datastore.create_user(
        username=data['username'],
        password=hash_password(data['password']),
        name=data['name'],
        active=True
    )
    user_datastore.add_role_to_user(new_user, 'patient')
    db.session.commit()

    # Create Patient Profile
    new_patient = Patient(user_id=new_user.id)
    db.session.add(new_patient)
    db.session.commit()

    return jsonify({"message": "Registration successful"})

@auth_bp.route('/current-user', methods=['GET'])
def get_current_user():
    if current_user.is_authenticated:
        return jsonify(current_user.to_dict())
    return jsonify(None), 401
