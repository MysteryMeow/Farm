import os
from datetime import datetime
import pandas as pd

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
    def is_accessible(self):
        # Only allow access if the user is logged in and is an Admin.
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
    # Initialize stock in the database if none exists.
    if Stock.query.count() == 0:
        data = {
            "Item": ["Mop", "Bucket", "Detergent", "Gloves", "Sponges"],
            "Stock": [50, 30, 100, 200, 150],
            "Used": [0, 0, 0, 0, 0],
            "Remaining": [50, 30, 100, 200, 150],
        }
        df = pd.DataFrame(data)
        for _, row in df.iterrows():
            new_stock = Stock(
                item=row["Item"],
                stock=row["Stock"],
                used=row["Used"],
                remaining=row["Remaining"]
            )
            db.session.add(new_stock)
        db.session.commit()
    stocks = Stock.query.all()
    data = [
        {"Item": stock.item, "Stock": stock.stock, "Used": stock.used, "Remaining": stock.remaining}
        for stock in stocks
    ]
    return render_template("index.html", data=data, role=current_user.role)

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
    # Only Admins can register new users.
    if current_user.role != "Admin":
        flash("You are not authorized to add new users.", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role", "Employee")  # default role is Employee
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
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid quantity."})
    stock_item = Stock.query.filter_by(item=item_name).first()
    if stock_item:
        stock_item.used += quantity_used
        stock_item.remaining = stock_item.stock - stock_item.used
        new_log = InventoryLog(
            timestamp=datetime.now(),
            user=current_user.username,
            item=item_name,
            quantity_used=quantity_used,
            action="Usage Logged"
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify({"success": True, "message": f"{quantity_used} units of {item_name} logged by {current_user.username}."})
    else:
        return jsonify({"success": False, "message": f"Item '{item_name}' not found."})

@app.route("/add-item", methods=["POST"])
@login_required
def add_item():
    item_name = request.form.get("item")
    try:
        stock_val = int(request.form.get("stock"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid stock value."})
    if Stock.query.filter_by(item=item_name).first():
        return jsonify({"success": False, "message": f"Item '{item_name}' already exists."})
    new_item = Stock(
        item=item_name,
        stock=stock_val,
        used=0,
        remaining=stock_val
    )
    db.session.add(new_item)
    db.session.commit()
    return jsonify({"success": True, "message": f"Item '{item_name}' added with stock {stock_val}."})

@app.route("/export", methods=["GET"])
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

@app.route("/download-log", methods=["GET"])
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

@app.route("/report/usage-trends", methods=["GET"])
@login_required
def usage_trends():
    logs = InventoryLog.query.all()
    if not logs:
        return jsonify({})
    data = [{
        "Timestamp": log.timestamp,
        "Item": log.item,
        "Quantity Used": log.quantity_used
    } for log in logs]
    df = pd.DataFrame(data)
    if not df.empty and {"Timestamp", "Item", "Quantity Used"}.issubset(df.columns):
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        grouped = df.groupby([df["Timestamp"].dt.date, "Item"])["Quantity Used"].sum().unstack(fill_value=0)
        trends = grouped.transpose().to_dict()
        trends_str_keys = {str(k): v for k, v in trends.items()}
        return jsonify(trends_str_keys)
    else:
        return jsonify({})

@app.route("/report/most-used", methods=["GET"])
@login_required
def most_used_report():
    if current_user.role != "Admin":
        flash("You are not authorized to download this report.", "danger")
        return redirect(url_for("index"))
    stocks = Stock.query.order_by(Stock.used.desc()).all()
    data = [{"Item": stock.item, "Used": stock.used} for stock in stocks]
    return jsonify(data)

@app.route("/report/employee-contributions", methods=["GET"])
@login_required
def employee_contributions_report():
    if current_user.role != "Admin":
        flash("You are not authorized to download this report.", "danger")
        return redirect(url_for("index"))
    logs = InventoryLog.query.all()
    data = [{"User": log.user, "Quantity Used": log.quantity_used} for log in logs]
    df = pd.DataFrame(data)
    if not df.empty:
        report_df = df.groupby("User")["Quantity Used"].sum().reset_index()
    else:
        report_df = pd.DataFrame(columns=["User", "Quantity Used"])
    return jsonify(report_df.to_dict(orient="records"))

@app.route("/report/most-used-data")
@login_required
def most_used_chart_data():
    stocks = Stock.query.all()
    data = {stock.item: stock.used for stock in stocks}
    return jsonify(data)

@app.route("/report/employee-usage-data")
@login_required
def employee_usage_chart_data():
    logs = InventoryLog.query.all()
    usage = {}
    for log in logs:
        usage[log.user] = usage.get(log.user, 0) + log.quantity_used
    return jsonify(usage)

@app.route("/report/usage-trends-data")
@login_required
def usage_trends_chart_data():
    logs = InventoryLog.query.all()
    if not logs:
        return jsonify({"error": "No log data found."})
    data = [{
        "Date": log.timestamp.strftime("%Y-%m-%d"),
        "Item": log.item,
        "Quantity Used": log.quantity_used
    } for log in logs]
    df = pd.DataFrame(data)
    if "Date" not in df or "Item" not in df or "Quantity Used" not in df:
        return jsonify({"error": "Missing required data in log."})
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.dropna(subset=["Date"])
    report_df = df.groupby([df["Date"].dt.strftime("%Y-%m-%d"), "Item"])["Quantity Used"].sum().reset_index()
    chart_data = {}
    for item in report_df["Item"].unique():
        item_df = report_df[report_df["Item"] == item]
        chart_data[item] = dict(zip(item_df["Date"], item_df["Quantity Used"]))
    return jsonify(chart_data)

# ------------------------------------------------------------------------------
# Main Block
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
