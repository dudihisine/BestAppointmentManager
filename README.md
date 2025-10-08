# 🤖 WhatsApp AI Appointment Manager

A complete, production-ready appointment management system with AI-powered optimization, WhatsApp integration, and automated background jobs.

## ✨ Features

### 📱 **WhatsApp-First Interface**
- **Natural language processing** - Understands "book haircut", "show appointments", etc.
- **Smart session management** - Handles interrupted conversations gracefully
- **Professional message templates** - Consistent, branded communication
- **Multi-step booking flows** - Service selection, time preferences, confirmation

### 🎯 **Appointment Management**
- **Complete booking system** - Service selection, time slots, confirmation
- **Reschedule functionality** - Change existing appointments
- **Cancellation system** - Cancel with gap-fill optimization
- **Appointment viewing** - Client can see all their bookings

### 🤖 **AI-Powered Optimization**
- **Intent-based scheduling** - Max Profit, Balanced, Free Time modes
- **Gap-fill automation** - Automatically fills cancelled slots
- **Waitlist management** - Priority-based notifications
- **Smart suggestions** - Mode-specific optimization recommendations

### ⏰ **Background Jobs & Automation**
- **Appointment reminders** - 24h, 2h, 30min before
- **Waitlist notifications** - Instant alerts when slots open
- **Daily reports** - Owner performance summaries
- **Redis Queue integration** - Scalable background processing

### 🌐 **Web Interface**
- **Owner dashboard** - Multi-date view, AI suggestions, waitlist management
- **Client booking interface** - Easy online booking
- **WhatsApp test interface** - Local testing without Twilio limits
- **Message capture system** - See actual bot responses

## 🚀 Quick Start

### 1. **Clone and Setup**
```bash
git clone <your-repo-url>
cd BestAppointmentManager
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. **Environment Configuration**
```bash
# Copy the example environment file
cp env.example .env

# Edit .env with your actual values
nano .env
```

### 3. **Database Setup**
```bash
# Start PostgreSQL and Redis with Docker
docker-compose up -d

# Run database migrations
alembic upgrade head

# Add test data
python add_test_data.py
```

### 4. **Start the System**
```bash
# Terminal 1: Start the main application
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start the background worker
python worker.py
```

### 5. **Access the Interfaces**
- **🌐 Web Interface:** http://localhost:8000
- **📱 WhatsApp Test:** http://localhost:8000/messages
- **👨‍💼 Owner Dashboard:** http://localhost:8000/owner/dashboard

## 🧪 Testing

### **Run All Tests**
```bash
python test_complete_system.py
```

### **Test Specific Features**
```bash
# Test background jobs
python test_background_jobs.py

# Test natural language processing
python test_natural_language.py

# Test individual components
python -m pytest tests/
```

## 📊 System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   WhatsApp      │    │   Web Interface │    │   Background    │
│   Interface     │    │   (FastAPI)     │    │   Jobs (RQ)     │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────┴─────────────┐
                    │      Business Logic       │
                    │  • Scheduler              │
                    │  • Optimizer              │
                    │  • Waitlist Manager       │
                    │  • Policy Enforcer        │
                    └─────────────┬─────────────┘
                                 │
                    ┌─────────────┴─────────────┐
                    │      Data Layer           │
                    │  • PostgreSQL             │
                    │  • Redis (Sessions)       │
                    │  • SQLAlchemy ORM         │
                    └───────────────────────────┘
```

## 🔧 Configuration

### **Environment Variables**
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `TWILIO_ACCOUNT_SID` - Twilio account SID
- `TWILIO_AUTH_TOKEN` - Twilio auth token
- `TWILIO_WHATSAPP_FROM` - WhatsApp sender number
- `TIMEZONE_DEFAULT` - Default timezone
- `DEBUG` - Debug mode (True/False)

### **Business Settings**
- **Intent Modes**: Max Profit, Balanced, Free Time
- **Service Configuration**: Duration, price, buffer time
- **Business Hours**: Start/end times, quiet hours
- **Policies**: Cancellation, rescheduling rules

## 📱 WhatsApp Integration

### **Test Mode (Default)**
- Messages are captured and displayed in web interface
- No actual WhatsApp messages sent
- Perfect for development and testing

### **Production Mode**
- Configure Twilio credentials in `.env`
- Real WhatsApp messages sent to clients
- Webhook endpoint: `/webhooks/whatsapp`

## 🎯 Usage Examples

### **For Business Owners**
1. **📊 View daily schedules** with AI optimization suggestions
2. **📋 Manage waitlists** with priority-based notifications
3. **📈 Get daily reports** with performance metrics
4. **⚙️ Change intent modes** (Max Profit, Balanced, Free Time)
5. **🔄 Handle cancellations** with automatic gap-fill

### **For Clients**
1. **📅 Book appointments** via natural language
2. **🔄 Reschedule** existing appointments
3. **❌ Cancel** appointments easily
4. **📋 View** all upcoming appointments
5. **📱 Get reminders** automatically

## 🚀 Production Deployment

### **Docker Deployment**
```bash
# Build and run with Docker Compose
docker-compose -f docker-compose.prod.yml up -d
```

### **Manual Deployment**
1. Set up PostgreSQL and Redis servers
2. Configure environment variables
3. Run database migrations
4. Start the application and worker processes
5. Set up reverse proxy (nginx)
6. Configure SSL certificates

## 📈 Monitoring & Logging

- **Application logs** - Structured logging with different levels
- **Performance metrics** - Response times, error rates
- **Background job monitoring** - Queue status, job failures
- **Database monitoring** - Connection pools, query performance

## 🔒 Security

- **Environment variables** - Sensitive data in `.env` files
- **Database security** - Connection encryption, user permissions
- **API security** - Input validation, rate limiting
- **Session management** - Secure session storage in Redis

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Documentation** - Check this README and code comments
- **Issues** - Create GitHub issues for bugs or feature requests
- **Testing** - Run the test suite to verify functionality

## 🎉 Acknowledgments

- **FastAPI** - Modern web framework
- **PostgreSQL** - Reliable database
- **Redis** - Fast caching and job queue
- **Twilio** - WhatsApp messaging API
- **SQLAlchemy** - Python ORM

---

**Built with ❤️ for service businesses who want to automate their appointment management.**
