from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from sendgrid import SendGridAPIClient
from twilio.rest import Client
from dotenv import load_dotenv
from extensions import db
from models import init_db
from flask_migrate import Migrate
import os

# Load .env file
load_dotenv()

app = Flask(__name__)

# Update CORS with your actual frontend URL
CORS(app, resources={r"/api/*": {
    "origins": [
        "http://localhost:3000",
        "https://movie-frontend-3173.onrender.com",  # Your frontend URL
        "https://*.onrender.com"
    ],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"],
    "supports_credentials": True
}})

# Manual CORS handling for OPTIONS
@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    print(f"DEBUG: Handling OPTIONS request for /api/{path}")
    response = app.make_response('')
    origin = request.headers.get('Origin')
    
    # Allow specific origins
    allowed_origins = [
        'http://localhost:3000',
        'https://movie-frontend-3173.onrender.com'
    ]
    
    if origin in allowed_origins or (origin and 'onrender.com' in origin):
        response.headers['Access-Control-Allow-Origin'] = origin
    
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response

# Configuration from .env
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['SENDGRID_CLIENT'] = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
app.config['TWILIO_CLIENT'] = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
app.config['TWILIO_WHATSAPP_FROM'] = os.getenv('TWILIO_WHATSAPP_FROM')

# Health check endpoint
@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'movie-backend'}), 200

# Root endpoint
@app.route('/')
def index():
    return jsonify({
        'message': 'Movie Backend API',
        'version': '1.0',
        'endpoints': {
            'health': '/health',
            'api': '/api/*'
        }
    }), 200

# Debug middleware
@app.before_request
def log_request():
    print(f"DEBUG: {request.method} request to {request.path}")
    print(f"DEBUG: Origin: {request.headers.get('Origin')}")
    print(f"DEBUG: Headers: {dict(request.headers)}")

db.init_app(app)
jwt = JWTManager(app)
migrate = Migrate(app, db)
init_db(app)

# JWT error handlers
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

# Register API routes
from routes import api_blueprint
app.register_blueprint(api_blueprint, url_prefix='/api')
print("DEBUG: Registered api_blueprint with /api prefix")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False, host='0.0.0.0', port=5000)