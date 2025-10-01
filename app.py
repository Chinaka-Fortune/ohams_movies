from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from sendgrid import SendGridAPIClient
from twilio.rest import Client
from dotenv import load_dotenv
from extensions import db
from models import init_db
import os

load_dotenv()

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://movie-frontend-3173.onrender.com",
            "https://ohams-movies.onrender.com",
            "https://movieticketsapp.com"
        ],
        "methods": ["GET", "POST", "OPTIONS", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['SENDGRID_CLIENT'] = SendGridAPIClient(os.getenv('SENDGRID_API_KEY')) if os.getenv('SENDGRID_API_KEY') else None
app.config['TWILIO_CLIENT'] = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')) if os.getenv('TWILIO_ACCOUNT_SID') else None
app.config['TWILIO_WHATSAPP_FROM'] = os.getenv('TWILIO_WHATSAPP_FROM')

db.init_app(app)
jwt = JWTManager(app)
migrate = Migrate(app, db)
init_db(app)

@jwt.invalid_token_loader
def invalid_token_callback(error):
    print(f"DEBUG: JWT invalid token error: {error}")
    return jsonify({'message': 'Invalid token', 'error': str(error)}), 401

@jwt.unauthorized_loader
def unauthorized_callback(error):
    print(f"DEBUG: JWT unauthorized error: {error}")
    return jsonify({'message': 'Missing or invalid token', 'error': str(error)}), 401

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    print(f"DEBUG: JWT expired token error: {jwt_payload}")
    return jsonify({'message': 'Token expired', 'error': 'Token has expired'}), 401

from api.routes import api_blueprint
app.register_blueprint(api_blueprint, url_prefix='/api')
print("DEBUG: Registered api_blueprint with /api prefix")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False, host='0.0.0.0', port=5000)