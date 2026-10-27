"""
Application Configuration
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# Load environment variables from .env file
load_dotenv(os.path.join(basedir, '.env'))

# Ensure instance directory exists
instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)


def get_database_url():
    """Get database URL with Supabase compatibility fix and safe SQLite fallback"""
    if os.environ.get('USE_SQLITE', '').lower() in ['1', 'true', 'yes']:
        return 'sqlite:///' + os.path.join(basedir, 'instance', 'sarva_gyaan.db')

    url = os.environ.get('DATABASE_URL')
    if url:
        # Check if URL contains placeholder tokens from .env.example
        placeholders = ['[YOUR-PASSWORD]', '[YOUR-PROJECT-REF]', 'localhost:5432/postgres']
        if any(p in url for p in placeholders):
            # Placeholder URL detected; fallback to SQLite
            return 'sqlite:///' + os.path.join(basedir, 'instance', 'sarva_gyaan.db')

        # Supabase uses 'postgres://' but SQLAlchemy requires 'postgresql://'
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql://', 1)
        return url
    # Fallback to SQLite for local development
    return 'sqlite:///' + os.path.join(basedir, 'instance', 'sarva_gyaan.db')


class Config:
    """Base configuration"""
    # Secret key for session management
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sarva-gyaan-academy-secret-key-2024'

    # Database configuration
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Upload configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    UPLOAD_FOLDER = os.path.join(os.path.dirname(basedir), 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'csv', 'xlsx'}

    # Pagination
    ITEMS_PER_PAGE = 20

    # Application settings & School Profile
    APP_NAME = 'PM SHRI Kendriya Vidyalaya'
    SCHOOL_NAME = os.environ.get('SCHOOL_NAME', 'PM SHRI Kendriya Vidyalaya')
    SCHOOL_TAGLINE = os.environ.get('SCHOOL_TAGLINE', 'Empowering Minds, Inspiring Futures')
    SCHOOL_ADDRESS = os.environ.get('SCHOOL_ADDRESS', 'Ordnance Factory Estate, Itarsi')
    SCHOOL_PHONE = os.environ.get('SCHOOL_PHONE', '+91 98765 43210')
    SCHOOL_EMAIL = os.environ.get('SCHOOL_EMAIL', 'admin@amrita.com')
    SCHOOL_AFFILIATION = os.environ.get('SCHOOL_AFFILIATION', 'CBSE / SGA-2024-889')

    TIMEZONE = 'Asia/Kolkata'
    CURRENCY = '₹'
    DATE_FORMAT = '%d-%m-%Y'
    DATETIME_FORMAT = '%d-%m-%Y %H:%M'

    # Admin credentials from environment (only for initial local setup)
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@sarvagyaan.com')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme123')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True

    INSECURE_SECRETS = {
        'sarva-gyaan-academy-secret-key-2024',
        'your-super-secret-key-change-this',
        'brosam',
        'changeme',
        'secret',
        'test'
    }

    @classmethod
    def validate_production(cls):
        secret = os.environ.get('SECRET_KEY', '').strip()
        if not secret or secret in cls.INSECURE_SECRETS or len(secret) < 16:
            raise ValueError(
                "Production mode requires a strong explicit SECRET_KEY environment variable. "
                "Default or fallback secrets are forbidden in production."
            )


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
