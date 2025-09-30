from flask import Flask, send_from_directory, request
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

app = Flask(__name__, static_folder="../movie_frontend/build/static", static_url_path="/static")
CORS(app, resources={r"/api/*": {
    "origins": ["http://localhost:3000", "http://localhost:5000", "https://*.onrender.com"],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

# Manual CORS handling for OPTIONS
@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    print(f"DEBUG: Handling OPTIONS request for /api/{path}")
    response = app.make_response('')
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Max-Age'] = '86400'  # Cache preflight for 24 hours
    return response

# Configuration from .env
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['SENDGRID_CLIENT'] = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
app.config['TWILIO_CLIENT'] = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
app.config['TWILIO_WHATSAPP_FROM'] = os.getenv('TWILIO_WHATSAPP_FROM')

# Serve static files
@app.route('/static/<path:filename>')
def serve_static(filename):
    print(f"DEBUG: Serving /static/{filename}")
    return send_from_directory(app.static_folder, filename)

@app.route('/favicon.ico')
def serve_favicon():
    print("DEBUG: Serving favicon.ico")
    return send_from_directory('../movie_frontend/build', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_index(path):
    print(f"DEBUG: Serving index.html for path: {path}")
    return send_from_directory('../movie_frontend/build', 'index.html')

# Block /src/ requests to prevent SyntaxError
@app.route('/src/<path:filename>')
def block_src(filename):
    print(f"DEBUG: Blocked request to /src/{filename}")
    return 'Not Found', 404

# Debug middleware
@app.before_request
def log_request():
    print(f"DEBUG: Request to {request.path} with method {request.method}")

db.init_app(app)
jwt = JWTManager(app)
migrate = Migrate(app, db)  # Initialize Flask-Migrate
init_db(app)  # Initialize database with VIP settings

# JWT error handlers
@jwt.invalid_token_loader
def invalid_token_callback(error):
    print(f"DEBUG: JWT invalid token error: {error}")
    return {'message': 'Invalid token', 'error': str(error)}, 401

@jwt.unauthorized_loader
def unauthorized_callback(error):
    print(f"DEBUG: JWT unauthorized error: {error}")
    return {'message': 'Missing or invalid token', 'error': str(error)}, 401

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    print(f"DEBUG: JWT expired token error: {jwt_payload}")
    return {'message': 'Token expired', 'error': 'Token has expired'}, 401

from routes import api_blueprint
app.register_blueprint(api_blueprint, url_prefix='/api')
print("DEBUG: Registered api_blueprint with /api prefix")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False, host='0.0.0.0', port=5000)