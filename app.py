from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

#gen reports
def generate_most_used_report():
    """Generates the most used items report."""
    if os.path.exists("stock_data.xlsx"):
        df = pd.read_excel("stock_data.xlsx")
        if "Item" in df and "Used" in df:
            report_df = df[["Item", "Used"]].sort_values(by="Used", ascending=False)
            report_df.to_excel("most_used_report.xlsx", index=False)
        else:
            print("Error: Required columns missing in stock_data.xlsx")
    else:
        print("Error: stock_data.xlsx not found")

def generate_employee_report():
    """Generates the employee contribution report."""
    if os.path.exists("inventory_log.xlsx"):
        df = pd.read_excel("inventory_log.xlsx")
        if "User" in df and "Quantity Used" in df:
            report_df = df.groupby("User")["Quantity Used"].sum().reset_index()
            report_df.to_excel("employee_contributions.xlsx", index=False)
        else:
            print("Error: Required columns missing in inventory_log.xlsx")
    else:
        print("Error: inventory_log.xlsx not found")

# User model (in-memory for simplicity)
users = {
    "admin": {"password": "admin123", "role": "Admin"},
    "employee1": {"password": "password1", "role": "Employee"},
    "employee2": {"password": "password2", "role": "Employee"},
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

# File paths
STOCK_FILE = "stock_data.xlsx"
LOG_FILE = "inventory_log.xlsx"

# Initialize stock file
def initialize_stock():
    if not os.path.exists(STOCK_FILE):
        data = {
            "Item": ["Mop", "Bucket", "Detergent", "Gloves", "Sponges"],
            "Stock": [50, 30, 100, 200, 150],
            "Used": [0, 0, 0, 0, 0],
            "Remaining": [50, 30, 100, 200, 150],
        }
        df = pd.DataFrame(data)
        df.to_excel(STOCK_FILE, index=False)

# Append inventory changes to the log
def log_change(item_name, quantity_used, user):
    if not os.path.exists(LOG_FILE):
        log_df = pd.DataFrame(columns=["Timestamp", "User", "Item", "Quantity Used", "Action"])
        log_df.to_excel(LOG_FILE, index=False)

    log_entry = pd.DataFrame([{
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "User": user,
        "Item": item_name,
        "Quantity Used": quantity_used,
        "Action": "Usage Logged",
    }])

    log_df = pd.read_excel(LOG_FILE)
    log_df = pd.concat([log_df, log_entry], ignore_index=True)
    log_df.to_excel(LOG_FILE, index=False)

# Routes
@app.route("/")
@login_required
def index():
    initialize_stock()
    df = pd.read_excel(STOCK_FILE)
    return render_template("index.html", data=df.to_dict(orient="records"), role=current_user.role)

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
    quantity_used = int(request.form.get("quantity"))
    user = current_user.id

    if os.path.exists(STOCK_FILE):
        df = pd.read_excel(STOCK_FILE)
        if item_name in df["Item"].values:
            df.loc[df["Item"] == item_name, "Used"] += quantity_used
            df["Remaining"] = df["Stock"] - df["Used"]
            df.to_excel(STOCK_FILE, index=False)
            log_change(item_name, quantity_used, user)
            return jsonify({"success": True, "message": f"{quantity_used} units of {item_name} logged by {user}."})
        else:
            return jsonify({"success": False, "message": f"Item '{item_name}' not found."})
    return jsonify({"success": False, "message": "Stock file not found."})

@app.route("/add-item", methods=["POST"])
@login_required
def add_item():
    item_name = request.form.get("item")
    stock = int(request.form.get("stock"))

    if os.path.exists(STOCK_FILE):
        df = pd.read_excel(STOCK_FILE)
        if item_name in df["Item"].values:
            return jsonify({"success": False, "message": f"Item '{item_name}' already exists."})
        new_item = pd.DataFrame([{
            "Item": item_name,
            "Stock": stock,
            "Used": 0,
            "Remaining": stock
        }])
        df = pd.concat([df, new_item], ignore_index=True)
        df.to_excel(STOCK_FILE, index=False)
        return jsonify({"success": True, "message": f"Item '{item_name}' added with stock {stock}."})
    return jsonify({"success": False, "message": "Stock file not found."})

@app.route("/export", methods=["GET"])
@login_required
def export_data():
    if current_user.role != "Admin":
        flash("You are not authorized to export data.", "danger")
        return redirect(url_for("index"))

    if os.path.exists("stock_data.xlsx"):
        return send_file(STOCK_FILE, as_attachment=True)

    flash("Stock file not found.", "danger")
    return redirect(url_for("index"))


@app.route("/download-log", methods=["GET"])
@login_required
def download_log():
    if current_user.role != "Admin":
        flash("You are not authorized to download the log.", "danger")
        return redirect(url_for("index"))

    if os.path.exists("inventory_log.xlsx"):
        return send_file("inventory_log.xlsx", as_attachment=True)

    flash("Log file not found.", "danger")
    return redirect(url_for("index"))



@app.route("/report/usage-trends", methods=["GET"])
@login_required
def usage_trends():
    """Return item usage trends over time."""
    try:
        if os.path.exists(LOG_FILE):
            log_df = pd.read_excel(LOG_FILE)

            # Ensure LOG_FILE is not empty and contains required columns
            if not log_df.empty and "Timestamp" in log_df.columns and "Item" in log_df.columns and "Quantity Used" in log_df.columns:
                # Convert Timestamp to datetime and ensure valid format
                log_df["Timestamp"] = pd.to_datetime(log_df["Timestamp"], errors='coerce')
                log_df = log_df.dropna(subset=["Timestamp"])  # Drop rows with invalid timestamps

                # Group by date and item, summing up the quantity used
                grouped = log_df.groupby([log_df["Timestamp"].dt.date, "Item"])["Quantity Used"].sum().unstack(fill_value=0)

                # Convert the grouped DataFrame to a dictionary with string dates as keys
                trends = grouped.transpose().to_dict()
                trends_str_keys = {str(k): v for k, v in trends.items()}

                return jsonify(trends_str_keys)  # Return trends as JSON with string keys
            else:
                return jsonify({})  # Return empty JSON if columns are missing
        return jsonify({})
    except Exception as e:
        print(f"Error in /report/usage-trends: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/report/most-used", methods=["GET"])
@login_required
def most_used_report():
    if current_user.role != "Admin":
        flash("You are not authorized to download this report.", "danger")
        return redirect(url_for("index"))

    generate_most_used_report()  # Ensure the report is generated before sending

    if os.path.exists("most_used_report.xlsx"):
        return send_file("most_used_report.xlsx", as_attachment=True)

    flash("Report not found.", "danger")
    return redirect(url_for("index"))



@app.route("/report/employee-contributions", methods=["GET"])
@login_required
def employee_contributions_report():
    if current_user.role != "Admin":
        flash("You are not authorized to download this report.", "danger")
        return redirect(url_for("index"))

    generate_employee_report()  # Ensure the report is generated before sending

    if os.path.exists("employee_contributions.xlsx"):
        return send_file("employee_contributions.xlsx", as_attachment=True)

    flash("Report not found.", "danger")
    return redirect(url_for("index"))

@app.route("/report/most-used-data")
@login_required
def most_used_chart_data():
    """Returns JSON data for most used items chart."""
    if os.path.exists("stock_data.xlsx"):
        df = pd.read_excel("stock_data.xlsx")
        if "Item" in df and "Used" in df:
            report_df = df[["Item", "Used"]].sort_values(by="Used", ascending=False)
            data = report_df.set_index("Item")["Used"].to_dict()
            return jsonify(data)
    return jsonify({})

@app.route("/report/employee-usage-data")
@login_required
def employee_usage_chart_data():
    """Returns JSON data for employee contributions chart."""
    if os.path.exists("inventory_log.xlsx"):
        df = pd.read_excel("inventory_log.xlsx")
        if "User" in df and "Quantity Used" in df:
            report_df = df.groupby("User")["Quantity Used"].sum().reset_index()
            data = report_df.set_index("User")["Quantity Used"].to_dict()
            return jsonify(data)
    return jsonify({})

@app.route("/report/usage-trends-data")
@login_required
def usage_trends_chart_data():
    """Returns JSON data for usage trends per item over time."""
    if os.path.exists("inventory_log.xlsx"):
        df = pd.read_excel("inventory_log.xlsx")

        if "Date" not in df or "Item" not in df or "Quantity Used" not in df:
            print("❌ ERROR: Missing required columns in inventory_log.xlsx")
            return jsonify({"error": "Missing required columns in inventory_log.xlsx", "columns_found": df.columns.tolist()})

        # Ensure Date is formatted correctly
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])

        if df.empty:
            print("❌ ERROR: No valid data after processing.")
            return jsonify({"error": "No valid data in log."})

        # Group by Date and Item, summing Quantity Used
        report_df = df.groupby([df["Date"].dt.strftime("%Y-%m-%d"), "Item"])["Quantity Used"].sum().reset_index()

        # Convert DataFrame into a dictionary of item-wise usage trends
        data = {}
        for item in report_df["Item"].unique():
            item_df = report_df[report_df["Item"] == item]
            data[item] = dict(zip(item_df["Date"], item_df["Quantity Used"]))

        print("✅ Processed Data:", data)  # Debugging output
        return jsonify(data)

    print("❌ ERROR: inventory_log.xlsx not found")
    return jsonify({"error": "inventory_log.xlsx not found"})





if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
