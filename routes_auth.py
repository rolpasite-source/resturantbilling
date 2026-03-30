# -*- coding: utf-8 -*-
"""
Authentication Module
"""

from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models import db, User, Restaurant
from security import rate_limit, track_login_attempt, audit_log, sanitize_input
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(max_attempts=5, window_seconds=900)
def login():
    """User login"""
    if request.method == 'GET':
        return render_template('auth/login.html')
    
    # POST request
    username = sanitize_input(request.form.get('username', ''))
    password = request.form.get('password', '')
    
    if not username or not password:
        return render_template('auth/login.html', error='Username and password required'), 400
    
    # Find user
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.check_password(password):
        track_login_attempt(request.remote_addr, success=False)
        audit_log('LOGIN_FAILED', entity_type='USER', details=f'Invalid credentials for {username}')
        return render_template('auth/login.html', error='Invalid credentials'), 401
    
    # Check if user is active
    if not user.is_active:
        audit_log('LOGIN_FAILED', entity_type='USER', details=f'Inactive user {username}')
        return render_template('auth/login.html', error='Account is inactive'), 403
    
    # Check if restaurant is active
    restaurant = user.restaurant
    if not restaurant or not restaurant.is_active:
        audit_log('LOGIN_FAILED', entity_type='USER', details=f'Inactive restaurant for user {username}')
        return render_template('auth/login.html', error='Restaurant is inactive'), 403
    
    # Check license
    if restaurant.license_status != 'ACTIVE':
        audit_log('LOGIN_FAILED', entity_type='USER', details=f'Invalid license for restaurant {restaurant.id}')
        return render_template('auth/login.html', error='License is not active'), 403
    
    if restaurant.license_expiry and restaurant.license_expiry < datetime.utcnow():
        audit_log('LOGIN_FAILED', entity_type='USER', details=f'Expired license for restaurant {restaurant.id}')
        return render_template('auth/login.html', error='License has expired'), 403
    
    # Check account lockout
    if user.locked_until and user.locked_until > datetime.utcnow():
        remaining = (user.locked_until - datetime.utcnow()).total_seconds() / 60
        audit_log('LOGIN_FAILED', entity_type='USER', details=f'Account locked for {username}')
        return render_template('auth/login.html', error=f'Account locked. Try again in {int(remaining)} minutes'), 403
    
    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    # Create session
    session['user_id'] = user.id
    session['restaurant_id'] = restaurant.id
    session['username'] = username
    session['restaurant_name'] = restaurant.name
    session['user_role'] = user.role
    session.permanent = True
    
    track_login_attempt(request.remote_addr, success=True)
    audit_log('LOGIN_SUCCESS', entity_type='USER', details=f'User {username} logged in')
    
    return redirect(url_for('dashboard'))

@auth_bp.route('/logout')
def logout():
    """User logout"""
    username = session.get('username', 'Unknown')
    restaurant_id = session.get('restaurant_id')
    
    session.clear()
    
    audit_log('LOGOUT', entity_type='USER', details=f'User {username} logged out', restaurant_id=restaurant_id)
    
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Restaurant registration (with license verification)"""
    if request.method == 'GET':
        return render_template('auth/register.html')
    
    # POST - Register new restaurant
    # Verify license first
    license_key = request.form.get('license_key', '').strip()
    username = sanitize_input(request.form.get('username', ''))
    password = request.form.get('password', '')
    password_confirm = request.form.get('password_confirm', '')
    
    if not all([license_key, username, password]):
        return render_template('auth/register.html', error='All fields required'), 400
    
    if password != password_confirm:
        return render_template('auth/register.html', error='Passwords do not match'), 400
    
    if len(password) < 8:
        return render_template('auth/register.html', error='Password must be at least 8 characters'), 400
    
    # Check license validity with License Server
    import requests
    from config import app_config
    
    try:
        response = requests.get(
            app_config.LICENSE_SERVER_API,
            params={'license_key': license_key},
            timeout=10
        )
        
        if response.status_code != 200:
            audit_log('REGISTRATION_FAILED', details=f'Invalid license {license_key}', severity='WARNING')
            return render_template('auth/register.html', error='Invalid license key'), 400
        
        license_data = response.json()
        if not license_data.get('success'):
            return render_template('auth/register.html', error='License verification failed'), 400
        
    except Exception as e:
        logger.error(f"License verification error: {e}")
        return render_template('auth/register.html', error='License server unavailable'), 500
    
    # Check if user exists
    if User.query.filter_by(username=username).first():
        return render_template('auth/register.html', error='Username already exists'), 400
    
    # Create restaurant (if doesn't exist)
    license_data = license_data.get('license', {})
    restaurant = Restaurant.query.filter_by(license_key=license_key).first()
    
    if not restaurant:
        restaurant = Restaurant(
            name=license_data.get('hotel_name', 'New Restaurant'),
            address=license_data.get('address', ''),
            contact_no=license_data.get('contract_no', ''),
            pan_no=license_data.get('pan_no', ''),
            license_key=license_key,
            license_status='ACTIVE',
            cloudflare_worker_url=license_data.get('cloudflare_worker_url', ''),
            permanent_menu_url=license_data.get('permanent_menu_url', '')
        )
        db.session.add(restaurant)
        db.session.commit()
        audit_log('RESTAURANT_CREATED', entity_type='RESTAURANT', entity_id=str(restaurant.id), restaurant_id=restaurant.id)
    
    # Create user
    user = User(
        restaurant_id=restaurant.id,
        username=username,
        full_name=request.form.get('full_name', ''),
        role='owner',  # First user is owner
        is_active=True
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    audit_log('USER_CREATED', entity_type='USER', entity_id=str(user.id), restaurant_id=restaurant.id)
    
    return redirect(url_for('auth.login')), 302

@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """Change user password"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not user.check_password(old_password):
        audit_log('CHANGE_PASSWORD_FAILED', entity_type='USER', 
                 details='Incorrect current password', severity='WARNING')
        return jsonify({'error': 'Incorrect current password'}), 400
    
    if new_password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400
    
    if len(new_password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    
    user.set_password(new_password)
    db.session.commit()
    
    audit_log('CHANGE_PASSWORD', entity_type='USER', details='Password changed successfully')
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})
