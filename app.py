from flask import Flask, render_template
from models.database import db, User, Role, Department
from flask_security import Security, SQLAlchemyUserDatastore
from flask_security.utils import hash_password
from backend.routes.auth_routes import auth_bp
from backend.routes.admin_routes import admin_bp
from backend.routes.doctor_routes import doctor_bp
from backend.routes.patient_routes import patient_bp
import os

app = Flask(__name__, template_folder='frontend', static_folder='frontend/static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hospital.db'
app.config['SECRET_KEY'] = 'thisisasecretkey'
app.config['SECURITY_PASSWORD_SALT'] = 'somesalt'
app.config['SECURITY_REGISTERABLE'] = False
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
app.config['SECURITY_USERNAME_ENABLE'] = True 

db.init_app(app)

# Setup Flask-Security
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(admin_bp, url_prefix='/api')
app.register_blueprint(doctor_bp, url_prefix='/api')
app.register_blueprint(patient_bp, url_prefix='/api')

@app.route('/')
def index():
    return render_template('index.html')

def create_initial_data():
    with app.app_context():
        db.create_all()
        
        # Create Roles
        user_datastore.find_or_create_role(name='admin', description='Administrator')
        user_datastore.find_or_create_role(name='doctor', description='Doctor')
        user_datastore.find_or_create_role(name='patient', description='Patient')
        db.session.commit()

        # Create Admin if not exists
        if not user_datastore.find_user(username='admin'):
            user_datastore.create_user(
                username='admin', 
                password=hash_password('adminpassword'), 
                roles=['admin'], 
                name='Super Admin',
                active=True,
                fs_uniquifier='admin_uniq'
            )
            db.session.commit()
            print("Admin created: username='admin', password='adminpassword'")

        # Create Departments if not exists
        if not Department.query.first():
            depts = [
                Department(name='General Medicine', description='General health care'),
                Department(name='Cardiology', description='Heart related treatments'),
                Department(name='Dermatology', description='Skin related treatments'),
                Department(name='Pediatrics', description='Child health care'),
                Department(name='Neurology', description='Brain and nerves')
            ]
            db.session.add_all(depts)
            db.session.commit()
            print("Initial departments created")

if __name__ == '__main__':
    create_initial_data()
    app.run(debug=True, port=5000)
