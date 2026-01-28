from flask import Flask, render_template
from models.database import db, User, Department
from backend.routes import api
from flask_login import LoginManager

app = Flask(__name__, template_folder='frontend', static_folder='frontend/static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hospital.db'
app.config['SECRET_KEY'] = 'thisisasecretkey'

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

app.register_blueprint(api, url_prefix='/api')

@app.route('/')
def index():
    return render_template('index.html')

def create_initial_data():
    with app.app_context():
        db.create_all()
        
        # Create Admin if not exists
        if not User.query.filter_by(role='admin').first():
            admin = User(username='admin', password='adminpassword', role='admin', name='Super Admin')
            db.session.add(admin)
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
