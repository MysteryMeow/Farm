from flask_migrate import Migrate
from app import app, db
from app import User
migrate = Migrate(app, db)
from app import db, Plot

# Create 100 plots if they don't already exist
for i in range(1, 101):
    if not Plot.query.filter_by(plot_number=i).first():
        plot = Plot(plot_number=i, crop=None, status='Empty')
        db.session.add(plot)
db.session.commit()
if __name__ == '__main__':
    app.run()