# -*- coding: utf-8 -*-
"""
Security Decorators & Utilities
"""

from functools import wraps
from flask import session, redirect, url_for, jsonify, request
from flask_login import current_user
from datetime import datetime, timedelta
import logging
from models import Restaurant, User
import json

logger = logging.getLogger(__name__)

# Rate limiting in-memory store
login_attempts = {}  # {ip: [(timestamp, success), ...]}

def login_required(f):
    """Require user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or 'restaurant_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def restaurant_required(f):
    """Require restaurant context"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'restaurant_id' not in session:
            return jsonify({'error': 'Restaurant context required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    """Check if user has specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            
            user = User.query.get(session.get('user_id'))
            if not user or not user.has_permission(permission):
                logger.warning(f"Permission denied: user {user.id if user else 'unknown'} lacks {permission}")
                return jsonify({'error': 'Permission denied'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limit(max_attempts=5, window_seconds=900):
    """Rate limit by IP address"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr
            now = datetime.utcnow().timestamp()
            
            # Clean old attempts
            if ip in login_attempts:
                login_attempts[ip] = [
                    (ts, success) for ts, success in login_attempts[ip]
                    if now - ts < window_seconds
                ]
            
            # Check limit
            recent_failed = [
                (ts, success) for ts, success in login_attempts.get(ip, [])
                if not success
            ]
            
            if len(recent_failed) >= max_attempts:
                logger.warning(f"Rate limit exceeded for IP {ip} on {f.__name__}")
                return jsonify({'error': 'Too many attempts. Please try again later.'}), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_restaurant():
    """Get current user's restaurant"""
    if 'restaurant_id' not in session:
        return None
    return Restaurant.query.get(session['restaurant_id'])

def validate_restaurant_access(restaurant_id):
    """Verify user has access to this restaurant"""
    if 'restaurant_id' not in session:
        return False
    return session['restaurant_id'] == restaurant_id

def audit_log(action, entity_type=None, entity_id=None, 
              old_value=None, new_value=None, details=None, severity='INFO'):
    """Log audit trail"""
    from models import AuditLog, db
    
    try:
        log_entry = AuditLog(
            restaurant_id=session.get('restaurant_id'),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=session.get('user_id'),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500],
            old_value=old_value,
            new_value=new_value,
            details=details,
            severity=severity
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Also log to application logs
        logger.info(f"[{severity}] {action} | Restaurant: {session.get('restaurant_id')} | Details: {details}")
        
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")

def track_login_attempt(ip, success=True):
    """Track login attempts for rate limiting"""
    now = datetime.utcnow().timestamp()
    
    if ip not in login_attempts:
        login_attempts[ip] = []
    
    login_attempts[ip].append((now, success))
    
    # Cleanup old entries
    login_attempts[ip] = [
        (ts, success) for ts, success in login_attempts[ip]
        if now - ts < 900  # 15 minutes
    ]

def validate_input(data, required_fields=None, field_types=None, max_lengths=None):
    """Validate input data"""
    if required_fields is None:
        required_fields = []
    if field_types is None:
        field_types = {}
    if max_lengths is None:
        max_lengths = {}
    
    errors = {}
    
    # Check required fields
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            errors[field] = f'{field} is required'
    
    # Check types
    for field, expected_type in field_types.items():
        if field in data:
            if not isinstance(data[field], expected_type):
                errors[field] = f'{field} must be {expected_type.__name__}'
    
    # Check max lengths
    for field, max_len in max_lengths.items():
        if field in data and len(str(data[field])) > max_len:
            errors[field] = f'{field} must be max {max_len} characters'
    
    return errors if errors else None

def sanitize_input(value, max_length=None):
    """Sanitize user input"""
    if not isinstance(value, str):
        return value
    
    # Strip whitespace
    value = value.strip()
    
    # Remove potentially harmful characters
    value = value.replace('<', '&lt;').replace('>', '&gt;')
    
    # Limit length
    if max_length:
        value = value[:max_length]
    
    return value

def check_restaurant_access(restaurant_id):
    """Ensure user has access to restaurant"""
    if 'restaurant_id' not in session:
        return False, 'Not authenticated'
    
    if session['restaurant_id'] != restaurant_id:
        audit_log(
            'UNAUTHORIZED_ACCESS_ATTEMPT',
            entity_type='RESTAURANT',
            entity_id=str(restaurant_id),
            severity='WARNING'
        )
        return False, 'Access denied'
    
    return True, None
