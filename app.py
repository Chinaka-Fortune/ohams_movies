from flask import Flask, request, jsonify, make_response
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from sendgrid import SendGridAPIClient
from twilio.rest import Client
from dotenv import load_dotenv
from extensions import db
from models import init_db
from flask_migrate import Migrate
import os

# Load .env
load_dotenv()

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",
                "https://movie-frontend-3173.onrender.com",
                "https://ohams-movies-i2kb.vercel.app",
                "https://*.vercel.app",
                # "https://*.onrender.com",
                "ohams-movies.vercel.app",
                "https://www.ohamsmovies.com.ng",
                "https://ohamsmovies.com.ng",
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
        }
    },
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
app.config["SENDGRID_CLIENT"] = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))

def get_twilio_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise ValueError("Twilio credentials missing")
    return Client(sid, token)

# Add helper
def get_config(key, default=None):
    return os.getenv(key, default)

# Use in routes:
from_email = get_config("FROM_EMAIL", "no-reply@ohamsmovies.com.ng")
whatsapp_from = get_config("TWILIO_WHATSAPP_FROM")

required_env_vars = [
    "DATABASE_URL",
    "JWT_SECRET_KEY",
    "SENDGRID_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_FROM",
    "PAYSTACK_SECRET_KEY",
    "PAYSTACK_BASE_URL",
]
for var in required_env_vars:
    if not os.getenv(var):
        raise EnvironmentError(f"Missing required environment variable: {var}")

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "movie-backend"}), 200

@app.route("/")
def index():
    return (
        jsonify(
            {
                "message": "Movie Backend API",
                "version": "1.0",
                "endpoints": {"health": "/health", "api": "/api/*"},
            }
        ),
        200,
    )

@app.before_request
def log_request():
    headers = {
        k: v for k, v in request.headers.items() if k not in ["Authorization"]
    }
    print(f"DEBUG: {request.method} request to {request.path}")
    print(f"DEBUG: Origin: {request.headers.get('Origin')}")
    print(f"DEBUG: Headers: {headers}")


db.init_app(app)
jwt = JWTManager(app)
migrate = Migrate(app, db)


def init_app(app):
    with app.app_context():
        db.create_all()
        init_db(app)


init_app(app)

@jwt.invalid_token_loader
def invalid_token_callback(error):
    print(f"DEBUG: JWT invalid token error: {error}")
    return jsonify({"message": "Invalid token", "error": str(error)}), 401


@jwt.unauthorized_loader
def unauthorized_callback(error):
    print(f"DEBUG: JWT unauthorized error: {error}")
    return jsonify({"message": "Missing or invalid token", "error": str(error)}), 401


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    print(f"DEBUG: JWT expired token error: {jwt_payload}")
    return jsonify({"message": "Token expired", "error": "Token has expired"}), 401


from routes import api_blueprint

app.register_blueprint(api_blueprint, url_prefix="/api")
print("DEBUG: Registered api_blueprint with /api prefix")

@app.after_request
def after_request(response):
    origin = request.headers.get("Origin")
    allowed_origins = [
        "https://ohamsmovies.com.ng",
        "https://www.ohamsmovies.com.ng",
        "https://movie-frontend-3173.onrender.com",
        "ohams-movies.vercel.app",
        "http://localhost:3000",
    ]
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        
    return response

def handler(event, context):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    return app(event, context)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)