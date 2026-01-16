import os
import sys
import shutil
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, redirect, url_for
from flask_cors import CORS
from sqlalchemy import inspect, text
from src.models.user import db
from src.routes.user import user_bp
from src.routes.vendor import vendor_bp
from src.routes.admin import admin_bp

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# Enable CORS for all routes
CORS(app)

app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(vendor_bp, url_prefix='/api')
app.register_blueprint(admin_bp, url_prefix='/api')

# Root route - redirect to entry page
@app.route('/')
def index():
    return redirect('/entry.html')

# Entry page route
@app.route('/entry')
def entry():
    return send_from_directory(app.static_folder, 'entry.html')

# Database configuration for Render
database_url = os.getenv('DATABASE_URL')
if database_url:
    # Production: Use PostgreSQL from Render
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Check if persistent disk should be used (based on env variable)
    use_persistent_disk = os.getenv('USE_PERSISTENT_DISK', 'false').lower() == 'true'

    if use_persistent_disk and os.path.exists('/data'):
        db_path = '/data/app.db'
        if not os.path.exists(db_path):
            import shutil
            clean_db_path = os.path.join(os.path.dirname(__file__), '..', 'cleandb', 'database', 'app.db')
            if os.path.exists(clean_db_path):
                shutil.copyfile(clean_db_path, db_path)
        app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
    else:
        # Windows-compatible fallback
        import tempfile
        temp_dir = tempfile.gettempdir()
        fallback_db_path = os.path.join(temp_dir, 'app.db')
        clean_db_path = os.path.join(os.path.dirname(__file__), '..', 'cleandb', 'database', 'app.db')
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(fallback_db_path), exist_ok=True)
        
        if not os.path.exists(fallback_db_path):
            if os.path.exists(clean_db_path):
                shutil.copyfile(clean_db_path, fallback_db_path)
                print(f"Copied template DB from {clean_db_path} to {fallback_db_path}")
        app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{fallback_db_path}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

    def ensure_schema():
        inspector = inspect(db.engine)
        with db.engine.begin() as connection:
            if inspector.has_table('invoices'):
                invoice_columns = {col['name'] for col in inspector.get_columns('invoices')}
                if 'contains_content_anomaly' not in invoice_columns:
                    connection.execute(text("ALTER TABLE invoices ADD COLUMN contains_content_anomaly BOOLEAN DEFAULT 0"))
                if 'scenario_marker_set' not in invoice_columns:
                    connection.execute(text("ALTER TABLE invoices ADD COLUMN scenario_marker_set BOOLEAN DEFAULT 0"))
            if inspector.has_table('finbot_config'):
                config_columns = {col['name'] for col in inspector.get_columns('finbot_config')}
                if 'integrity_checks_enabled' not in config_columns:
                    connection.execute(text("ALTER TABLE finbot_config ADD COLUMN integrity_checks_enabled BOOLEAN DEFAULT 1"))

    ensure_schema()
    
    # Initialize default config if not exists
    from src.models.vendor import FinBotConfig
    if not FinBotConfig.query.first():
        default_config = FinBotConfig(
            auto_approve_threshold=1000.00,
            manual_review_threshold=5000.00,
            speed_priority=0.7,
            integrity_checks_enabled=True
        )
        db.session.add(default_config)
        db.session.commit()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    # Use PORT environment variable for Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

