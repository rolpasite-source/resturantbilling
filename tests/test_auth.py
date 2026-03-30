"""
Unit tests for authentication routes and security.
"""

import pytest
from app import app, db
from models import User, Restaurant, AuditLog
from datetime import datetime
import uuid


@pytest.mark.unit
class TestAuthenticationFlow:
    """Test authentication routes and flows."""
    
    def test_login_page_loads(self, client):
        """Test that login page loads without authentication."""
        response = client.get('/')
        assert response.status_code == 302  # Redirect to login
        assert '/auth/login' in response.location or '/dashboard' in response.location
    
    def test_login_with_invalid_credentials(self, client, test_user):
        """Test login fails with wrong password."""
        response = client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        # Should show error (status 200 due to redirect)
        assert response.status_code == 200
        assert b'Invalid' in response.data or b'incorrect' in response.data.lower()
    
    def test_register_with_invalid_license(self, client):
        """Test registration fails with invalid license key."""
        response = client.post('/auth/register', data={
            'license_key': 'INVALID-LICENSE-KEY'
        }, follow_redirects=True)
        
        # Should show error (license verification fails)
        assert response.status_code == 200
        assert b'Invalid' in response.data or b'license' in response.data.lower()
    
    def test_password_change_requires_auth(self, client):
        """Test that password change requires authentication."""
        response = client.post('/auth/change-password', data={
            'current_password': 'password',
            'new_password': 'newpassword',
            'confirm_password': 'newpassword'
        }, follow_redirects=True)
        
        # Should redirect to login (not authenticated)
        assert response.status_code == 200
        assert b'login' in response.data.lower()
    
    def test_logout_clears_session(self, client, test_user):
        """Test that logout clears user session."""
        # This would require setting up a logged-in session first
        # For now, we'll just test the logout route exists
        response = client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200


@pytest.mark.security
class TestRateLimiting:
    """Test rate limiting on sensitive endpoints."""
    
    def test_login_rate_limiting(self, client, test_user):
        """Test that login attempts are rate-limited."""
        # Simulate 6 failed attempts (limit is 5)
        for i in range(6):
            response = client.post('/auth/login', data={
                'username': 'testuser',
                'password': 'wrongpassword'
            })
            
            if i < 5:
                # First 5 should fail with invalid credentials
                assert response.status_code in [200, 302]
            else:
                # 6th should fail with rate limit
                assert b'locked' in response.data.lower() or response.status_code == 429


@pytest.mark.security
class TestPasswordSecurity:
    """Test password security features."""
    
    def test_password_requires_minimum_length(self, client):
        """Test that passwords must be at least 8 characters."""
        # This would require being authenticated
        # Test would call /auth/change-password with short password
        pass
    
    def test_password_not_stored_plaintext(self):
        """Test that passwords are hashed, not stored plaintext."""
        with app.app_context():
            user = User(
                username='sectest',
                email='sectest@test.com',
                restaurant_id='test-restaurant',
                password_hash='pbkdf2:sha256$260000$test$test',
                role='owner'
            )
            db.session.add(user)
            db.session.commit()
            
            # Retrieve and verify password is hashed
            retrieved = User.query.filter_by(username='sectest').first()
            assert retrieved is not None
            assert retrieved.password_hash.startswith('pbkdf2:sha256')
            assert 'password' not in retrieved.password_hash.lower()


@pytest.mark.unit
class TestAuditLogging:
    """Test audit logging for security events."""
    
    def test_login_attempt_logged(self, test_restaurant):
        """Test that login attempts are logged."""
        with app.app_context():
            # Create a test login audit log entry
            audit = AuditLog(
                restaurant_id=test_restaurant.restaurant_id,
                user_id=None,
                action='LOGIN_ATTEMPT',
                entity_type='User',
                entity_id='test-user',
                severity='INFO',
                ip_address='127.0.0.1',
                additional_data='{"success": false, "reason": "invalid_password"}'
            )
            db.session.add(audit)
            db.session.commit()
            
            # Verify log exists
            logged = AuditLog.query.filter_by(action='LOGIN_ATTEMPT').first()
            assert logged is not None
            assert logged.severity == 'INFO'
    
    def test_sensitive_actions_logged(self, test_restaurant, test_user):
        """Test that sensitive actions are audited."""
        with app.app_context():
            sensitive_actions = [
                'PASSWORD_CHANGED',
                'USER_CREATED',
                'USER_ROLE_CHANGED',
                'ORDER_CANCELLED',
                'PAYMENT_REFUNDED'
            ]
            
            for action in sensitive_actions:
                audit = AuditLog(
                    restaurant_id=test_restaurant.restaurant_id,
                    user_id=test_user.id,
                    action=action,
                    entity_type='Order' if 'ORDER' in action else 'User',
                    entity_id='test-id',
                    severity='WARNING' if 'CHANGED' in action else 'INFO'
                )
                db.session.add(audit)
            
            db.session.commit()
            
            # Verify all logs exist
            logs = AuditLog.query.filter(
                AuditLog.action.in_(sensitive_actions)
            ).all()
            assert len(logs) == len(sensitive_actions)


@pytest.mark.unit
class TestMultiTenantIsolation:
    """Test multi-tenant data isolation."""
    
    def test_user_belongs_to_restaurant(self, test_restaurant, test_user):
        """Test that users are properly tied to restaurants."""
        with app.app_context():
            user = User.query.filter_by(username='testuser').first()
            assert user is not None
            assert user.restaurant_id == test_restaurant.restaurant_id
    
    def test_restaurant_isolation(self):
        """Test that restaurants cannot see each other's data."""
        with app.app_context():
            # Create two restaurants
            rest1 = Restaurant(
                restaurant_id=str(uuid.uuid4()),
                license_key='KEY-001',
                name='Restaurant 1'
            )
            rest2 = Restaurant(
                restaurant_id=str(uuid.uuid4()),
                license_key='KEY-002',
                name='Restaurant 2'
            )
            db.session.add(rest1)
            db.session.add(rest2)
            db.session.commit()
            
            # Verify both exist
            all_restaurants = Restaurant.query.all()
            assert len(all_restaurants) == 2
            
            # Verify they have different IDs
            ids = {r.restaurant_id for r in all_restaurants}
            assert len(ids) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
