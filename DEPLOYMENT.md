# Deployment Guide

This guide covers deploying the Restaurant Billing Web App to production on Railway, Heroku, or similar platforms.

## 🚀 Deploy to Railway (Recommended)

### Prerequisites
- GitHub account with repository pushed
- Railway account (https://railway.app)
- PostgreSQL database

### Step 1: Connect Repository

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click "New Project"
3. Select "Deploy from GitHub"
4. Connect your GitHub account
5. Select the `RestaurantBilling_Web` repository
6. Click "Add Service"

### Step 2: Add PostgreSQL Database

1. Click "Add Service" in Railway
2. Select "PostgreSQL"
3. Connect it as a service
4. Find the connection string in service variables

### Step 3: Configure Environment Variables

In Railway Dashboard, go to Variables and add:

```
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=[Generate with: python -c "import secrets; print(secrets.token_hex(32))"]
LICENSE_SERVER_API=https://web-production-99f80.up.railway.app/api/verify-license
STRIPE_SECRET_KEY=sk_live_[your_stripe_key]
STRIPE_WEBHOOK_SECRET=whsec_[your_webhook_secret]
STRIPE_PUBLISHABLE_KEY=pk_live_[your_public_key]
ENABLE_PAYMENTS=True
ENABLE_QR_GENERATION=True
LOG_LEVEL=INFO
```

Railway automatically provides:
- `DATABASE_URL` (PostgreSQL connection string)
- `REDIS_URL` (Redis connection if Redis service added)

### Step 4: Configure Start Command

In the settings, set the Dockerfile to:
```
Docker/Dockerfile
```

Railway will automatically detect and build from this Dockerfile.

### Step 5: Deploy

1. Railway automatically deploys on push to main branch
2. Monitor deployment status in Dashboard
3. Once green, click "View Logs" to verify startup
4. Access your app at `https://your-app.railway.app`

### Step 6: Initialize Database

Once deployed:

```bash
# SSH into the container or run via Railway CLI
railway shell

# Initialize database
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

---

## 🚀 Deploy to Heroku (Alternative)

### Prerequisites
- Heroku account (https://heroku.com)
- Heroku CLI installed

### Step 1: Create Heroku App

```bash
heroku create restaurant-billing-web
heroku stack:set heroku-22
```

### Step 2: Add Add-ons

```bash
# PostgreSQL
heroku addons:create heroku-postgresql:standard-0

# Redis
heroku addons:create heroku-redis:premium-0
```

### Step 3: Set Environment Variables

```bash
heroku config:set FLASK_ENV=production
heroku config:set FLASK_DEBUG=False
heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
heroku config:set LICENSE_SERVER_API=https://web-production-99f80.up.railway.app/api/verify-license
heroku config:set STRIPE_SECRET_KEY=sk_live_...
heroku config:set STRIPE_WEBHOOK_SECRET=whsec_...
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_live_...
heroku config:set ENABLE_PAYMENTS=True
```

Heroku automatically sets `DATABASE_URL` and `REDIS_URL`.

### Step 4: Deploy

```bash
git push heroku main
```

### Step 5: Initialize Database

```bash
heroku run "python -c 'from app import app, db; app.app_context().push(); db.create_all()'"
```

### Step 6: Monitor

```bash
# View logs
heroku logs --tail

# Check app status
heroku ps
```

---

## 🚀 Deploy to AWS (ECS + RDS)

### Step 1: Prepare AWS Environment

```bash
# Create ECR repository
aws ecr create-repository --repository-name restaurant-billing

# Build and push Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin [account-id].dkr.ecr.us-east-1.amazonaws.com

docker build -f Docker/Dockerfile -t restaurant-billing:latest .
docker tag restaurant-billing:latest [account-id].dkr.ecr.us-east-1.amazonaws.com/restaurant-billing:latest
docker push [account-id].dkr.ecr.us-east-1.amazonaws.com/restaurant-billing:latest
```

### Step 2: Create RDS PostgreSQL Database

```bash
# Create RDS instance
aws rds create-db-instance \
    --db-instance-identifier restaurant-billing-db \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --master-username admin \
    --master-user-password [your-secure-password] \
    --allocated-storage 20 \
    --vpc-security-group-ids sg-xxxxx
```

Get the RDS endpoint and create DATABASE_URL:
```
postgresql://admin:password@[rds-endpoint]:5432/restaurant_billing
```

### Step 3: Create ECS Task Definition

Create `ecs-task-definition.json`:

```json
{
  "family": "restaurant-billing",
  "networkMode": "awsvpc",
  "containerDefinitions": [
    {
      "name": "restaurant-billing",
      "image": "[account-id].dkr.ecr.us-east-1.amazonaws.com/restaurant-billing:latest",
      "portMappings": [{"containerPort": 5000}],
      "environment": [
        {"name": "FLASK_ENV", "value": "production"},
        {"name": "DATABASE_URL", "value": "postgresql://..."}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/restaurant-billing",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

Register task definition:
```bash
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
```

### Step 4: Create ECS Service

```bash
aws ecs create-service \
    --cluster restaurant-billing-cluster \
    --service-name restaurant-billing \
    --task-definition restaurant-billing \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx]}"
```

---

## 📊 Post-Deployment Verification

After deploying to production:

```bash
# 1. Test health endpoint
curl https://your-app.com/
# Should return 302 (redirect to login)

# 2. Test API endpoint
curl https://your-app.com/api/stats \
  -H "Cookie: session=[your_session_id]"
# Should return 401 (unauthorized) or stats JSON

# 3. Check database connection
# Via SSH: python -c "from app import db; print(db.engine.url)"

# 4. Verify HTTPS
curl -I https://your-app.com
# Should show TLS version and security headers

# 5. Monitor logs
# Railway: Dashboard → Logs
# Heroku: heroku logs --tail
# AWS: CloudWatch → Log Groups → /ecs/restaurant-billing
```

---

## 🔒 Security Checklist (Pre-Production)

- [ ] `SECRET_KEY` is randomized (32 bytes)
- [ ] `FLASK_DEBUG=False` in production
- [ ] `DATABASE_URL` points to production PostgreSQL
- [ ] HTTPS is enforced (automatic on Railway/Heroku)
- [ ] Stripe webhook secret is configured
- [ ] License Server API URL is correct
- [ ] Database backups are enabled
- [ ] Error logging is configured (Sentry optional)
- [ ] Redis is secured (no public access)
- [ ] Security headers are verified (HSTS, CSP)
- [ ] Rate limiting is configured
- [ ] Audit logs are monitored

---

## 🚨 Scaling to 1000+ Restaurants

### Database Optimization

1. **Connection Pooling** (configured in production):
   ```python
   # gunicorn workers × 5 connections per worker
   # = 4 workers × 5 = 20 max connections
   ```

2. **Index Verification**:
   ```sql
   -- These indexes must exist
   CREATE INDEX idx_orders_restaurant_id ON orders(restaurant_id);
   CREATE INDEX idx_orders_restaurant_status ON orders(restaurant_id, status);
   CREATE INDEX idx_users_restaurant_id ON users(restaurant_id);
   ```

3. **Query Optimization**:
   - All queries filter by `restaurant_id` first
   - Use pagination (limit 50 orders per request)
   - Cache stats with Redis (10-second TTL)

### Load Balancing

For Railway/Heroku (automatic):
- Scale to multiple dyos/instances
- Load balancer distributes traffic

For AWS (manual):
```bash
# Scale service to 4 tasks
aws ecs update-service \
    --cluster restaurant-billing-cluster \
    --service restaurant-billing \
    --desired-count 4
```

### Redis Caching

Enable Redis to cache:
- Restaurant stats (10 seconds)
- License validation (1 hour)
- QR codes (24 hours)

---

## 📈 Monitoring & Alerts

### Recommended Services

1. **Error Tracking**: Sentry (Flask integration)
   ```python
   import sentry_sdk
   sentry_sdk.init("https://[key]@sentry.io/[project]")
   ```

2. **Uptime Monitoring**: Pingdom or UptimeRobot
   - Monitor `https://your-app.com/api/stats`

3. **Database Monitoring**: 
   - Railway: Built-in dashboard
   - AWS: RDS Performance Insights
   - Heroku: Database dashboard

4. **Log Aggregation**: 
   - Railway: Built-in logs
   - AWS: CloudWatch
   - Heroku: LogDNA (add-on)

---

## 🔄 Rolling Updates

To update production without downtime:

### Railway (Automatic)
```bash
git push origin main
# Railway auto-redeploys
```

### Heroku
```bash
git push heroku main
# Heroku automatically manages rolling update
```

### AWS (Manual)
```bash
# 1. Build and push new image
docker build -f Docker/Dockerfile -t restaurant-billing:v2 .
docker tag restaurant-billing:v2 [account-id].dkr.ecr.us-east-1.amazonaws.com/restaurant-billing:v2
docker push [account-id].dkr.ecr.us-east-1.amazonaws.com/restaurant-billing:v2

# 2. Update task definition
aws ecs register-task-definition ...

# 3. Update service (rolling deployment, 2 min
# 4. Update service (rolling deployment)
aws ecs update-service \
    --cluster restaurant-billing-cluster \
    --service restaurant-billing \
    --task-definition restaurant-billing:2
```

---

## 🆘 Troubleshooting Deployments

### Issue: "Application failed to start"
- Check logs for errors
- Verify DATABASE_URL is correct
- Ensure `db.create_all()` was run
- Verify SECRET_KEY is set

### Issue: "502 Bad Gateway"
- Check if app is running (ps aux | grep gunicorn)
- Verify database connection
- Check memory/CPU limits
- Scale up if needed

### Issue: "Database connection timeout"
- Verify database service is running
- Check security group/firewall rules
- Verify CONNECTION LIMIT on database
- Enable connection pooling

### Issue: "CSRF token validation failed in production"
- Ensure cookies are secure (HTTPS required)
- Check SECRET_KEY matches across instances
- Verify browser accepts cookies

---

**Last Updated**: March 30, 2025  
**Status**: Production Ready
