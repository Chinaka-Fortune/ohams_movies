from flask import Blueprint, request, jsonify, current_app, send_file, url_for
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from extensions import db
from models import User, Payment, Ticket, Movie, Setting
from sendgrid.helpers.mail import Mail, To
import requests
import os
from datetime import datetime
import base64
from PIL import Image
import io
import tempfile
import secrets
import re
import socket
import dns.resolver

api_blueprint = Blueprint('api', __name__)
print("DEBUG: Loading routes.py with blueprint v1")

resolver = dns.resolver.Resolver()
resolver.nameservers = ['8.8.8.8', '8.8.4.4']

def compress_image(image_data, max_size=(300, 300), quality=85):
    """Compress image to JPEG with specified max size and quality."""
    try:
        img = Image.open(io.BytesIO(image_data))
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        img.convert('RGB').save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"DEBUG: Image compression error: {str(e)}")
        return image_data

def upload_image_to_twilio(image_data, twilio_client):
    """Upload image to Twilio Content API and return media URL."""
    try:
        if len(image_data) > 5 * 1024 * 1024:  # 5MB limit
            print("DEBUG: Image exceeds size limit")
            return None
        img = Image.open(io.BytesIO(image_data))
        if img.format.lower() not in ['jpeg', 'png']:
            print("DEBUG: Unsupported image format")
            return None
        url = 'https://content.twilio.com/v1/Content'
        headers = {
            'Authorization': f'Basic {base64.b64encode(f"{os.getenv("TWILIO_ACCOUNT_SID")}:{os.getenv("TWILIO_AUTH_TOKEN")}".encode()).decode()}',
            'Content-Type': 'application/json'
        }
        payload = {
            'ContentType': 'image/jpeg',
            'FriendlyName': 'Movie Flier',
            'Content': base64.b64encode(image_data).decode('utf-8')
        }
        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()
        if response.status_code == 201:
            content_sid = response_data['sid']
            print(f"DEBUG: Image uploaded to Twilio, Content SID: {content_sid}")
            return f"https://content.twilio.com/v1/Content/{content_sid}"
        else:
            print(f"DEBUG: Failed to upload image to Twilio: {response_data}")
            return None
    except Exception as e:
        print(f"DEBUG: Error uploading image to Twilio: {str(e)}")
        return None

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))

def is_valid_phone(phone):
    pattern = r'^\+?\d{10,15}$'
    return bool(re.match(pattern, phone.strip()))

@api_blueprint.route('/register', methods=['POST'])
def register():
    print("DEBUG: /api/register endpoint called")
    try:
        data = request.json
        if not all(key in data for key in ['email', 'phone', 'password']):
            return jsonify({'message': 'Missing required fields'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'message': 'Email already exists'}), 400
        if User.query.filter_by(phone=data['phone']).first():
            return jsonify({'message': 'Phone already exists'}), 400
        user = User(email=data['email'], phone=data['phone'])
        user.set_password(data['password'])
        db.session.add(user)
        db.session.commit()
        return jsonify({'message': 'User created'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/login', methods=['POST'])
def login():
    print("DEBUG: /api/login endpoint called")
    try:
        data = request.json
        user = User.query.filter_by(email=data['email']).first()
        if user and user.check_password(data['password']):
            token = create_access_token(identity=str(user.id), additional_claims={'email': user.email, 'is_admin': user.is_admin})
            return jsonify({'token': token, 'is_admin': user.is_admin})
        return jsonify({'message': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/movies', methods=['GET'])
def get_movies():
    print("DEBUG: /api/movies endpoint called")
    try:
        movies = Movie.query.all()
        vip_price = float(Setting.query.filter_by(key='vip_price').first().value)
        return jsonify([{
            'id': m.id,
            'title': m.title,
            'premiere_date': str(m.premiere_date),
            'flier_image': base64.b64encode(m.flier_image).decode('utf-8') if m.flier_image else None,
            'regular_price': str(m.price),
            'vip_price': str(vip_price)
        } for m in movies])
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/movies', methods=['GET'])
@jwt_required()
def get_admin_movies():
    print("DEBUG: /api/admin/movies endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        movies = Movie.query.all()
        vip_price = float(Setting.query.filter_by(key='vip_price').first().value)
        return jsonify([{
            'id': m.id,
            'title': m.title,
            'premiere_date': str(m.premiere_date),
            'flier_image': base64.b64encode(m.flier_image).decode('utf-8') if m.flier_image else None,
            'regular_price': str(m.price),
            'vip_price': str(vip_price)
        } for m in movies])
    except Exception as e:
        print(f"DEBUG: Error in /api/admin/movies GET: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/verify-token', methods=['GET'])
@jwt_required()
def verify_token_endpoint():
    print("DEBUG: /api/verify-token endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        return jsonify({
            'message': 'Token is valid',
            'user': {
                'id': user.id,
                'email': user.email,
                'is_admin': user.is_admin
            }
        }), 200
    except Exception as e:
        print(f"DEBUG: Error in /api/verify-token: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 401

@api_blueprint.route('/image/<int:movie_id>', methods=['GET'])
def get_movie_image(movie_id):
    print("DEBUG: /api/image endpoint called")
    try:
        movie = Movie.query.get(movie_id)
        if not movie or not movie.flier_image:
            return jsonify({'message': 'Image not found'}), 404
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(movie.flier_image)
            temp_file_path = temp_file.name
        return send_file(temp_file_path, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/movies/v1', methods=['POST'])
@jwt_required()
def add_movie():
    print("DEBUG: /api/admin/movies/v1 endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        print(f"DEBUG: Identity: {user_id}, is_admin: {user.is_admin}")
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403

        if 'title' not in request.form or 'premiere_date' not in request.form or 'flier_image' not in request.files:
            return jsonify({'message': 'Missing required fields: title, premiere_date, flier_image'}), 400

        title = request.form['title']
        premiere_date_str = request.form['premiere_date']
        price = request.form.get('price', Setting.query.filter_by(key='regular_price').first().value)
        price = float(price)

        try:
            premiere_date = datetime.strptime(premiere_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return jsonify({'message': f'Invalid premiere_date format: {str(e)}'}), 400

        file = request.files['flier_image']
        if file.filename == '':
            return jsonify({'message': 'No selected file'}), 400

        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            return jsonify({'message': 'Invalid file type. Allowed: png, jpg, jpeg, gif'}), 400

        image_data = file.read()
        if len(image_data) > 5 * 1024 * 1024:
            return jsonify({'message': 'File too large. Max 5MB'}), 400

        compressed_image = compress_image(image_data)

        movie = Movie(title=title, premiere_date=premiere_date, flier_image=compressed_image, price=price)
        db.session.add(movie)
        db.session.commit()
        print("DEBUG: Movie added successfully v1")
        return jsonify({'message': 'Movie added'}), 201
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/admin/movies/v1: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/movies/<int:movie_id>', methods=['DELETE'])
@jwt_required()
def delete_movie(movie_id):
    print(f"DEBUG: /api/admin/movies/{movie_id} DELETE endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        print(f"DEBUG: Identity: {user_id}, is_admin: {user.is_admin}")
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        movie = Movie.query.get(movie_id)
        if not movie:
            return jsonify({'message': 'Movie not found'}), 404
        Ticket.query.filter_by(movie_id=movie_id).delete()
        Payment.query.filter_by(movie_id=movie_id).delete()
        db.session.delete(movie)
        db.session.commit()
        print(f"DEBUG: Movie {movie_id} deleted successfully")
        return jsonify({'message': 'Movie deleted'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/admin/movies/{movie_id} DELETE: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    print(f"DEBUG: /api/admin/users/{user_id} DELETE endpoint called")
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(int(admin_id))
        print(f"DEBUG: Identity: {admin_id}, is_admin: {admin.is_admin}")
        if not admin.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        if int(admin_id) == user_id:
            return jsonify({'message': 'Cannot delete own account'}), 403
        user = User.query.get(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
        Payment.query.filter_by(user_id=user_id).delete()
        Ticket.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
        print(f"DEBUG: User {user_id} deleted successfully")
        return jsonify({'message': 'User deleted'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/admin/users/{user_id} DELETE: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/tickets/<int:ticket_id>', methods=['DELETE'])
@jwt_required()
def delete_ticket(ticket_id):
    print(f"DEBUG: /api/admin/tickets/{ticket_id} DELETE endpoint called")
    try:
        admin_id = get_jwt_identity()
        admin = User.query.get(int(admin_id))
        print(f"DEBUG: Identity: {admin_id}, is_admin: {admin.is_admin}")
        if not admin.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        ticket = Ticket.query.get(ticket_id)
        if not ticket:
            return jsonify({'message': 'Ticket not found'}), 404
        db.session.delete(ticket)
        db.session.commit()
        print(f"DEBUG: Ticket {ticket_id} deleted successfully")
        return jsonify({'message': 'Ticket deleted'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/admin/tickets/{ticket_id} DELETE: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/tickets', methods=['GET'])
@jwt_required()
def get_tickets():
    print("DEBUG: /api/admin/tickets GET endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        tickets = Ticket.query.all()
        return jsonify([{
            'id': ticket.id,
            'user_id': ticket.user_id,
            'movie_id': ticket.movie_id,
            'payment_id': ticket.payment_id,
            'token': ticket.token,
            'ticket_type': ticket.ticket_type,
            'created_at': str(ticket.created_at)
        } for ticket in tickets]), 200
    except Exception as e:
        print(f"DEBUG: Error in /api/admin/tickets GET: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/verify-token', methods=['POST'])
@jwt_required()
def verify_token():
    print("DEBUG: /api/admin/verify-token endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        data = request.json
        if 'token' not in data:
            return jsonify({'message': 'Missing token'}), 400
        ticket = Ticket.query.filter_by(token=data['token']).first()
        if not ticket:
            return jsonify({'message': 'Invalid token'}), 404
        ticket_user = User.query.get(ticket.user_id)
        movie = Movie.query.get(ticket.movie_id)
        return jsonify({
            'valid': True,
            'user_email': ticket_user.email,
            'user_phone': ticket_user.phone,
            'movie_title': movie.title,
            'premiere_date': str(movie.premiere_date),
            'created_at': str(ticket.created_at),
            'ticket_type': ticket.ticket_type
        })
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/users', methods=['GET'])
@jwt_required()
def get_users():
    print("DEBUG: /api/admin/users endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        users = User.query.all()
        result = []
        for user in users:
            payments = Payment.query.filter_by(user_id=user.id).all()
            tickets = Ticket.query.filter_by(user_id=user.id).all()
            user_data = {
                'id': user.id,
                'email': user.email,
                'phone': user.phone,
                'is_admin': user.is_admin,
                'payments': [{
                    'id': p.id,
                    'movie_id': p.movie_id,
                    'amount': str(p.amount),
                    'status': p.status,
                    'paystack_ref': p.paystack_ref,
                    'ticket_type': p.ticket_type,
                    'created_at': str(p.created_at)
                } for p in payments],
                'tickets': [{
                    'id': t.id,
                    'movie_id': t.movie_id,
                    'token': t.token,
                    'ticket_type': t.ticket_type,
                    'created_at': str(t.created_at)
                } for t in tickets]
            }
            result.append(user_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/payments/initialize', methods=['POST'])
@jwt_required()
def initialize_payment():
    print("DEBUG: /api/payments/initialize endpoint called")
    try:
        user_id = get_jwt_identity()
        data = request.json
        print(f"DEBUG: Request data: {data}")
        if not data or 'movie_id' not in data or 'email' not in data or 'ticket_type' not in data:
            missing_fields = []
            if not data.get('movie_id'): missing_fields.append('movie_id')
            if not data.get('email'): missing_fields.append('email')
            if not data.get('ticket_type'): missing_fields.append('ticket_type')
            print(f"DEBUG: Missing required fields: {', '.join(missing_fields)}")
            return jsonify({'message': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        movie_id = int(data['movie_id'])
        email = data['email']
        ticket_type = data['ticket_type']
        if ticket_type not in ['regular', 'vip']:
            print(f"DEBUG: Invalid ticket_type: {ticket_type}")
            return jsonify({'message': 'Invalid ticket_type: must be regular or vip'}), 400
        user = User.query.get(int(user_id))
        print(f"DEBUG: User ID: {user_id}, Email: {user.email}, Provided Email: {email}")
        if user.email != email:
            print("DEBUG: Email does not match user")
            return jsonify({'message': 'Invalid email'}), 403
        movie = Movie.query.get(movie_id)
        if not movie:
            print(f"DEBUG: Movie not found for movie_id: {movie_id}")
            return jsonify({'message': 'Movie not found'}), 404

        if ticket_type == 'vip':
            vip_setting = Setting.query.filter_by(key='vip_price').first()
            if not vip_setting:
                print("DEBUG: vip_price setting not found")
                return jsonify({'message': 'VIP price not configured'}), 500
            vip_limit = int(Setting.query.filter_by(key='vip_limit').first().value)
            vip_count = Payment.query.filter_by(movie_id=movie_id, ticket_type='vip', status='success').count()
            if vip_count >= vip_limit:
                print(f"DEBUG: VIP limit reached: {vip_count}/{vip_limit}")
                return jsonify({'message': 'VIP tickets sold out'}), 400
            amount = float(vip_setting.value)
        else:
            amount = float(movie.price)

        headers = {
            'Authorization': f'Bearer {os.getenv("PAYSTACK_SECRET_KEY")}',
            'Content-Type': 'application/json'
        }
        frontend_url = os.getenv("FRONTEND_URL", "https://ohamsmovies.com.ng")
        callback_url = f"{frontend_url}/payment-status"
        payload = {
            'amount': int(amount * 100),
            'email': email,
            'callback_url': callback_url,
            'metadata': {'movie_id': movie_id, 'user_id': user.id, 'ticket_type': ticket_type}
        }
        print(f"DEBUG: Paystack payload: {payload}")
        
        # Test DNS resolution
        try:
            resolved_ip = resolver.resolve('api.paystack.co', 'A')
            print(f"DEBUG: Resolved api.paystack.co to {resolved_ip[0].to_text()}")
        except Exception as dns_error:
            print(f"DEBUG: DNS resolution failed: {str(dns_error)}")
            return jsonify({'message': f'Error: DNS resolution failed for Paystack API: {str(dns_error)}'}), 500

        # Make Paystack API call with retry logic
        try:
            response = requests.post(
                f'{os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")}/transaction/initialize',
                json=payload,
                headers=headers,
                timeout=10
            )
            response_data = response.json()
            print(f"DEBUG: Paystack response: {response_data}")
            if response.status_code != 200:
                print(f"DEBUG: Paystack error: {response_data}")
                return jsonify({'message': 'Payment initialization failed', 'error': response_data}), 400
        except requests.exceptions.RequestException as e:
            print(f"DEBUG: Network error calling Paystack API: {str(e)}")
            return jsonify({'message': f'Error: Network issue contacting Paystack: {str(e)}'}), 500

        payment = Payment(
            user_id=user.id,
            movie_id=movie_id,
            amount=amount,
            paystack_ref=response_data['data']['reference'],
            status='pending',
            ticket_type=ticket_type
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify({
            'authorization_url': response_data['data']['authorization_url'],
            'reference': response_data['data']['reference']
        })
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/payments/initialize: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/payment-callback', methods=['GET'])
def payment_callback():
    print("DEBUG: /api/payment-callback endpoint called")
    try:
        reference = request.args.get('reference')
        if not reference:
            print("DEBUG: No reference provided in callback")
            return jsonify({'message': 'Missing reference'}), 400
        
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        redirect_url = f"{frontend_url}/payment-status?reference={reference}"
        return jsonify({
            'message': 'Payment callback received',
            'redirect': redirect_url
        }), 200
    except Exception as e:
        print(f"DEBUG: Error in /api/payment-callback: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/payments/verify/<reference>', methods=['GET'])
def verify_payment(reference):
    print(f"DEBUG: /api/payments/verify/{reference} endpoint called")
    try:
        user_id = None
        try:
            jwt = get_jwt()
            user_id = get_jwt_identity()
            print(f"DEBUG: JWT provided, user_id: {user_id}")
        except:
            print("DEBUG: No valid JWT provided, proceeding without authentication")

        payment = Payment.query.filter_by(paystack_ref=reference).first()
        if not payment:
            print(f"DEBUG: Payment not found for reference: {reference}")
            return jsonify({'message': 'Payment not found'}), 404
        if user_id and payment.user_id != int(user_id):
            print(f"DEBUG: User ID mismatch: payment.user_id={payment.user_id}, jwt.user_id={user_id}")
            return jsonify({'message': 'Unauthorized access to payment'}), 403

        headers = {'Authorization': f'Bearer {os.getenv("PAYSTACK_SECRET_KEY")}'}
        response = requests.get(
            f'{os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")}/transaction/verify/{reference}',
            headers=headers
        )
        response_data = response.json()
        print(f"DEBUG: Paystack verify response: {response_data}")
        if response.status_code != 200 or response_data['data']['status'] != 'success':
            print(f"DEBUG: Payment verification failed: {response_data}")
            return jsonify({'message': 'Payment verification failed', 'error': response_data}), 400

        if payment.status != 'success':
            payment.status = 'success'
            ticket_token = Ticket.generate_token()
            ticket = Ticket(
                user_id=payment.user_id,
                movie_id=payment.movie_id,
                payment_id=payment.id,
                token=ticket_token,
                ticket_type=payment.ticket_type
            )
            db.session.add(ticket)
            db.session.commit()
            movie = Movie.query.get(payment.movie_id)
            user = User.query.get(payment.user_id)
            
            event_title = movie.title
            event_date = str(movie.premiere_date)
            event_time = movie.event_time
            event_location = movie.event_location
            
            ticket_type_label = 'VIP' if payment.ticket_type == 'vip' else 'Regular'
            flier_data_uri = f"data:image/jpeg;base64,{base64.b64encode(movie.flier_image).decode('utf-8')}" if movie.flier_image else ""
            
            email_message = f"""
Dear {user.email},

Thank you for purchasing a {ticket_type_label} ticket to the highly anticipated premiere of "{event_title}". We're thrilled to have you join us for this exclusive event.

Your access code is: {ticket_token}

- Date: {event_date}
- Time: {event_time}
- Location: {event_location}

Join us for an evening of drama, suspense, and intrigue as we unveil the cinematic masterpiece that explores the complexities of family dynamics. Meet the cast, get exclusive behind-the-scenes insights, and be among the first to experience the film.

Please arrive 30 minutes prior to the screening time to allow for smooth entry and seating. Complimentary refreshments will be provided. Photo opportunities with the cast will be available during the red carpet.

Thank you again for your support! We're honored to share this cinematic journey with you.

Best regards,
<br><img src="{flier_data_uri}" alt="Movie Flier" style="max-width: 100%; height: auto;">
"""
            message = Mail(
                from_email=current_app.config['FROM_EMAIL'],
                to_emails=user.email,
                subject=f'{ticket_type_label} Ticket for {event_title}',
                html_content=email_message
            )
            try:
                sendgrid_client = current_app.config['SENDGRID_CLIENT']
                if sendgrid_client:
                    sendgrid_client.send(message)
                    print(f"DEBUG: {ticket_type_label} Email sent to {user.email} via SendGrid")
                else:
                    print("DEBUG: SendGrid is disabled, skipping email")
            except Exception as e:
                print(f"DEBUG: SendGrid error: {str(e)}")
            
            try:
                twilio_client = current_app.config['TWILIO_CLIENT']
                if twilio_client and user.phone:
                    whatsapp_message = f"""
Dear {user.email},

Thank you for purchasing a {ticket_type_label} ticket to the premiere of "{event_title}".

Your access code: {ticket_token}

- Date: {event_date}
- Time: {event_time}
- Location: {event_location}

Join us for an evening of drama and intrigue. Arrive 30 minutes early for smooth entry. Complimentary refreshments and photo opportunities with the cast will be available.

Thank you for your support!
"""
                    media_url = []
                    if movie.flier_image:
                        media_url = [upload_image_to_twilio(movie.flier_image, twilio_client)]
                        media_url = [url for url in media_url if url]
                    twilio_client.messages.create(
                        from_=current_app.config['TWILIO_WHATSAPP_FROM'],
                        body=whatsapp_message,
                        media_url=media_url,
                        to=f"whatsapp:{user.phone}"
                    )
                    print(f"DEBUG: {ticket_type_label} WhatsApp message sent to {user.phone}")
                else:
                    print("DEBUG: Twilio is disabled or no phone number, skipping WhatsApp message")
            except Exception as e:
                print(f"DEBUG: Twilio error: {str(e)}")
        
        return jsonify({'message': 'Payment verified', 'ticket_token': ticket_token, 'ticket_type': payment.ticket_type})
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/payments/verify/{reference}: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/send-event-email', methods=['POST'])
@jwt_required()
def send_event_email():
    print("DEBUG: /api/admin/send-event-email endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        data = request.json
        if not all(key in data for key in ['movie_id', 'email', 'phone']):
            return jsonify({'message': 'Missing required fields: movie_id, email, phone'}), 400
        movie = Movie.query.get(data['movie_id'])
        if not movie:
            print(f"DEBUG: Movie not found for movie_id: {data['movie_id']}")
            return jsonify({'message': 'Movie not found'}), 404
        
        email_list = [email.strip() for email in data['email'].split(',')]
        phone_list = [phone.strip() for phone in data['phone'].split(',')]
        if len(email_list) != len(phone_list):
            return jsonify({'message': 'Number of emails and phone numbers must match'}), 400
        for email in email_list:
            if not is_valid_email(email):
                return jsonify({'message': f'Invalid email format: {email}'}), 400
        for phone in phone_list:
            if not is_valid_phone(phone):
                return jsonify({'message': f'Invalid phone format: {phone}'}), 400
        
        ticket_tokens = []
        
        for email, phone in zip(email_list, phone_list):
            target_user = User.query.filter_by(email=email).first()
            if not target_user:
                print(f"DEBUG: User not found for email: {email}, creating new user")
                random_password = secrets.token_urlsafe(12)
                target_user = User(email=email, phone=phone)
                target_user.set_password(random_password)
                db.session.add(target_user)
                db.session.commit()
                print(f"DEBUG: New user created with email: {email}, phone: {phone}")
            
            ticket_token = Ticket.generate_token()
            ticket = Ticket(
                user_id=target_user.id,
                movie_id=data['movie_id'],
                token=ticket_token,
                ticket_type='vip'
            )
            db.session.add(ticket)
            ticket_tokens.append({'email': email, 'ticket_token': ticket_token})
            
            flier_data_uri = f"data:image/jpeg;base64,{base64.b64encode(movie.flier_image).decode('utf-8')}" if movie.flier_image else ""
            
            message = Mail(
                from_email=current_app.config['FROM_EMAIL'],
                to_emails=To(email),
                subject=f'VIP Event: {movie.title}',
                html_content=f'Your VIP ticket token: {ticket_token}<br>Movie: {movie.title}<br>Date: {movie.premiere_date}<br><img src="{flier_data_uri}" alt="Movie Flier" style="max-width: 100%; height: auto;">'
            )
            try:
                sendgrid_client = current_app.config['SENDGRID_CLIENT']
                if sendgrid_client:
                    sendgrid_client.send(message)
                    print(f"DEBUG: VIP Email sent to {email} via SendGrid")
                else:
                    print("DEBUG: SendGrid is disabled, skipping email")
            except Exception as e:
                print(f"DEBUG: SendGrid error for {email}: {str(e)}")
        
        db.session.commit()
        return jsonify({'message': 'Emails sent', 'tickets': ticket_tokens})
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/admin/send-event-email: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/send-whatsapp', methods=['POST'])
@jwt_required()
def send_whatsapp():
    print("DEBUG: /api/admin/send-whatsapp endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        data = request.json
        if not all(key in data for key in ['movie_id', 'phone']):
            return jsonify({'message': 'Missing required fields: movie_id, phone'}), 400
        movie_id = data['movie_id']
        print(f"DEBUG: Processing movie_id: {movie_id}")
        movie = Movie.query.get(movie_id)
        if not movie:
            print(f"DEBUG: Movie not found for movie_id: {movie_id}")
            return jsonify({'message': 'Movie not found'}), 404
        
        phone_list = [phone.strip() for phone in data['phone'].split(',')]
        for phone in phone_list:
            if not is_valid_phone(phone):
                return jsonify({'message': f'Invalid phone format: {phone}'}), 400
        
        errors = []
        ticket_tokens = []
        
        try:
            twilio_client = current_app.config['TWILIO_CLIENT']
            if twilio_client:
                for phone in phone_list:
                    try:
                        target_user = User.query.filter_by(phone=phone).first()
                        ticket_token = None
                        if target_user:
                            ticket_token = Ticket.generate_token()
                            ticket = Ticket(
                                user_id=target_user.id,
                                movie_id=movie_id,
                                token=ticket_token,
                                ticket_type='vip'
                            )
                            db.session.add(ticket)
                            ticket_tokens.append({'phone': phone, 'ticket_token': ticket_token})
                        
                        media_url = []
                        if movie.flier_image:
                            media_url = [upload_image_to_twilio(movie.flier_image, twilio_client)]
                            media_url = [url for url in media_url if url]
                        print(f"DEBUG: Sending WhatsApp to {phone}, has_image: {bool(movie.flier_image)}, media_url: {media_url}")
                        body = f"VIP Event: {movie.title}\nDate: {movie.premiere_date}"
                        if ticket_token:
                            body += f"\nYour VIP ticket token: {ticket_token}"
                        twilio_client.messages.create(
                            from_=current_app.config['TWILIO_WHATSAPP_FROM'],
                            body=body,
                            media_url=media_url,
                            to=f"whatsapp:{phone}"
                        )
                        print(f"DEBUG: WhatsApp message sent to {phone}")
                    except Exception as e:
                        error_msg = f"Twilio error for {phone}: {str(e)}"
                        print(f"DEBUG: {error_msg}")
                        errors.append(error_msg)
                db.session.commit()
                if errors:
                    return jsonify({'message': 'Some WhatsApp messages failed', 'errors': errors, 'tickets': ticket_tokens}), 207
                return jsonify({'message': 'WhatsApp messages sent', 'tickets': ticket_tokens})
            else:
                error_msg = 'Twilio client not configured'
                print(f"DEBUG: {error_msg}")
                return jsonify({'message': error_msg}), 500
        except Exception as e:
            db.session.rollback()
            error_msg = f'Twilio error: {str(e)}'
            print(f"DEBUG: {error_msg}")
            return jsonify({'message': error_msg}), 500
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/admin/send-whatsapp: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/send-vip-ticket', methods=['POST'])
@jwt_required()
def send_vip_ticket():
    print("DEBUG: /api/admin/send-vip-ticket endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        data = request.json
        if not all(key in data for key in ['movie_id', 'recipient', 'phone', 'method']):
            return jsonify({'message': 'Missing required fields: movie_id, recipient, phone, method'}), 400
        if data['method'] not in ['email', 'whatsapp']:
            return jsonify({'message': 'Invalid method: must be email or whatsapp'}), 400
        
        movie = Movie.query.get(data['movie_id'])
        if not movie:
            print(f"DEBUG: Movie not found for movie_id: {data['movie_id']}")
            return jsonify({'message': 'Movie not found'}), 404
        
        recipient = data['recipient'].strip()
        phone = data['phone'].strip()
        if data['method'] == 'email':
            if not is_valid_email(recipient):
                return jsonify({'message': f'Invalid email format: {recipient}'}), 400
        if not is_valid_phone(phone):
            return jsonify({'message': f'Invalid phone format: {phone}'}), 400
        
        target_user = None
        if data['method'] == 'email':
            target_user = User.query.filter_by(email=recipient).first()
            if not target_user:
                print(f"DEBUG: User not found for email: {recipient}, creating new user")
                random_password = secrets.token_urlsafe(12)
                target_user = User(email=recipient, phone=phone)
                target_user.set_password(random_password)
                db.session.add(target_user)
                db.session.commit()
                print(f"DEBUG: New user created with email: {recipient}, phone: {phone}")
        else:  # whatsapp
            target_user = User.query.filter_by(phone=phone).first()
            if not target_user:
                print(f"DEBUG: User not found for phone: {phone}, creating new user")
                random_email = f"vip_{secrets.token_hex(8)}@example.com"
                random_password = secrets.token_urlsafe(12)
                target_user = User(email=random_email, phone=phone)
                target_user.set_password(random_password)
                db.session.add(target_user)
                db.session.commit()
                print(f"DEBUG: New user created with phone: {phone}, email: {random_email}")
        
        vip_limit = int(Setting.query.filter_by(key='vip_limit').first().value)
        vip_count = Ticket.query.filter_by(movie_id=data['movie_id'], ticket_type='vip').count()
        if vip_count >= vip_limit:
            print(f"DEBUG: VIP limit reached: {vip_count}/{vip_limit}")
            return jsonify({'message': 'VIP tickets sold out'}), 400

        ticket_token = Ticket.generate_token()
        ticket = Ticket(
            user_id=target_user.id,
            movie_id=data['movie_id'],
            token=ticket_token,
            ticket_type='vip'
        )
        db.session.add(ticket)
        db.session.commit()
        
        flier_data_uri = f"data:image/jpeg;base64,{base64.b64encode(movie.flier_image).decode('utf-8')}" if movie.flier_image else ""
        
        if data['method'] == 'email':
            message = Mail(
                from_email=current_app.config['FROM_EMAIL'],
                to_emails=To(recipient),
                subject=f'VIP Ticket for {movie.title}',
                html_content=f'Your VIP ticket token: {ticket_token}<br>Movie: {movie.title}<br>Date: {movie.premiere_date}<br><img src="{flier_data_uri}" alt="Movie Flier" style="max-width: 100%; height: auto;">'
            )
            try:
                sendgrid_client = current_app.config['SENDGRID_CLIENT']
                if sendgrid_client:
                    sendgrid_client.send(message)
                    print(f"DEBUG: VIP email sent to {recipient}")
                else:
                    print("DEBUG: SendGrid is disabled, skipping email")
            except Exception as e:
                print(f"DEBUG: SendGrid error for {recipient}: {str(e)}")
                return jsonify({'message': f'Error sending email: {str(e)}'}), 500
        else:  # whatsapp
            try:
                twilio_client = current_app.config['TWILIO_CLIENT']
                if twilio_client:
                    media_url = []
                    if movie.flier_image:
                        media_url = [upload_image_to_twilio(movie.flier_image, twilio_client)]
                        media_url = [url for url in media_url if url]
                    print(f"DEBUG: Sending VIP WhatsApp to {phone}, has_image: {bool(movie.flier_image)}, media_url: {media_url}")
                    twilio_client.messages.create(
                        from_=current_app.config['TWILIO_WHATSAPP_FROM'],
                        body=f"VIP Ticket\nEvent: {movie.title}\nDate: {movie.premiere_date}\nYour ticket token: {ticket_token}",
                        media_url=media_url,
                        to=f"whatsapp:{phone}"
                    )
                    print(f"DEBUG: VIP WhatsApp message sent to {phone}")
                else:
                    print("DEBUG: Twilio is disabled, skipping WhatsApp message")
                    return jsonify({'message': 'Twilio client not configured'}), 500
            except Exception as e:
                print(f"DEBUG: Twilio error for {phone}: {str(e)}")
                return jsonify({'message': f'Error sending WhatsApp: {str(e)}'}), 500
        
        return jsonify({'message': f'VIP ticket sent via {data['method']}', 'ticket_token': ticket_token})
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/admin/send-vip-ticket: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/send-reminder', methods=['POST'])
@jwt_required()
def send_reminder():
    print("DEBUG: /api/admin/send-reminder endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        data = request.json
        if not all(key in data for key in ['movie_id', 'recipients', 'phones', 'method', 'message']):
            return jsonify({'message': 'Missing required fields: movie_id, recipients, phones, method, message'}), 400
        if data['method'] not in ['email', 'whatsapp']:
            return jsonify({'message': 'Invalid method: must be email or whatsapp'}), 400
        
        movie = Movie.query.get(data['movie_id'])
        if not movie:
            print(f"DEBUG: Movie not found for movie_id: {data['movie_id']}")
            return jsonify({'message': 'Movie not found'}), 404
        
        recipient_list = [recipient.strip() for recipient in data['recipients'].split(',')]
        phone_list = [phone.strip() for phone in data['phones'].split(',')]
        if len(recipient_list) != len(phone_list):
            return jsonify({'message': 'Number of recipients and phone numbers must match'}), 400
        
        if data['method'] == 'email':
            for recipient in recipient_list:
                if not is_valid_email(recipient):
                    return jsonify({'message': f'Invalid email format: {recipient}'}), 400
        for phone in phone_list:
            if not is_valid_phone(phone):
                return jsonify({'message': f'Invalid phone format: {phone}'}), 400
        
        errors = []
        
        flier_data_uri = f"data:image/jpeg;base64,{base64.b64encode(movie.flier_image).decode('utf-8')}" if movie.flier_image else ""
        
        if data['method'] == 'email':
            for recipient, phone in zip(recipient_list, phone_list):
                try:
                    message = Mail(
                        from_email=current_app.config['FROM_EMAIL'],
                        to_emails=To(recipient),
                        subject=f'Reminder: {movie.title}',
                        html_content=f'{data["message"]}<br>Movie: {movie.title}<br>Date: {movie.premiere_date}<br><img src="{flier_data_uri}" alt="Movie Flier" style="max-width: 100%; height: auto;">'
                    )
                    sendgrid_client = current_app.config['SENDGRID_CLIENT']
                    if sendgrid_client:
                        sendgrid_client.send(message)
                        print(f"DEBUG: Reminder email sent to {recipient}")
                    else:
                        print("DEBUG: SendGrid is disabled, skipping email")
                except Exception as e:
                    error_msg = f"SendGrid error for {recipient}: {str(e)}"
                    print(f"DEBUG: {error_msg}")
                    errors.append(error_msg)
        else:
            try:
                twilio_client = current_app.config['TWILIO_CLIENT']
                if twilio_client:
                    for phone in phone_list:
                        try:
                            media_url = []
                            if movie.flier_image:
                                media_url = [upload_image_to_twilio(movie.flier_image, twilio_client)]
                                media_url = [url for url in media_url if url]
                            print(f"DEBUG: Sending reminder WhatsApp to {phone}, has_image: {bool(movie.flier_image)}, media_url: {media_url}")
                            twilio_client.messages.create(
                                from_=current_app.config['TWILIO_WHATSAPP_FROM'],
                                body=f"Reminder: {data['message']}\nEvent: {movie.title}\nDate: {movie.premiere_date}",
                                media_url=media_url,
                                to=f"whatsapp:{phone}"
                            )
                            print(f"DEBUG: Reminder WhatsApp message sent to {phone}")
                        except Exception as e:
                            error_msg = f"Twilio error for {phone}: {str(e)}"
                            print(f"DEBUG: {error_msg}")
                            errors.append(error_msg)
                else:
                    error_msg = 'Twilio client not configured'
                    print(f"DEBUG: {error_msg}")
                    return jsonify({'message': error_msg}), 500
            except Exception as e:
                error_msg = f'Twilio error: {str(e)}'
                print(f"DEBUG: {error_msg}")
                return jsonify({'message': error_msg}), 500
        
        if errors:
            return jsonify({'message': 'Some reminder messages failed', 'errors': errors}), 207
        return jsonify({'message': 'Reminder messages sent'})
    except Exception as e:
        print(f"DEBUG: Error in /api/admin/send-reminder: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/settings', methods=['POST'])
@jwt_required()
def update_settings():
    print("DEBUG: /api/settings POST endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        data = request.json
        vip_price = data.get('vip_price')
        vip_limit = data.get('vip_limit')
        if vip_price is None and vip_limit is None:
            return jsonify({'message': 'At least one setting (vip_price or vip_limit) required'}), 400
        if vip_price is not None:
            if float(vip_price) <= 0:
                return jsonify({'message': 'VIP price must be positive'}), 400
            setting = Setting.query.filter_by(key='vip_price').first()
            setting.value = str(float(vip_price))
            db.session.commit()
        if vip_limit is not None:
            if int(vip_limit) < 0:
                return jsonify({'message': 'VIP limit must be non-negative'}), 400
            setting = Setting.query.filter_by(key='vip_limit').first()
            setting.value = str(int(vip_limit))
            db.session.commit()
        return jsonify({'message': 'Settings updated'})
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in /api/settings POST: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/settings', methods=['GET'])
@jwt_required()
def get_settings():
    print("DEBUG: /api/settings GET endpoint called")
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        settings = Setting.query.all()
        return jsonify({s.key: s.value for s in settings})
    except Exception as e:
        print(f"DEBUG: Error in /api/settings GET: {str(e)}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

@api_blueprint.route('/admin/test', methods=['POST'])
@jwt_required()
def test_route():
    print("DEBUG: /api/admin/test endpoint called")
    return jsonify({'message': 'Test route works'})

@api_blueprint.route('/admin/no-auth-test', methods=['POST'])
def no_auth_test():
    print("DEBUG: /api/admin/no-auth-test endpoint called")
    return jsonify({'message': 'No auth test route works'})

@api_blueprint.route('/debug', methods=['GET'])
def debug():
    print("DEBUG: /api/debug endpoint called")
    return jsonify({'message': 'Blueprint v1 is active'})