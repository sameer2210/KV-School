"""
PM SHRI Kendriya Vidyalaya - Flask Application Factory
"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

from app.config import Config

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()

# Configure login manager
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    """Application factory pattern"""
    instance_path = getattr(config_class, 'INSTANCE_PATH', None)
    if instance_path:
        app = Flask(__name__, instance_path=instance_path)
    else:
        app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.student import student_bp
    from app.routes.attendance import attendance_bp
    from app.routes.fee import fee_bp
    from app.routes.announcement import announcement_bp
    from app.routes.portal import portal_bp
    from app.routes.chat import chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(fee_bp)
    app.register_blueprint(announcement_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(chat_bp)

    # Create database tables and seed data
    with app.app_context():
        try:
            db.create_all()
            ensure_schema_upgrades()
            seed_database()
        except Exception as e:
            app.logger.warning(f"Database auto-setup deferred or failed: {e}")

    return app


def ensure_schema_upgrades():
    """
    Ensure newly added columns and tables exist in the database,
    preserving existing data across both SQLite and PostgreSQL.
    """
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        # 1. fee_structures new columns:
        if 'fee_structures' in table_names:
            cols = [c['name'] for c in inspector.get_columns('fee_structures')]
            with db.engine.connect() as conn:
                if 'batch_id' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN batch_id INTEGER"))
                if 'academic_session' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN academic_session VARCHAR(20)"))
                if 'fee_component' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN fee_component VARCHAR(50)"))
                if 'quarter' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN quarter VARCHAR(10)"))
                if 'frequency' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN frequency VARCHAR(20)"))
                if 'description' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN description TEXT"))
                if 'is_active' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                if 'created_at' not in cols:
                    conn.execute(text("ALTER TABLE fee_structures ADD COLUMN created_at TIMESTAMP"))
                conn.commit()

        # 2. fee_dues new columns:
        if 'fee_dues' in table_names:
            cols = [c['name'] for c in inspector.get_columns('fee_dues')]
            with db.engine.connect() as conn:
                if 'fee_structure_id' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN fee_structure_id INTEGER REFERENCES fee_structures(id)"))
                if 'academic_session' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN academic_session VARCHAR(20)"))
                if 'quarter' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN quarter VARCHAR(10)"))
                if 'fee_component' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN fee_component VARCHAR(50)"))
                if 'month_for' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN month_for VARCHAR(20)"))
                if 'discount_amount' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN discount_amount NUMERIC(10, 2) DEFAULT 0"))
                if 'fine_amount' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN fine_amount NUMERIC(10, 2) DEFAULT 0"))
                if 'created_at' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN created_at TIMESTAMP"))
                if 'updated_at' not in cols:
                    conn.execute(text("ALTER TABLE fee_dues ADD COLUMN updated_at TIMESTAMP"))
                conn.commit()

        # 3. fee_transactions new columns:
        if 'fee_transactions' in table_names:
            cols = [c['name'] for c in inspector.get_columns('fee_transactions')]
            with db.engine.connect() as conn:
                if 'fee_structure_id' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN fee_structure_id INTEGER REFERENCES fee_structures(id)"))
                if 'transaction_id' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN transaction_id VARCHAR(100)"))
                if 'cheque_number' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN cheque_number VARCHAR(50)"))
                if 'cheque_date' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN cheque_date DATE"))
                if 'bank_name' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN bank_name VARCHAR(100)"))
                if 'description' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN description TEXT"))
                if 'month_for' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN month_for VARCHAR(20)"))
                if 'academic_session' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN academic_session VARCHAR(20)"))
                if 'quarter' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN quarter VARCHAR(10)"))
                if 'fee_component' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN fee_component VARCHAR(50)"))
                if 'discount' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN discount NUMERIC(10, 2) DEFAULT 0"))
                if 'fine' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN fine NUMERIC(10, 2) DEFAULT 0"))
                if 'remarks' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN remarks TEXT"))
                if 'collected_by' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN collected_by INTEGER REFERENCES users(id)"))
                if 'status' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN status VARCHAR(20) DEFAULT 'SUCCESS'"))
                if 'reversal_reason' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN reversal_reason VARCHAR(255)"))
                if 'reversed_at' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN reversed_at TIMESTAMP"))
                if 'reversed_by' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN reversed_by INTEGER REFERENCES users(id)"))
                if 'created_at' not in cols:
                    conn.execute(text("ALTER TABLE fee_transactions ADD COLUMN created_at TIMESTAMP"))
                conn.commit()
    except Exception as e:
        # Schema upgrade check completed or not needed
        pass


def seed_database():
    """Seed initial data if database is empty"""
    from app.models import User, Batch
    from flask import current_app

    # Get admin credentials from config (environment variables)
    admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@sarvagyaan.com')
    admin_password = current_app.config.get('ADMIN_PASSWORD', 'changeme123')

    # Check if admin exists
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        # Create admin user
        admin = User(
            username='Admin',
            email=admin_email,
            role='ADMIN',
            is_active=True
        )
        admin.set_password(admin_password)
        db.session.add(admin)

        # Create sample batches
        batches = [
            Batch(name='Class 10-A', class_name='Class 10', capacity=30, is_active=True),
            Batch(name='Class 10-B', class_name='Class 10', capacity=30, is_active=True),
            Batch(name='Class 11-Science', class_name='Class 11', capacity=25, is_active=True),
            Batch(name='Class 11-Commerce', class_name='Class 11', capacity=25, is_active=True),
            Batch(name='Class 12-Science', class_name='Class 12', capacity=25, is_active=True),
        ]
        for batch in batches:
            db.session.add(batch)

        db.session.commit()
        print("[OK] Initial database configuration ready")
