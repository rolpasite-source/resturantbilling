# -*- coding: utf-8 -*-
"""
Configuration Module - Secure Web App
Keep all secrets in environment variables, never hardcoded
"""

import os
from datetime import timedelta

class Config:
    """Base configuration"""
    
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    SESSION_PERMANENT = False
    SESSION_COOKIE_SECURE = True  # HTTPS only
    SESSION_COOKIE_HTTPONLY = True  # No JavaScript access
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///restaurant_billing.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # API Keys (from environment only, never hardcode)
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    
    LICENSE_SERVER_API = os.environ.get(
        'LICENSE_SERVER_API', 
        'https://web-production-99f80.up.railway.app/api/verify-license'
    )
    
    # Encryption
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '')
    
    # File uploads
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'xlsx'}
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Features
    ENABLE_PAYMENTS = os.environ.get('ENABLE_PAYMENTS', 'False').lower() == 'true'
    ENABLE_QR_GENERATION = os.environ.get('ENABLE_QR_GENERATION', 'True').lower() == 'true'

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False  # Allow HTTP in dev
    
class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True  # HTTPS required
    # Force SSL redirect
    PREFERRED_URL_SCHEME = 'https'
    
class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

# Load environment-based config
config_name = os.environ.get('FLASK_ENV', 'development')
if config_name == 'production':
    app_config = ProductionConfig
elif config_name == 'testing':
    app_config = TestingConfig
else:
    app_config = DevelopmentConfig
