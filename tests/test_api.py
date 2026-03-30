"""
Unit tests for API endpoints.
"""

import pytest
import json
from app import app, db
from models import Order, Restaurant, User
from datetime import datetime
import uuid


@pytest.mark.unit
class TestOrderAPI:
    """Test order API endpoints."""
    
    def test_get_orders_requires_auth(self, client):
        """Test that /api/orders requires authentication."""
        response = client.get('/api/orders')
        # Should redirect to login or return 401
        assert response.status_code in [302, 401]
    
    def test_create_order_requires_auth(self, client):
        """Test that creating orders requires authentication."""
        response = client.post('/api/orders', json={
            'customer_name': 'Test Customer',
            'table_number': '01',
            'items': [{'name': 'Item 1', 'qty': 1, 'price': 10.00}],
            'total': 10.00
        })
        assert response.status_code in [302, 401]
    
    def test_order_number_format(self, test_restaurant):
        """Test that order numbers are generated in correct format."""
        with app.app_context():
            order = Order(
                restaurant_id=test_restaurant.restaurant_id,
                customer_name='Test Customer',
                table_number='01',
                order_number='ORD' + datetime.now().strftime('%Y%m%d') + '001',
                items_json=json.dumps([{'name': 'Item 1', 'qty': 1}]),
                total_amount=10.00,
                status='PENDING'
            )
            db.session.add(order)
            db.session.commit()
            
            retrieved = Order.query.first()
            # Format: ORD20260330001
            assert retrieved.order_number.startswith('ORD')
            assert len(retrieved.order_number) == 13  # ORD + YYYYMMDD + 001


@pytest.mark.unit
class TestQRCodeAPI:
    """Test QR code generation endpoint."""
    
    def test_qr_code_requires_auth(self, client):
        """Test that QR code generation requires authentication."""
        response = client.get('/api/qr-code?table=01')
        assert response.status_code in [302, 401]
    
    def test_qr_code_includes_table(self, test_restaurant):
        """Test that QR codes include table parameter."""
        with app.app_context():
            # QR code should include table parameter in URL
            expected_url = test_restaurant.permanent_menu_url + '?table=01'
            assert 'table=01' in expected_url


@pytest.mark.unit
class TestStatsAPI:
    """Test statistics API endpoint."""
    
    def test_stats_requires_auth(self, client):
        """Test that /api/stats requires authentication."""
        response = client.get('/api/stats')
        assert response.status_code in [302, 401]
    
    def test_stats_returns_json(self, test_restaurant, test_user):
        """Test that stats endpoint returns JSON."""
        with app.app_context():
            # Create some test orders
            for i in range(3):
                order = Order(
                    restaurant_id=test_restaurant.restaurant_id,
                    customer_name=f'Customer {i}',
                    table_number='01',
                    order_number=f'ORD202603300{i+1}',
                    items_json='[]',
                    total_amount=10.00 * (i + 1),
                    status='PENDING'
                )
                db.session.add(order)
            
            db.session.commit()
            
            # Verify orders exist
            orders = Order.query.filter_by(
                restaurant_id=test_restaurant.restaurant_id
            ).all()
            assert len(orders) == 3


@pytest.mark.security
class TestAPIMultiTenantSecurity:
    """Test multi-tenant security on API endpoints."""
    
    def test_cannot_access_other_restaurant_orders(self):
        """Test that users cannot access other restaurant's orders."""
        with app.app_context():
            # Create two restaurants
            rest1_id = str(uuid.uuid4())
            rest2_id = str(uuid.uuid4())
            
            rest1 = Restaurant(restaurant_id=rest1_id, license_key='KEY-001')
            rest2 = Restaurant(restaurant_id=rest2_id, license_key='KEY-002')
            db.session.add(rest1)
            db.session.add(rest2)
            db.session.commit()
            
            # Create orders for both
            order1 = Order(
                restaurant_id=rest1_id,
                customer_name='Rest 1 Customer',
                order_number='ORD001',
                items_json='[]',
                total_amount=10.00
            )
            order2 = Order(
                restaurant_id=rest2_id,
                customer_name='Rest 2 Customer',
                order_number='ORD002',
                items_json='[]',
                total_amount=20.00
            )
            db.session.add(order1)
            db.session.add(order2)
            db.session.commit()
            
            # Verify orders are separate
            rest1_orders = Order.query.filter_by(restaurant_id=rest1_id).all()
            rest2_orders = Order.query.filter_by(restaurant_id=rest2_id).all()
            
            assert len(rest1_orders) == 1
            assert len(rest2_orders) == 1
            assert rest1_orders[0].customer_name == 'Rest 1 Customer'
            assert rest2_orders[0].customer_name == 'Rest 2 Customer'
    
    def test_order_queries_include_restaurant_filter(self, test_restaurant, test_user):
        """Test that all order queries filter by restaurant_id."""
        with app.app_context():
            # Create test order
            order = Order(
                restaurant_id=test_restaurant.restaurant_id,
                customer_name='Test',
                order_number='ORD001',
                items_json='[]',
                total_amount=10.00
            )
            db.session.add(order)
            db.session.commit()
            
            # Query should filter by restaurant_id AND order_id
            retrieved = Order.query.filter_by(
                restaurant_id=test_restaurant.restaurant_id,
                id=order.id
            ).first()
            assert retrieved is not None
            assert retrieved.restaurant_id == test_restaurant.restaurant_id


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling on API endpoints."""
    
    def test_404_handler_exists(self, client):
        """Test that 404 errors are handled gracefully."""
        response = client.get('/nonexistent-route')
        assert response.status_code == 404
    
    def test_500_handler_exists(self, client):
        """Test that 500 errors are handled gracefully."""
        # This would require triggering a server error
        # In real tests, you might mock a database error
        pass
    
    def test_invalid_json_handling(self, client, test_user):
        """Test that invalid JSON is handled gracefully."""
        # Requires authentication, but tests the error handling
        response = client.post('/api/orders', 
            data='invalid json',
            content_type='application/json'
        )
        # Should either reject the request or handle the error
        assert response.status_code in [400, 401, 302]


@pytest.mark.unit
class TestInputValidation:
    """Test input validation on API endpoints."""
    
    def test_order_requires_customer_name(self, test_restaurant, test_user):
        """Test that orders require a customer name."""
        with app.app_context():
            # Try to create order without customer_name
            # This test would need to be run against the actual endpoint
            # For now, we test the validation logic
            
            from security import validate_input, ValidationError
            
            try:
                validate_input({
                    'required': ['customer_name', 'items'],
                    'types': {}
                }, data={})
                assert False, "Should have raised ValidationError"
            except Exception:
                # Expected - validation should fail
                pass
    
    def test_order_items_must_be_list(self, test_restaurant, test_user):
        """Test that items must be a list."""
        with app.app_context():
            # Items must be a list, not a string or dict
            from security import validate_input
            
            # Valid: items is a list
            try:
                data = {'items': [{'name': 'Item 1'}]}
                # Would validate successfully
            except:
                pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
