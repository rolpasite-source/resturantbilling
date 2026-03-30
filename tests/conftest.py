"""
Pytest configuration and fixtures for Restaurant Billing tests.
"""

import os
import pytest
from app import app, db
from models import Restaurant, User
from datetime import datetime
import uuid


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def runner():
    """Create a test CLI runner for the Flask app."""
    return app.test_cli_runner()


@pytest.fixture
def test_restaurant(client):
    """Create a test restaurant."""
    with app.app_context():
        restaurant = Restaurant(
            restaurant_id=str(uuid.uuid4()),
            license_key='TEST-LICENSE-KEY-001',
            license_status='ACTIVE',
            license_expiry=datetime(2025, 12, 31),
            name='Test Restaurant',
            phone='1234567890',
            email='test@restaurant.com',
            cloudflare_url='https://test.himalayanhotel.workers.dev',
            permanent_menu_url='https://test-permanent.himalayanhotel.workers.dev',
            menu_url_shortcode='test123'
        )
        db.session.add(restaurant)
        db.session.commit()
        return restaurant


@pytest.fixture
def test_user(test_restaurant):
    """Create a test user."""
    with app.app_context():
        user = User(
            username='testuser',
            email='testuser@test.com',
            restaurant_id=test_restaurant.restaurant_id,
            password_hash='pbkdf2:sha256$260000$test$test',  # 'password'
            role='owner',
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def authenticated_client(client, test_user):
    """Create an authenticated test client (logged-in user)."""
    with client:
        # Note: This requires you to implement cookie-based session testing
        # For now, we'll just return the client
        # In a real scenario, you'd call /auth/login endpoint
        return client


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "security: mark test as a security test"
    )
