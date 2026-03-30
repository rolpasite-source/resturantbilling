# Restaurant Billing Web Application

A secure, production-ready web application for managing restaurant orders across 1000+ locations with a unified licensing system.

## 📋 Features

- **Multi-Tenant Architecture**: Complete data isolation between restaurants
- **License-Based Registration**: Restaurant owners register with a valid license key
- **Secure Authentication**: Rate-limited login with account lockout protection
- **QR Code Generation**: Generate table-specific QR codes for customers
- **Real-Time Dashboard**: Live order stats, revenue tracking, pending order count
- **Order Management**: Create, update, and track order status in real-time
- **Role-Based Access Control**: Owner, Manager, Staff, and Kitchen roles with specific permissions
- **Comprehensive Audit Logging**: All important actions logged for compliance
- **Payment Integration**: Stripe integration (optional, no card data stored)
- **Security Headers**: HTTPS enforcement, CSP, HSTS, and more

## 🏗️ Architecture

```
RestaurantBilling_Web/
├── app.py                      # Main Flask application
├── config.py                   # Configuration (dev/prod/testing)
├── models.py                   # SQLAlchemy database models
├── security.py                 # Security decorators & utilities
├── routes_auth.py              # Authentication endpoints
├── requirements.txt            # Python dependencies
├── .env.example               # Environment variable template
├── templates/
│   ├── auth/
│   │   └── login.html         # Login form
│   ├── dashboard.html         # Main dashboard
│   ├── orders.html            # Order management
│   ├── qr_generator.html      # QR code generation
│   └── settings.html          # Restaurant settings
├── static/
│   ├── css/
│   │   └── style.css          # Main stylesheet
│   └── js/
│       └── app.js             # Client-side JavaScript
└── Docker/
    ├── Dockerfile
    └── docker-compose.yml
```

## 🚀 Quick Start

### 1. Local Development Setup

```bash
# Clone or extract the repository
cd RestaurantBilling_Web

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure
cp .env.example .env
# Edit .env with your values:
# - DATABASE_URL: Use SQLite for local dev (sqlite:///billing.db)
# - SECRET_KEY: Generate with: python -c "import secrets; print(secrets.token_hex(32))"
# - LICENSE_SERVER_API: Use the production endpoint

# Initialize database
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Run development server
python app.py
```

The app will be available at `http://localhost:5000`

### 2. First Restaurant Registration

1. Go to `http://localhost:5000`
2. Register with a valid license key from the License Server
3. Create your first user account (automatically assigned as "owner")
4. Log in and view the dashboard

### 3. Generate Required Keys

```bash
# Generate SECRET_KEY for Flask
python -c "import secrets; print(secrets.token_hex(32))"

# Generate Fernet encryption key (if using encrypted fields)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 🔐 Security Implementation

### Multi-Tenant Data Isolation

All queries filter by `restaurant_id` to prevent cross-restaurant data access:

```python
# ✅ CORRECT: Filters by both restaurant_id and order_id
order = Order.query.filter_by(
    restaurant_id=current_user.restaurant_id,
    id=order_id
).first()

# ❌ WRONG: Only filters by order_id (SECURITY VULNERABILITY!)
order = Order.query.get(order_id)
```

### Authentication Flow

1. **Login Endpoint**: `/auth/login`
   - Rate limited to 5 attempts per 15 minutes
   - Validates license is active and not expired
   - Creates secure session with 1-hour timeout
   - Logs all login attempts (success/failure)

2. **Registration Endpoint**: `/auth/register`
   - Requires valid license key
   - Queries License Server API for verification
   - Creates restaurant record from license data
   - Creates first user as "owner" role

3. **Session Security**
   - Secure cookies (HTTPS only in production)
   - CSRF protection on all POST/PUT/DELETE requests
   - Session invalidated after 1 hour of inactivity

### Password Security

- Hashed with pbkdf2:sha256 (NOT plaintext)
- Minimum 8 characters required
- Password change requires current password verification
- Failed login attempts tracked and account locked after 5 attempts

### Input Validation & Sanitization

All user input is validated and sanitized:

```python
# Validate input
validate_input({
    'required': ['customer_name', 'items'],
    'types': {'items': list, 'amount': float},
    'max_length': {'customer_name': 100}
})

# Sanitize input (remove HTML, limit length, etc.)
customer_name = sanitize_input(customer_name, max_length=100)
```

## 📊 Database Schema

### Tables

1. **Restaurant**: Parent entity (license_id, name, contact, Cloudflare URLs)
2. **User**: Staff members per restaurant (restaurant_id FK, role, password)
3. **Order**: Customer orders (restaurant_id FK, status, items, payment)
4. **Payment**: Payment records (stripe_id, status, amount)
5. **AuditLog**: Compliance trail (action, entity_type, old_value, new_value)

All tables indexed on `(restaurant_id, id)` for fast lookups.

## 🔌 API Endpoints

### Authentication
- `GET /auth/register` - License registration form
- `POST /auth/login` - User login
- `POST /auth/change-password` - Password change
- `GET /auth/logout` - User logout

### Dashboard
- `GET /dashboard` - Main dashboard view
- `GET /api/stats` - Restaurant stats (orders, revenue, pending)

### Orders
- `GET /api/orders` - List restaurant's orders (optional status filter)
- `POST /api/orders` - Create new order
- `GET /api/orders/<id>` - Get specific order (with multi-tenant check)
- `PUT /api/orders/<id>` - Update order status

### QR Codes
- `GET /api/qr-code` - Generate table-specific QR code

### Error Handlers
- `404` - Not found (custom template)
- `403` - Forbidden (custom template)
- `500` - Server error (custom template)

## 💳 Payment Integration (Optional)

To enable Stripe payments:

1. **Set Environment Variables**
   ```bash
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ENABLE_PAYMENTS=True
   ```

2. **Add Webhook Handler** (in app.py)
   ```python
   @app.route('/webhook/stripe', methods=['POST'])
   def stripe_webhook():
       # Handle payment.intent.succeeded event
       # Update order status to PAID
       # Audit log the transaction
   ```

3. **Security Note**: We NEVER store credit card data
   - All card data is handled by Stripe
   - We only store Stripe payment_id and status
   - PCI-DSS compliant by design

## 🐳 Docker Deployment

### Build Image

```bash
cd Docker
docker build -t restaurant-billing:latest .
```

### Run Locally

```bash
docker-compose up
```

This will:
- Start Flask app on port 5000
- Start PostgreSQL on port 5432
- Load environment from .env file

### Production Deployment (Railway/Heroku)

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Deploy web app"
   git push origin main
   ```

2. **Deploy to Railway**
   - Connect GitHub repo
   - Set environment variables in Railway dashboard
   - Database: PostgreSQL on Railway
   - Deploy from main branch

3. **Verify Deployment**
   ```bash
   # Check health
   curl https://your-app.railway.app/

   # Test API
   curl -X GET https://your-app.railway.app/api/stats -H "Cookie: ..."
   ```

## 📈 Scaling to 1000+ Restaurants

This architecture scales horizontally because:

1. **Database Indexed**: Queries filter by `restaurant_id` (fast lookups)
2. **Stateless Sessions**: Can run multiple instances behind load balancer
3. **Redis Optional**: Use for rate limiting across instances
4. **No Per-Restaurant Limits**: Can handle 1000+, limited only by DB connections
5. **Load Distribution**: Each restaurant's orders processed independently

### When to Consider Upgrades

- **1000+ concurrent orders/minute**: Add Redis cache layer
- **10,000+ restaurants**: Shard database by restaurant_id range
- **Peak traffic**: Use CDN for static files (CSS, JS, QR images)

## 🧪 Testing

### Unit Tests

```bash
# Run tests
python -m pytest tests/

# Test authentication
pytest tests/test_auth.py -v

# Test API endpoints
pytest tests/test_api.py -v

# Test multi-tenant isolation
pytest tests/test_security.py -v
```

### Load Testing

```bash
# Install locust
pip install locust

# Run load test
locust -f locustfile.py --host=http://localhost:5000

# Target: 1000 concurrent users
```

## 🚨 Security Checklist

- [ ] Change `SECRET_KEY` in production (use 32-byte random string)
- [ ] Use PostgreSQL in production (not SQLite)
- [ ] Enable HTTPS (required for secure cookies)
- [ ] Set `DATABASE_URL` to production database
- [ ] Set `STRIPE_SECRET_KEY` and webhook secret
- [ ] Configure CORS for frontend (if separate domain)
- [ ] Enable Redis for distributed rate limiting
- [ ] Monitor audit logs for suspicious activity
- [ ] Regular password rotation policy (encourage users)
- [ ] Backup database daily
- [ ] Monitor disk space and CPU usage
- [ ] Set up error alerts (Sentry, DataDog)

## 📝 Logging & Monitoring

All important actions are logged to `AuditLog` table:

```python
# Example: View login attempts
from models import AuditLog
failed_logins = AuditLog.query.filter(
    AuditLog.action == 'LOGIN_FAILED',
    AuditLog.created_at >= today
).all()

# Example: View order changes
order_changes = AuditLog.query.filter(
    AuditLog.entity_type == 'Order',
    AuditLog.entity_id == order_id
).all()
```

## 🆘 Troubleshooting

### Issue: "License verification failed"
- Verify License Server is running and accessible
- Check `LICENSE_SERVER_API` environment variable
- Ensure license key is valid (not expired)

### Issue: "Database connection refused"
- Check `DATABASE_URL` is correct
- Ensure PostgreSQL is running locally or on Railway
- Verify firewall allows database connection

### Issue: "CSRF validation failed"
- Clear browser cookies and try again
- Ensure cookies are enabled
- Check that form includes `{{ csrf_token() }}`

### Issue: "Rate limit exceeded"
- Wait 15 minutes for rate limit to reset
- Or configure Redis for distributed rate limiting
- Or increase rate limit in config.py during dev

## 📞 Support

For issues or questions:
1. Check AuditLog table for detailed action history
2. Review error logs in console output
3. Verify multi-tenant isolation with restaurant_id filter
4. Contact development team with session ID and timestamp

## 📄 License

This software is proprietary and licensed to restaurant owners via the License Server system.

---

**Version**: 1.0.0  
**Last Updated**: March 30, 2025  
**Deployment Status**: Ready for Production
