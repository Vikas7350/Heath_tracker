import os
from dotenv import load_dotenv

load_dotenv(override=True)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

    _mongo_uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/health_tracker')
    if 'serverSelectionTimeoutMS' not in _mongo_uri:
        _mongo_uri += ('&' if '?' in _mongo_uri else '?') + 'serverSelectionTimeoutMS=5000&connectTimeoutMS=5000'
    MONGO_URI = _mongo_uri
    MONGO_DBNAME = os.environ.get('MONGO_DBNAME', 'health_tracker')

    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')

    # Session & security
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('SESSION_TIMEOUT_SECONDS', 3600))
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', str(not DEBUG)).lower() == 'true'
    SESSION_COOKIE_HTTPONLY = os.environ.get('SESSION_COOKIE_HTTPONLY', 'True').lower() == 'true'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    PROPAGATE_EXCEPTIONS = False
