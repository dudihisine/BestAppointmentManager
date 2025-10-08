# 🚀 Deployment Guide

This guide covers deploying the WhatsApp AI Appointment Manager to production.

## 📋 Prerequisites

- **Server**: Ubuntu 20.04+ or similar Linux distribution
- **Docker & Docker Compose**: For containerized deployment
- **Domain name**: For web interface and webhooks
- **SSL certificate**: For HTTPS (Let's Encrypt recommended)
- **Twilio account**: For WhatsApp messaging

## 🐳 Docker Deployment (Recommended)

### 1. **Prepare Server**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Logout and login to apply Docker group changes
```

### 2. **Clone Repository**
```bash
git clone <your-repo-url>
cd BestAppointmentManager
```

### 3. **Configure Environment**
```bash
# Copy environment template
cp env.example .env

# Edit with production values
nano .env
```

**Production Environment Variables:**
```env
# Database
DATABASE_URL=postgresql://appointment_user:secure_password@postgres:5432/appointment_manager

# Redis
REDIS_URL=redis://redis:6379/0

# Twilio (Production)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_production_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+1234567890

# Application
TIMEZONE_DEFAULT=America/New_York
DEBUG=False
LOG_LEVEL=INFO
SECRET_KEY=your_very_secure_secret_key_here

# Business
BUSINESS_NAME=Your Business Name
BUSINESS_PHONE=+1234567890
BUSINESS_EMAIL=contact@yourbusiness.com
```

### 4. **Deploy with Docker Compose**
```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 5. **Run Database Migrations**
```bash
# Run migrations
docker-compose exec web alembic upgrade head

# Add initial data
docker-compose exec web python add_test_data.py
```

## 🌐 Web Server Configuration

### **Nginx Configuration**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /webhooks/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### **SSL Certificate (Let's Encrypt)**
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

## 📱 WhatsApp Webhook Setup

### 1. **Configure Twilio Webhook**
- Go to Twilio Console → Messaging → Settings → WhatsApp Sandbox
- Set webhook URL: `https://your-domain.com/webhooks/whatsapp`
- Set HTTP method: POST

### 2. **Test Webhook**
```bash
# Test webhook endpoint
curl -X POST https://your-domain.com/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+1234567890&Body=test"
```

## 🔧 Production Optimizations

### **Database Optimization**
```sql
-- Add indexes for better performance
CREATE INDEX idx_appointments_owner_start ON appointments(owner_id, start_dt);
CREATE INDEX idx_appointments_client_start ON appointments(client_id, start_dt);
CREATE INDEX idx_waitlist_owner_window ON waitlist(owner_id, window_start_dt);
```

### **Redis Configuration**
```conf
# redis.conf
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

### **Application Monitoring**
```bash
# Install monitoring tools
sudo apt install htop iotop nethogs

# Monitor application
docker-compose logs -f web
docker-compose logs -f worker
```

## 🔄 Backup Strategy

### **Database Backup**
```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec postgres pg_dump -U appointment_user appointment_manager > backup_$DATE.sql
gzip backup_$DATE.sql
aws s3 cp backup_$DATE.sql.gz s3://your-backup-bucket/
EOF

chmod +x backup.sh

# Schedule daily backups
crontab -e
# Add: 0 2 * * * /path/to/backup.sh
```

### **Application Backup**
```bash
# Backup application files
tar -czf app_backup_$(date +%Y%m%d).tar.gz \
  --exclude=venv \
  --exclude=.git \
  --exclude=__pycache__ \
  /path/to/BestAppointmentManager
```

## 🚨 Monitoring & Alerts

### **Health Checks**
```bash
# Application health
curl https://your-domain.com/health

# Database health
docker-compose exec postgres pg_isready

# Redis health
docker-compose exec redis redis-cli ping
```

### **Log Monitoring**
```bash
# Monitor application logs
tail -f /var/log/nginx/access.log
docker-compose logs -f web

# Monitor error logs
docker-compose logs -f web | grep ERROR
```

## 🔒 Security Checklist

- [ ] **Environment variables** secured
- [ ] **Database passwords** strong and unique
- [ ] **SSL certificates** valid and auto-renewing
- [ ] **Firewall** configured (ports 80, 443 only)
- [ ] **Regular updates** scheduled
- [ ] **Backups** automated and tested
- [ ] **Monitoring** alerts configured
- [ ] **Access logs** reviewed regularly

## 🆘 Troubleshooting

### **Common Issues**

**1. Application won't start**
```bash
# Check logs
docker-compose logs web

# Check environment variables
docker-compose exec web env | grep -E "(DATABASE|REDIS|TWILIO)"
```

**2. Database connection issues**
```bash
# Test database connection
docker-compose exec web python -c "from app.db import test_db_connection; print(test_db_connection())"
```

**3. WhatsApp messages not sending**
```bash
# Check Twilio configuration
docker-compose exec web python -c "from app.config import get_settings; s = get_settings(); print(f'Twilio configured: {bool(s.twilio_account_sid)}')"
```

**4. Background jobs not running**
```bash
# Check worker logs
docker-compose logs worker

# Check Redis connection
docker-compose exec redis redis-cli ping
```

## 📞 Support

- **Documentation**: Check README.md and code comments
- **Issues**: Create GitHub issues for bugs
- **Logs**: Check application and system logs
- **Monitoring**: Use health check endpoints

---

**Your WhatsApp AI Appointment Manager is now ready for production! 🎉**
