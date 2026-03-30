# -*- coding: utf-8 -*-
"""
Database Models - Multi-tenant schema for 1000+ restaurants
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

db = SQLAlchemy()

class Restaurant(db.Model):
    """Restaurant/Organization - Top-level tenant"""
    __tablename__ = 'restaurants'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Business info
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(500))
    contact_no = db.Column(db.String(20))
    pan_no = db.Column(db.String(20), unique=True)
    owner_name = db.Column(db.String(255))
    
    # License info
    license_key = db.Column(db.String(100), unique=True, nullable=False)
    license_status = db.Column(db.String(50), default='ACTIVE')  # ACTIVE, SUSPENDED, EXPIRED
    license_expiry = db.Column(db.DateTime)
    
    # Cloudflare integration
    cloudflare_worker_url = db.Column(db.String(500))
    permanent_menu_url = db.Column(db.String(500))
    menu_url_shortcode = db.Column(db.String(20), unique=True)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    users = db.relationship('User', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Restaurant {self.name}>'

class User(UserMixin, db.Model):
    """Restaurant staff users"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id'), nullable=False)
    
    # Authentication
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile
    full_name = db.Column(db.String(255))
    role = db.Column(db.String(50), default='staff')  # owner, manager, staff, kitchen
    is_active = db.Column(db.Boolean, default=True)
    
    # Security
    last_login = db.Column(db.DateTime)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        """Hash password"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission):
        """Check if user has permission"""
        permissions = {
            'owner': ['view_all', 'create_order', 'modify_order', 'delete_order', 'manage_staff', 'view_reports', 'manage_settings'],
            'manager': ['view_all', 'create_order', 'modify_order', 'view_reports'],
            'staff': ['create_order', 'view_own_orders'],
            'kitchen': ['view_pending_orders', 'update_order_status']
        }
        return permission in permissions.get(self.role, [])
    
    def __repr__(self):
        return f'<User {self.username}>'

class Order(db.Model):
    """Customer orders - CRITICAL: Must always filter by restaurant_id"""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id'), nullable=False, index=True)  # ⭐ KEY FIELD
    
    # Order info
    order_number = db.Column(db.String(50), unique=True, nullable=False)  # ORD20260330001
    customer_name = db.Column(db.String(255), nullable=False)
    table_number = db.Column(db.Integer)
    
    # Items & pricing
    items_json = db.Column(db.JSON)  # Serialized order items
    subtotal = db.Column(db.Float, default=0)
    tax = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, nullable=False)
    
    # Status tracking
    status = db.Column(db.String(50), default='PENDING')  # PENDING, CONFIRMED, PREPARING, READY, SERVED, PAID, CANCELLED
    payment_status = db.Column(db.String(50), default='UNPAID')  # UNPAID, PARTIAL, PAID, REFUNDED
    
    # Payment
    payment_method = db.Column(db.String(50))  # CASH, CARD, ONLINE
    payment_reference = db.Column(db.String(100))  # For tracking
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime)
    served_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    
    # Relationships
    payments = db.relationship('Payment', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('idx_restaurant_orders', 'restaurant_id', 'id'),
        db.Index('idx_restaurant_status', 'restaurant_id', 'status'),
    )
    
    def __repr__(self):
        return f'<Order {self.order_number}>'

class Payment(db.Model):
    """Payment records - NEVER store full card details"""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))
    stripe_payment_id = db.Column(db.String(100))  # External ID, not our card
    
    status = db.Column(db.String(50), default='PENDING')  # PENDING, COMPLETED, FAILED, REFUNDED
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Payment {self.amount}>'

class AuditLog(db.Model):
    """Audit trail - track all important actions"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id'), nullable=False, index=True)
    
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))  # ORDER, USER, PAYMENT, etc
    entity_id = db.Column(db.String(100))
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    
    old_value = db.Column(db.JSON)  # For tracking changes
    new_value = db.Column(db.JSON)
    details = db.Column(db.Text)
    
    severity = db.Column(db.String(50), default='INFO')  # INFO, WARNING, ERROR, CRITICAL
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        db.Index('idx_restaurant_audit', 'restaurant_id', 'created_at'),
    )
    
    def __repr__(self):
        return f'<AuditLog {self.action}>'
