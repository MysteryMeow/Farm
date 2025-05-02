from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)

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
    """Append inventory changes to a log file."""
    if not os.path.exists(LOG_FILE):
        # Create an empty log file with the correct columns if it doesn't exist
        log_df = pd.DataFrame(columns=["Timestamp", "User", "Item", "Quantity Used", "Action"])
        log_df.to_excel(LOG_FILE, index=False)

    # Prepare the log entry as a DataFrame
    log_entry = pd.DataFrame([{
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "User": user,
        "Item": item_name,
        "Quantity Used": quantity_used,
        "Action": "Usage Logged",
    }])

    # Read the existing log file
    log_df = pd.read_excel(LOG_FILE)

    # Append the new log entry using pd.concat
    log_df = pd.concat([log_df, log_entry], ignore_index=True)

    # Save the updated log back to the file
    log_df.to_excel(LOG_FILE, index=False)

@app.route("/")
def index():
    initialize_stock()
    df = pd.read_excel(STOCK_FILE)
    return render_template("index.html", data=df.to_dict(orient="records"))

@app.route("/log", methods=["POST"])
def log_usage():
    """Log item usage and update the stock file."""
    item_name = request.form.get("item")
    quantity_used = int(request.form.get("quantity"))
    user = request.form.get("user", "Unknown User")

    if os.path.exists(STOCK_FILE):
        df = pd.read_excel(STOCK_FILE)
        if item_name in df["Item"].values:
            # Update stock
            df.loc[df["Item"] == item_name, "Used"] += quantity_used
            df["Remaining"] = df["Stock"] - df["Used"]
            df.to_excel(STOCK_FILE, index=False)

            # Log the change
            log_change(item_name, quantity_used, user)

            return jsonify({"success": True, "message": f"{quantity_used} units of {item_name} logged by {user}."})
        else:
            return jsonify({"success": False, "message": f"Item '{item_name}' not found."})
    return jsonify({"success": False, "message": "Stock file not found."})

@app.route("/export", methods=["GET"])
def export_data():
    if os.path.exists(STOCK_FILE):
        return send_file(STOCK_FILE, as_attachment=True)
    return jsonify({"success": False, "message": "Stock file not found."})

@app.route("/download-log", methods=["GET"])
def download_log():
    if os.path.exists(LOG_FILE):
        return send_file(LOG_FILE, as_attachment=True)
    return jsonify({"success": False, "message": "Log file not found."})

@app.route("/report/most-used", methods=["GET"])
def most_used_items():
    if os.path.exists(LOG_FILE):
        log_df = pd.read_excel(LOG_FILE)
        if "Quantity Used" in log_df.columns:
            report = log_df.groupby("Item")["Quantity Used"].sum().sort_values(ascending=False)
            return jsonify(report.to_dict())
    return jsonify({"success": False, "message": "Log file not found."})

@app.route("/report/usage-trends", methods=["GET"])
def usage_trends():
    """Generate trends for all items over time."""
    if os.path.exists(LOG_FILE):
        log_df = pd.read_excel(LOG_FILE)
        log_df["Timestamp"] = pd.to_datetime(log_df["Timestamp"])
        trends = log_df.groupby([log_df["Timestamp"].dt.date, "Item"])["Quantity Used"].sum().unstack(fill_value=0)
        trends.index = trends.index.astype(str)  # Convert dates to strings for JSON
        return jsonify(trends.to_dict(orient="index"))
    return jsonify({"success": False, "message": "Log file not found."})

@app.route("/report/employee-contributions", methods=["GET"])
def employee_contributions():
    """Generate a report of usage by employee."""
    if os.path.exists(LOG_FILE):
        log_df = pd.read_excel(LOG_FILE)
        contributions = log_df.groupby("User")["Quantity Used"].sum().sort_values(ascending=False)
        return jsonify(contributions.to_dict())
    return jsonify({"success": False, "message": "Log file not found."})

if __name__ == "__main__":
    # Use the PORT environment variable or default to 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
