import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate, upgrade
from flask import jsonify
from sqlalchemy import func
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
    plot_number = db.Column(db.String(50), unique=True)
    crop = db.Column(db.String(100))
    status = db.Column(db.String(100))

    # ✅ New fields for grid placement
    row = db.Column(db.Integer)
    col = db.Column(db.Integer)

    def __repr__(self):
        return f"<Plot {self.plot_number} [{self.row}, {self.col}] - {self.status}>"



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
@app.route("/inventory")
@login_required
def inventory():
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
    return render_template("inventory.html", grouped_items=grouped_items, user_role=current_user.role)

@app.route('/create_item', methods=['POST'])
@login_required
def create_item():
    item_name = request.form.get('item')
    category = request.form.get('category')
    try:
        stock_amount = int(request.form.get('stock'))
        if stock_amount < 1:
            flash("Stock amount must be at least 1.", "warning")
            return redirect(url_for('index'))
    except (TypeError, ValueError):
        flash("Invalid stock amount.", "warning")
        return redirect(url_for('index'))

    if item_name and category:
        existing_item = Stock.query.filter_by(item=item_name).first()
        if existing_item:
            flash(f"Item '{item_name}' already exists in the system!", "warning")
            return redirect(url_for('index'))

        new_item = Stock(
            item=item_name,
            stock=stock_amount,
            used=0,
            category=category
        )

        try:
            db.session.add(new_item)
            db.session.commit()
            log = InventoryLog(
                timestamp=datetime.now(),
                user=current_user.username,
                item=item_name,
                quantity_used=stock_amount,
                action="Item Created"
            )
            db.session.add(log)
            db.session.commit()
            flash(f"Item '{item_name}' added under '{category}' by {current_user.username}!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for('index'))
    else:
        flash("All fields are required", "warning")

    return redirect(url_for('index'))

@app.route("/")
@login_required
def index():
    return render_template("index.html", user_role=current_user.role)

@app.route("/silly")
@login_required
def silly():
    return render_template("silly.html", user_role=current_user.role)
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

@app.route("/lists")
@login_required
def lists():
    stocks = Stock.query.order_by(Stock.category.asc(), Stock.item.asc()).all()
    grouped_items = {}
    for stock in stocks:
        grouped_items.setdefault(stock.category, []).append(stock)
    return render_template("lists.html", grouped_items=grouped_items, user_role=current_user.role)
@app.route("/charts")
@login_required
def charts():
    return render_template("charts.html", user_role=current_user.role)
# API route to get items by category
@app.route("/api/items/<category>")
@login_required
def get_items_by_category(category):
    items = Stock.query.filter_by(category=category).all()
    return jsonify([{
        "item": item.item,
        "stock": item.stock,
        "used": item.used,
        "remaining": item.remaining
    } for item in items])

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
    if not stock_item:
        return jsonify({"success": False, "message": f"Item '{item_name}' not found."})

    if quantity_used > stock_item.remaining:
        return jsonify({"success": False, "message": f"Not enough stock for {item_name}."})

    stock_item.used += quantity_used

    new_log = InventoryLog(
        timestamp=datetime.now(),
        user=current_user.username,
        item=item_name,
        quantity_used=quantity_used,
        action="Usage Logged"
    )
    db.session.add(new_log)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"{quantity_used} units of {item_name} used by {current_user.username}."
    })

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
    if not stock_item:
        return jsonify({
            "success": False,
            "message": f"Item '{item_name}' not found in stock. Cannot restock non-existing item."
        })

    stock_item.stock += stock_val

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



@app.route("/report/most-used-data")
@login_required
def most_used_data():
    data = (
        db.session.query(Stock.item, Stock.used)
        .filter(Stock.used > 0)
        .order_by(Stock.used.desc())
        .limit(10)
        .all()
    )
    return jsonify({item: used for item, used in data})
@app.route("/report/employee-usage-data")
@login_required
def employee_usage_data():
    data = (
        db.session.query(InventoryLog.user, func.sum(InventoryLog.quantity_used))
        .group_by(InventoryLog.user)
        .all()
    )
    return jsonify({employee: total for employee, total in data})

@app.route("/report/usage-trends-data")
@login_required
def usage_trends_data():
    data = (
        db.session.query(InventoryLog.item, func.strftime('%Y-%m-%d', InventoryLog.timestamp), func.sum(InventoryLog.quantity_used))
        .group_by(InventoryLog.item, func.strftime('%Y-%m-%d', InventoryLog.timestamp))
        .order_by(func.strftime('%Y-%m-%d', InventoryLog.timestamp))
        .all()
    )

    result = {}
    for item, date, total in data:
        if item not in result:
            result[item] = {}
        result[item][date] = total

    return jsonify(result)
@app.route("/update-plot/<int:plot_id>", methods=["POST"])
@login_required
def update_plot(plot_id):
    data = request.get_json()
    crop = data.get("crop", "").strip()
    status = data.get("status", "").strip()

    if not status:
        return jsonify({"success": False, "message": "Status is required."})

    plot = Plot.query.get(plot_id)
    if not plot:
        return jsonify({"success": False, "message": f"Plot #{plot_id} not found."})

    plot.crop = crop if crop else None
    plot.status = status

    try:
        db.session.commit()
        return jsonify({"success": True, "message": f"Plot #{plot_id} updated."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error: {str(e)}"})
from random import choice

@app.route("/admin/plot-manager")
@login_required
def plot_manager():
    if current_user.role != "Admin":
        return "Unauthorized", 403
    return render_template("plot_manager.html")

@app.route("/admin/add-plots", methods=["POST"])
@login_required
def add_plots():
    if current_user.role != "Admin":
        return "Unauthorized", 403

    start = int(request.form.get("start", 0))
    end = int(request.form.get("end", 0))

    for i in range(start, end + 1):
        if not Plot.query.filter_by(plot_number=i).first():
            db.session.add(Plot(plot_number=i))
    db.session.commit()
    flash(f"Added plots {start} to {end}", "success")
    return redirect(url_for("plot_manager"))

@app.route("/admin/reset-plots", methods=["POST"])
@login_required
def reset_plots():
    if current_user.role != "Admin":
        return "Unauthorized", 403
    db.session.query(Plot).delete()
    db.session.commit()
    flash("All plots deleted!", "danger")
    return redirect(url_for("plot_manager"))

@app.route("/admin/randomize-plots", methods=["POST"])
@login_required
def randomize_plots():
    if current_user.role != "Admin":
        return "Unauthorized", 403

    crops = ["Corn", "Tomato", "Carrot", "Pumpkin", "Sunflower", "Beans", "Lettuce", "Wheat"]
    statuses = ["Planted", "Needs Water", "Harvest Ready", "Empty"]

    plots = Plot.query.all()
    for plot in plots:
        plot.crop = choice(crops)
        plot.status = choice(statuses)
    db.session.commit()
    flash("All plots randomized!", "info")
    return redirect(url_for("plot_manager"))

@app.route('/add-plot', methods=['POST'])
def add_plot():
    data = request.get_json()
    try:
        row = int(data.get('row'))
        col = int(data.get('col'))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Invalid row or col"), 400

    crop = data.get('crop', '')
    status = data.get('status', 'Empty')

    # Prevent duplicates
    if Plot.query.filter_by(row=row, col=col).first():
        return jsonify(success=False, message="Plot already exists at that location"), 400

    new_plot = Plot(
        plot_number=f"{row}-{col}",
        crop=crop,
        status=status,
        row=row,
        col=col
    )

    db.session.add(new_plot)
    db.session.commit()

    return jsonify(success=True)

@app.route('/move-plot/<int:plot_id>', methods=['POST'])
def move_plot(plot_id):
    data = request.get_json()
    row = int(data.get('row'))
    col = int(data.get('col'))

    existing = Plot.query.filter_by(row=row, col=col).first()
    if existing:
        return jsonify(success=False, message="Target position already occupied"), 400

    plot = Plot.query.get(plot_id)
    if plot:
        plot.row = row
        plot.col = col
        plot.plot_number = f"{row}-{col}"
        db.session.commit()
        return jsonify(success=True)
    else:
        return jsonify(success=False, message="Plot not found"), 404

