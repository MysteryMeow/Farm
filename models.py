from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(64), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Stock(db.Model):
    __tablename__ = 'stocks'
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(64), unique=True, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    used = db.Column(db.Integer, default=0)
    category = db.Column(db.String(64), nullable=False, default="Misc")

    @property
    def remaining(self):
        return self.stock - self.used

class InventoryLog(db.Model):
    __tablename__ = 'inventory_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)
    user = db.Column(db.String(64), nullable=False)
    item = db.Column(db.String(64), nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(128), nullable=False)
