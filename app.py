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

# ------------------------------------------------------------------------------
# App & Database Configuration
# ------------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Configure SQLAlchemy to use SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------------------------------------------------------------------
# Flask-Login Setup
# ------------------------------------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"

# In-memory user data (for demonstration)
users = {
	"admin": {"password": "admin123", "role": "Admin"},
	"employee1": {"password": "password1", "role": "Employee"},
	"employee2": {"password": "password2", "role": "Employee"},
	"Constance": {"password": "Constance81","role": "Admin"}
}


class User(UserMixin):
	def __init__(self, username, role):
		self.id = username
		self.role = role


@login_manager.user_loader
def load_user(username):
	if username in users:
		return User(username, users[username]["role"])
	return None


# ------------------------------------------------------------------------------
# Database Models
# ------------------------------------------------------------------------------
class Stock(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	item = db.Column(db.String(64), unique=True, nullable=False)
	stock = db.Column(db.Integer, nullable=False)
	used = db.Column(db.Integer, default=0)
	remaining = db.Column(db.Integer, nullable=False)

	def __repr__(self):
		return f'<Stock {self.item}>'


class InventoryLog(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)
	user = db.Column(db.String(64), nullable=False)
	item = db.Column(db.String(64), nullable=False)
	quantity_used = db.Column(db.Integer, nullable=False)
	action = db.Column(db.String(128), nullable=False)

	def __repr__(self):
		return f'<InventoryLog {self.item} - {self.quantity_used}>'


# ------------------------------------------------------------------------------
# Data Migration Functions
# ------------------------------------------------------------------------------
def migrate_stock_data():
	"""Migrate stock data from stock_data.xlsx to the database."""
	if os.path.exists("stock_data.xlsx"):
		df = pd.read_excel("stock_data.xlsx")
		for _, row in df.iterrows():
			# Avoid duplicate entries if migration is run multiple times
			existing_item = Stock.query.filter_by(item=row["Item"]).first()
			if not existing_item:
				new_stock = Stock(
					item=row["Item"],
					stock=row["Stock"],
					used=row["Used"],
					remaining=row["Remaining"]
				)
				db.session.add(new_stock)
		db.session.commit()
		print("Stock data migration complete.")
	else:
		print("stock_data.xlsx not found.")


def migrate_inventory_logs():
	"""Migrate inventory log data from inventory_log.xlsx to the database."""
	if os.path.exists("inventory_log.xlsx"):
		df = pd.read_excel("inventory_log.xlsx")
		expected_columns = {"Timestamp", "User", "Item", "Quantity Used", "Action"}
		if not expected_columns.issubset(set(df.columns)):
			print("❌ ERROR: Missing required columns in inventory_log.xlsx")
			return
		for _, row in df.iterrows():
			try:
				timestamp = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")
			except Exception as e:
				print(f"Skipping row due to timestamp conversion error: {e}")
				continue

			new_log = InventoryLog(
				timestamp=timestamp,
				user=row["User"],
				item=row["Item"],
				quantity_used=row["Quantity Used"],
				action=row["Action"]
			)
			db.session.add(new_log)
		db.session.commit()
		print("Inventory log migration complete.")
	else:
		print("inventory_log.xlsx not found.")


def initialize_stock_db():
	"""If the Stock table is empty, initialize it with default items."""
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
		print("Initialized stock in DB.")


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
	# Ensure stock items are initialized.
	initialize_stock_db()
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

		if username in users and users[username]["password"] == password:
			user = User(username, users[username]["role"])
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


@app.route("/log", methods=["POST"])
@login_required
def log_usage():
	item_name = request.form.get("item")
	try:
		quantity_used = int(request.form.get("quantity"))
	except (TypeError, ValueError):
		return jsonify({"success": False, "message": "Invalid quantity."})

	user = current_user.id

	stock_item = Stock.query.filter_by(item=item_name).first()
	if stock_item:
		stock_item.used += quantity_used
		stock_item.remaining = stock_item.stock - stock_item.used

		new_log = InventoryLog(
			timestamp=datetime.now(),
			user=user,
			item=item_name,
			quantity_used=quantity_used,
			action="Usage Logged"
		)
		db.session.add(new_log)
		db.session.commit()

		return jsonify({"success": True, "message": f"{quantity_used} units of {item_name} logged by {user}."})
	else:
		return jsonify({"success": False, "message": f"Item '{item_name}' not found."})


@app.route("/add-item", methods=["POST"])
@login_required
def add_item():
	item_name = request.form.get("item")
	try:
		stock = int(request.form.get("stock"))
	except (TypeError, ValueError):
		return jsonify({"success": False, "message": "Invalid stock value."})

	if Stock.query.filter_by(item=item_name).first():
		return jsonify({"success": False, "message": f"Item '{item_name}' already exists."})

	new_item = Stock(
		item=item_name,
		stock=stock,
		used=0,
		remaining=stock
	)
	db.session.add(new_item)
	db.session.commit()
	return jsonify({"success": True, "message": f"Item '{item_name}' added with stock {stock}."})


@app.route("/export", methods=["GET"])
@login_required
def export_data():
	if current_user.role != "Admin":
		flash("You are not authorized to export data.", "danger")
		return redirect(url_for("index"))

	stocks = Stock.query.all()
	data = [
		{"Item": stock.item, "Stock": stock.stock, "Used": stock.used, "Remaining": stock.remaining}
		for stock in stocks
	]
	df = pd.DataFrame(data)
	file_path = "stock_data_export.xlsx"
	df.to_excel(file_path, index=False)
	return send_file(file_path, as_attachment=True)


@app.route("/download-log", methods=["GET"])
@login_required
def download_log():
	if current_user.role != "Admin":
		flash("You are not authorized to download the log.", "danger")
		return redirect(url_for("index"))

	logs = InventoryLog.query.all()
	data = [{
		"Timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
		"User": log.user,
		"Item": log.item,
		"Quantity Used": log.quantity_used,
		"Action": log.action
	} for log in logs]
	df = pd.DataFrame(data)
	file_path = "inventory_log_export.xlsx"
	df.to_excel(file_path, index=False)
	return send_file(file_path, as_attachment=True)


# ------------------ Reporting Endpoints ------------------

@app.route("/report/usage-trends", methods=["GET"])
@login_required
def usage_trends():
	"""Return item usage trends over time."""
	logs = InventoryLog.query.all()
	if not logs:
		return jsonify({})

	# Create a DataFrame from the logs
	data = [{
		"Timestamp": log.timestamp,
		"Item": log.item,
		"Quantity Used": log.quantity_used
	} for log in logs]
	df = pd.DataFrame(data)
	if not df.empty and {"Timestamp", "Item", "Quantity Used"}.issubset(df.columns):
		df["Timestamp"] = pd.to_datetime(df["Timestamp"])
		# Group by date and item, summing quantity used
		grouped = df.groupby([df["Timestamp"].dt.date, "Item"])["Quantity Used"].sum().unstack(fill_value=0)
		trends = grouped.transpose().to_dict()
		# Convert keys to strings for JSON compatibility
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
	df = pd.DataFrame(data)
	file_path = "most_used_report.xlsx"
	df.to_excel(file_path, index=False)
	return send_file(file_path, as_attachment=True)


@app.route("/report/employee-contributions", methods=["GET"])
@login_required
def employee_contributions_report():
	if current_user.role != "Admin":
		flash("You are not authorized to download this report.", "danger")
		return redirect(url_for("index"))

	logs = InventoryLog.query.all()
	data = [{
		"User": log.user,
		"Quantity Used": log.quantity_used
	} for log in logs]
	df = pd.DataFrame(data)
	if not df.empty:
		report_df = df.groupby("User")["Quantity Used"].sum().reset_index()
	else:
		report_df = pd.DataFrame(columns=["User", "Quantity Used"])
	file_path = "employee_contributions.xlsx"
	report_df.to_excel(file_path, index=False)
	return send_file(file_path, as_attachment=True)


@app.route("/report/most-used-data")
@login_required
def most_used_chart_data():
	"""Returns JSON data for most used items chart."""
	stocks = Stock.query.all()
	data = {stock.item: stock.used for stock in stocks}
	return jsonify(data)


@app.route("/report/employee-usage-data")
@login_required
def employee_usage_chart_data():
	"""Returns JSON data for employee contributions chart."""
	logs = InventoryLog.query.all()
	usage = {}
	for log in logs:
		usage[log.user] = usage.get(log.user, 0) + log.quantity_used
	return jsonify(usage)


@app.route("/report/usage-trends-data")
@login_required
def usage_trends_chart_data():
	"""Returns JSON data for usage trends per item over time."""
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

		# Uncomment the following lines if you need to migrate existing Excel data:
		# migrate_stock_data()
		# migrate_inventory_logs()
	port = int(os.environ.get("PORT", 5000))
	app.run(debug=True, host="0.0.0.0", port=port)
