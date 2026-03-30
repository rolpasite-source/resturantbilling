#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Initialize the database with default admin user
Run this once to set up the database
"""

from app import app, db
from models import User, Restaurant
from datetime import datetime
import os

def init_db():
    """Initialize database with default data"""
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✅ Tables created")
        
        # Check if admin restaurant exists
        admin_restaurant = Restaurant.query.filter_by(name="Admin Restaurant").first()
        if not admin_restaurant:
            admin_restaurant = Restaurant(
                name="Admin Restaurant",
                owner_name="Admin",
                contact_no="9999999999",
                license_key="ADMIN-LICENSE-KEY-001",
                license_status="ACTIVE",
                is_active=True,
                permanent_menu_url="https://menu.example.com"
            )
            db.session.add(admin_restaurant)
            db.session.commit()
            print("✅ Admin restaurant created")
        else:
            print("⚠️ Admin restaurant already exists")
        
        # Check if admin user exists
        admin_user = User.query.filter_by(username="admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@restaurant.com",
                restaurant_id=admin_restaurant.id,
                role="owner",
                is_active=True,
                created_at=datetime.utcnow()
            )
            admin_user.set_password("admin123")  # Set password hash
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Admin user created (username: admin, password: admin123)")
        else:
            print("⚠️ Admin user already exists")
        
        print("\n✅ Database initialized successfully!")

if __name__ == '__main__':
    init_db()
