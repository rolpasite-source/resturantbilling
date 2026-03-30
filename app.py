# -*- coding: utf-8 -*-
"""
Restaurant Billing System - Secure Web Version
Multi-tenant architecture for 1000+ restaurants
"""

from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from flask_talisman import Talisman
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import configuration
from config import app_config
from models import db, User, Restaurant, Order, AuditLog
from security import audit_log, get_current_restaurant, login_required, restaurant_required
from routes_auth import auth_bp

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(app_config)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ===== SECURITY MIDDLEWARE =====

# Enable HTTPS only (Talisman enforces security headers)
Talisman(app, 
    force_https=True,
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy={
        'default-src': "'self'",
        'script-src': ["'self'", "'unsafe-inline'"],  # Allow inline for now, can restrict later
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", "data:", "https:"],
        'font-src': ["'self'"],
    }
)

# CSRF Protection
csrf = CSRFProtect(app)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=app.config['RATELIMIT_STORAGE_URL']
)

# Database
db.init_app(app)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===== HEALTH CHECK (Required for Railway) =====

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    try:
        with app.app_context():
            db.session.execute(db.text("SELECT 1"))
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

# ===== ERROR HANDLERS =====

@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return render_template('errors/500.html'), 500

# ===== ROUTES =====

# Register blueprints
app.register_blueprint(auth_bp)

@app.before_request
def before_request():
    """Run before each request"""
    # Validate session
    if 'user_id' in session and 'restaurant_id' in session:
        user = User.query.get(session['user_id'])
        if not user or not user.is_active:
            session.clear()
            return redirect(url_for('auth.login'))
        
        restaurant = Restaurant.query.get(session['restaurant_id'])
        if not restaurant or not restaurant.is_active:
            session.clear()
            return redirect(url_for('auth.login'))

@app.route('/')
def index():
    """Home page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/dashboard')
@login_required
@restaurant_required
def dashboard():
    """Main dashboard"""
    restaurant = get_current_restaurant()
    
    # Get today's statistics
    today = datetime.utcnow().date()
    
    total_orders = Order.query.filter(
        Order.restaurant_id == restaurant.id,
        db.func.date(Order.created_at) == today
    ).count()
    
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.restaurant_id == restaurant.id,
        db.func.date(Order.created_at) == today,
        Order.payment_status == 'PAID'
    ).scalar() or 0
    
    pending_orders = Order.query.filter(
        Order.restaurant_id == restaurant.id,
        Order.status.in_(['PENDING', 'CONFIRMED', 'PREPARING'])
    ).count()
    
    audit_log('DASHBOARD_VIEW', entity_type='DASHBOARD')
    
    return render_template('dashboard.html',
        restaurant=restaurant,
        total_orders=total_orders,
        total_revenue=float(total_revenue),
        pending_orders=pending_orders
    )

@app.route('/api/orders', methods=['GET', 'POST'])
@login_required
@restaurant_required
def orders_api():
    """Get or create orders"""
    restaurant_id = session.get('restaurant_id')
    
    if request.method == 'GET':
        # Get orders for this restaurant
        status = request.args.get('status')
        limit = int(request.args.get('limit', 20))
        
        query = Order.query.filter_by(restaurant_id=restaurant_id)
        
        if status:
            query = query.filter_by(status=status)
        
        orders = query.order_by(Order.created_at.desc()).limit(limit).all()
        
        return jsonify({
            'success': True,
            'orders': [{
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': o.customer_name,
                'table_number': o.table_number,
                'total_amount': o.total_amount,
                'status': o.status,
                'payment_status': o.payment_status,
                'created_at': o.created_at.isoformat()
            } for o in orders]
        })
    
    elif request.method == 'POST':
        # Create new order
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['customer_name', 'items', 'total_amount']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400
        
        # Validate data
        if not isinstance(data['items'], list) or len(data['items']) == 0:
            return jsonify({'error': 'Items list cannot be empty'}), 400
        
        if data['total_amount'] <= 0:
            return jsonify({'error': 'Amount must be greater than 0'}), 400
        
        # Generate order number
        import datetime as dt
        today = dt.date.today()
        count = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            db.func.date(Order.created_at) == today
        ).count() + 1
        order_number = f"ORD{today.strftime('%Y%m%d')}{count:03d}"
        
        # Create order
        order = Order(
            restaurant_id=restaurant_id,
            order_number=order_number,
            customer_name=data.get('customer_name', '').strip()[:255],
            table_number=data.get('table_number'),
            items_json=data.get('items'),
            total_amount=float(data['total_amount']),
            status='PENDING'
        )
        
        db.session.add(order)
        db.session.commit()
        
        audit_log('ORDER_CREATED', 
                 entity_type='ORDER', 
                 entity_id=str(order.id),
                 new_value={'order_number': order.order_number, 'amount': order.total_amount})
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'message': 'Order created successfully'
        }), 201

@app.route('/api/orders/<int:order_id>', methods=['GET', 'PUT'])
@login_required
@restaurant_required
def order_detail(order_id):
    """Get or update specific order"""
    restaurant_id = session.get('restaurant_id')
    
    # ⭐ SECURITY: Always filter by restaurant_id
    order = Order.query.filter_by(
        id=order_id,
        restaurant_id=restaurant_id
    ).first()
    
    if not order:
        audit_log('ORDER_ACCESS_DENIED', entity_type='ORDER', entity_id=str(order_id), severity='WARNING')
        return jsonify({'error': 'Order not found'}), 404
    
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'customer_name': order.customer_name,
                'table_number': order.table_number,
                'items': order.items_json,
                'total_amount': order.total_amount,
                'status': order.status,
                'payment_status': order.payment_status,
                'created_at': order.created_at.isoformat()
            }
        })
    
    elif request.method == 'PUT':
        data = request.get_json()
        
        # Update status if provided
        if 'status' in data:
            valid_statuses = ['PENDING', 'CONFIRMED', 'PREPARING', 'READY', 'SERVED', 'CANCELLED']
            if data['status'] not in valid_statuses:
                return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
            
            old_status = order.status
            order.status = data['status']
            
            if data['status'] == 'SERVED':
                order.served_at = datetime.utcnow()
            
            db.session.commit()
            
            audit_log('ORDER_STATUS_CHANGED',
                     entity_type='ORDER',
                     entity_id=str(order.id),
                     old_value={'status': old_status},
                     new_value={'status': order.status})
        
        return jsonify({
            'success': True,
            'message': 'Order updated successfully'
        })

@app.route('/api/qr-code', methods=['GET'])
@login_required
@restaurant_required
def generate_qr():
    """Generate QR code for menu"""
    if not app.config['ENABLE_QR_GENERATION']:
        return jsonify({'error': 'QR generation disabled'}), 403
    
    restaurant = get_current_restaurant()
    if not restaurant.permanent_menu_url:
        return jsonify({'error': 'Permanent menu URL not configured'}), 400
    
    table_number = request.args.get('table', '')
    
    if table_number:
        try:
            table_num = int(table_number)
            if table_num < 1 or table_num > 999:
                return jsonify({'error': 'Table number must be between 1 and 999'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid table number'}), 400
    
    # Generate QR code
    import qrcode
    import io
    from base64 import b64encode
    
    qr_url = f"{restaurant.permanent_menu_url}?table={table_number}" if table_number else restaurant.permanent_menu_url
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = b64encode(buffered.getvalue()).decode()
    
    audit_log('QR_CODE_GENERATED', entity_type='QR', 
             details=f'Table: {table_number or "General"}')
    
    return jsonify({
        'success': True,
        'qr_code': f'data:image/png;base64,{img_str}',
        'url': qr_url
    })

@app.route('/api/stats', methods=['GET'])
@login_required
@restaurant_required
def stats():
    """Get restaurant statistics"""
    restaurant_id = session.get('restaurant_id')
    
    # Today's stats
    today = datetime.utcnow().date()
    
    orders_today = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        db.func.date(Order.created_at) == today
    ).count()
    
    revenue_today = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.restaurant_id == restaurant_id,
        db.func.date(Order.created_at) == today,
        Order.payment_status == 'PAID'
    ).scalar() or 0
    
    pending_orders = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.status.in_(['PENDING', 'CONFIRMED', 'PREPARING'])
    ).count()
    
    return jsonify({
        'success': True,
        'stats': {
            'orders_today': orders_today,
            'revenue_today': float(revenue_today),
            'pending_orders': pending_orders,
            'timestamp': datetime.utcnow().isoformat()
        }
    })

# ===== DATABASE INITIALIZATION =====

with app.app_context():
    try:
        db.create_all()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ Database init warning (may be normal): {e}")


# ===== RUN =====

if __name__ == '__main__':
    # In production, use gunicorn:
    # gunicorn -w 4 -b 0.0.0.0:8000 app:app
    
    debug_mode = app.config.get('DEBUG', False)
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=debug_mode
    )
