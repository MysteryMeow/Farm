import os
from datetime import datetime
import pandas as pd
from wtforms.fields import SelectField
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, flash, send_file
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate

# ------------------------------------------------------------------------------
# App & Database Configuration
# ------------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

# Use DATABASE_URL if provided (for Heroku Postgres), else fallback to SQLite.
database_url = os.environ.get("DATABASE_URL", "sqlite:///inventory.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ------------------------------------------------------------------------------
# Flask-Login Setup
# ------------------------------------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"


# ------------------------------------------------------------------------------
# Database Models
# ------------------------------------------------------------------------------
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

    def __repr__(self):
        return f'<User {self.username}>'


class Stock(db.Model):
    __tablename__ = 'stocks'
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(64), unique=True, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    used = db.Column(db.Integer, default=0)
    remaining = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(64), nullable=False, default="Misc")

    def __repr__(self):
        return f'<Stock {self.item}>'


class InventoryLog(db.Model):
    __tablename__ = 'inventory_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)
    user = db.Column(db.String(64), nullable=False)
    item = db.Column(db.String(64), nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return f'<InventoryLog {self.item} - {self.quantity_used}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------------------------------------------------------------------
# Flask-Admin Integration
# ------------------------------------------------------------------------------
class AdminModelView(ModelView):
    form_overrides = {
        'category': SelectField
    }

    form_args = {
        'category': {
            'choices': [('Misc', 'Misc'), ('Clothing', 'Clothing'), ('Security Gear', 'Security Gear')]
        }
    }

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == "Admin"

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("login"))


admin = Admin(app, name='Inventory Admin', template_mode='bootstrap3')
admin.add_view(AdminModelView(User, db.session))
admin.add_view(AdminModelView(Stock, db.session))
admin.add_view(AdminModelView(InventoryLog, db.session))


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    # Query and group items by category
    stocks = Stock.query.all()
    grouped_items = {}
    for item in stocks:
        category = item.category or "Uncategorized"
        if category not in grouped_items:
            grouped_items[category] = []
        grouped_items[category].append(item)

    # Sort each category's items alphabetically by item name
    for items in grouped_items.values():
        items.sort(key=lambda x: x.item.lower())

    # Sort categories alphabetically
    grouped_items = dict(sorted(grouped_items.items()))

    return render_template("index.html", grouped_items=grouped_items, user_role=current_user.role)


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


@app.route("/log", methods=["POST"])
@login_required
def log_usage():
    item_name = request.form.get("item")
    try:
        quantity_used = int(request.form.get("quantity"))
        if quantity_used < 1:
            return jsonify({"success": False, "message": "Quantity must be at least 1."})
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid quantity."})

    stock_item = Stock.query.filter_by(item=item_name).first()
    if stock_item:
        action = "Usage Logged" if quantity_used > 0 else "Restocked"
        stock_item.used += max(quantity_used, 0)
        if quantity_used > 0:
            stock_item.used += quantity_used
            stock_item.remaining = stock_item.stock - stock_item.used
        else:
            stock_item.stock += abs(quantity_used)
            stock_item.remaining += abs(quantity_used)

        new_log = InventoryLog(
            timestamp=datetime.now(),
            user=current_user.username,
            item=item_name,
            quantity_used=quantity_used,
            action=action
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify(
            {"success": True, "message": f"{quantity_used} units of {item_name} logged by {current_user.username}."})
    else:
        return jsonify({"success": False, "message": f"Item '{item_name}' not found."})


@app.route("/add-item", methods=["POST"])
@login_required
def add_item():
    item_name = request.form.get("item")
    try:
        stock_val = int(request.form.get("stock"))
        if stock_val < 1:
            return jsonify({"success": False, "message": "Stock must be at least 1."})
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid stock value."})

    stock_item = Stock.query.filter_by(item=item_name).first()
    if stock_item:
        stock_item.stock += stock_val
        stock_item.remaining += stock_val

        new_log = InventoryLog(
            timestamp=datetime.now(),
            user=current_user.username,
            item=item_name,
            quantity_used=stock_val,
            action="Restocked"
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify({"success": True, "message": f"{stock_val} units restocked for {item_name}."})
    else:
        return jsonify(
            {"success": False, "message": f"Item '{item_name}' not found in stock. Cannot restock non-existing item."})


@app.route("/export")
@login_required
def export_data():
    if current_user.role != "Admin":
        return jsonify({"error": "You are not authorized to export data."}), 403
    stocks = Stock.query.all()
    data = [
        {"Item": stock.item, "Stock": stock.stock, "Used": stock.used, "Remaining": stock.remaining}
        for stock in stocks
    ]
    return jsonify(data)


@app.route("/download-log")
@login_required
def download_log():
    if current_user.role != "Admin":
        return jsonify({"error": "You are not authorized to download the log."}), 403
    logs = InventoryLog.query.all()
    data = [{
        "Timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "User": log.user,
        "Item": log.item,
        "Quantity Used": log.quantity_used,
        "Action": log.action
    } for log in logs]
    return jsonify(data)


# (remaining routes unchanged)
@app.route("/report/most-used-data")
@login_required
def most_used_data():
    results = db.session.query(Stock.item, Stock.used).order_by(Stock.used.desc()).limit(10).all()
    return jsonify({item: used for item, used in results})


# Route: Employee Usage Data for Chart.js
@app.route("/report/employee-usage-data")
@login_required
def employee_usage_data():
    results = db.session.query(InventoryLog.user, db.func.sum(InventoryLog.quantity_used)) \
        .group_by(InventoryLog.user).all()
    return jsonify({user: qty for user, qty in results})


# Route: Usage Trends Over Time (line chart)
@app.route("/report/usage-trends-data")
@login_required
def usage_trends_data():
    logs = InventoryLog.query.order_by(InventoryLog.timestamp).all()
    trends = {}

    for log in logs:
        date = log.timestamp.strftime("%Y-%m-%d")
        item = log.item
        qty = log.quantity_used

        if item not in trends:
            trends[item] = {}
        if date not in trends[item]:
            trends[item][date] = 0
        trends[item][date] += qty

    return jsonify(trends)

#allowing input of new items
@app.route('/create_item', methods=['POST'])
@login_required
def create_item():
    if current_user.role != "Admin":
        flash("Unauthorized access", "danger")
        return redirect(url_for('index'))

    item_name = request.form.get('item')
    stock_amount = int(request.form.get('stock'))
    category = request.form.get('category')

    if item_name and category:
        new_item = Stock(item=item_name, stock=stock_amount, used=0, remaining=stock_amount, category=category)
        db.session.add(new_item)
        db.session.commit()
        flash(f"Item '{item_name}' added under '{category}'!", "success")
    else:
        flash("All fields are required", "warning")
    if stock_amount <0:
        return jsonify({"success": False, "message": "Stock must be at least 1."})

    return redirect(url_for('index'))



if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
