from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Movie(db.Model):
    __tablename__ = 'movies'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    premiere_date = db.Column(db.Date, nullable=False)
    flier_image = db.Column(db.LargeBinary, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=13000.00)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'))
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    paystack_ref = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    ticket_type = db.Column(db.String(10), nullable=False, default='regular')
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

class Ticket(db.Model):
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'))
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'))
    token = db.Column(db.String(7), unique=True, nullable=False)
    ticket_type = db.Column(db.String(10), nullable=False, default='regular')
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    @staticmethod
    def generate_token():
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))

class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)

def init_db(app):
    with app.app_context():
        db.create_all()
        if not Setting.query.filter_by(key='vip_price').first():
            db.session.add(Setting(key='vip_price', value='25000.00'))
        if not Setting.query.filter_by(key='vip_limit').first():
            db.session.add(Setting(key='vip_limit', value='50'))
        db.session.commit()