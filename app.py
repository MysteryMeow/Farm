import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate, upgrade

# ------------------------------------------------------------------------------
# App & Database Configuration
# ------------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

database_url = os.environ.get("DATABASE_URL", "sqlite:///inventory.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------
class Plot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plot_number = db.Column(db.Integer, unique=True, nullable=False)
    crop = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), default='Empty')

    def __repr__(self):
        return f"<Plot {self.plot_number} - {self.status}>"


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(64), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(64), unique=True, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    used = db.Column(db.Integer, default=0)
    category = db.Column(db.String(64), nullable=False, default="Misc")

    @property
    def remaining(self):
        return self.stock - self.used


class InventoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)
    user = db.Column(db.String(64), nullable=False)
    item = db.Column(db.String(64), nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(128), nullable=False)

# ------------------------------------------------------------------------------
# Flask-Login Setup
# ------------------------------------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------------------------------------------------------------------
# Flask-Admin Integration
# ------------------------------------------------------------------------------
class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == "Admin"

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("login"))


admin = Admin(app, name='Inventory Admin', template_mode='bootstrap3')
admin.add_view(AdminModelView(User, db.session))
admin.add_view(AdminModelView(Stock, db.session))
admin.add_view(AdminModelView(InventoryLog, db.session))
admin.add_view(AdminModelView(Plot, db.session))

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    stocks = Stock.query.all()
    grouped_items = {}
    for item in stocks:
        category = item.category or "Uncategorized"
        if category not in grouped_items:
            grouped_items[category] = []
        grouped_items[category].append(item)

    for items in grouped_items.values():
        items.sort(key=lambda x: x.item.lower())

    grouped_items = dict(sorted(grouped_items.items()))
    return render_template("index.html", grouped_items=grouped_items, user_role=current_user.role)


@app.route("/map")
@login_required
def map_view():
    plots = Plot.query.order_by(Plot.plot_number).all()
    return render_template("farm_map.html", plots=plots, user_role=current_user.role)


@app.route("/admin/upgrade-db")
@login_required
def upgrade_db_route():
    if current_user.role != "Admin":
        return "Unauthorized", 403
    upgrade()
    return "Database upgraded successfully!"

# --- Your existing routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if current_user.role != "Admin":
        flash("You are not authorized to add new users.", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role", "Employee")
        if User.query.filter_by(username=username).first():
            flash("User already exists.", "danger")
            return redirect(url_for("register"))
        new_user = User(username=username, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash(f"User {username} added successfully.", "success")
        return redirect(url_for("index"))
    return render_template("register.html")


# All your other routes (log, add-item, reports, etc.) remain unchanged.
# You can continue copying them below this line if needed.
