# 🧪 Testing Guide for WhatsApp Appointment Assistant

This guide shows you how to test the appointment system without needing actual WhatsApp/Twilio setup.

## 🚀 Quick Start

### 1. Setup Test Environment

```bash
# Make sure containers are running
docker compose up -d

# Activate virtual environment
source venv/bin/activate

# Create test data (owner + services)
python setup_test_data.py

# Start the server
uvicorn app.main:app --reload
```

### 2. Run Automated Tests

```bash
# In a new terminal
python test_webhook.py
```

This will simulate complete conversation flows for both owners and clients.

## 📱 Manual Testing

### Test Owner Flow

**Owner Phone:** `+972501234567` (this is the test owner)

```bash
# Test owner setup
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972501234567&WaId=972501234567&Body=setup&MessageSid=test1"

# Test daily summary
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972501234567&WaId=972501234567&Body=summary&MessageSid=test2"

# Test help
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972501234567&WaId=972501234567&Body=help&MessageSid=test3"
```

### Test Client Flow

**Client Phone:** Any other number (e.g., `+972509876543`)

```bash
# Start booking
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=book&MessageSid=test4"

# Continue with name
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=John Doe&MessageSid=test5"

# Select service (1 = Haircut)
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=1&MessageSid=test6"
```

## 🔍 What to Look For

### Server Logs
Watch your FastAPI server terminal for:
- ✅ Message routing (owner vs client)
- ✅ Session state changes
- ✅ Database operations
- ✅ Response messages (these would be sent via WhatsApp)

### Database State
```bash
# Check what's in the database
python setup_test_data.py show
```

### Redis Sessions
```bash
# Connect to Redis and check sessions
docker exec -it bestappointmentmanager-redis-1 redis-cli
> KEYS whatsapp_session:*
> GET whatsapp_session:+972509876543
```

## 🧪 Test Scenarios

### Owner Scenarios
1. **First-time setup**: `setup` → complete wizard
2. **Daily routine**: `summary` → see today's schedule
3. **Settings change**: `intent profit` → change optimization mode
4. **Help system**: `help` → see all commands

### Client Scenarios
1. **New client booking**: `book` → name → service → time
2. **Returning client**: `appointments` → see existing bookings
3. **Session cancellation**: Start booking → `cancel` → exit flow
4. **Invalid inputs**: Try wrong service numbers, invalid names

### Session Management
1. **Multi-step flows**: Start booking, continue conversation
2. **Session expiry**: Wait 30+ minutes, try to continue
3. **Context switching**: Switch between different commands
4. **Error recovery**: Send invalid inputs, recover gracefully

## 🐛 Debugging Tips

### Check Health Status
```bash
curl http://localhost:8000/health | python -m json.tool
```

### View Logs with Filtering
```bash
# Start server with more detailed logs
uvicorn app.main:app --reload --log-level debug

# Or filter logs
uvicorn app.main:app --reload | grep -E "(INFO|ERROR|WARNING)"
```

### Database Debugging
```bash
# Connect to PostgreSQL
docker exec -it bestappointmentmanager-db-1 psql -U app -d scheduler

# Check tables
\dt

# Check owners
SELECT * FROM owners;

# Check sessions in Redis
docker exec -it bestappointmentmanager-redis-1 redis-cli KEYS "*"
```

### Common Issues

**"python-multipart not installed"**
```bash
pip install python-multipart==0.0.6
```

**"Database connection failed"**
```bash
docker compose up -d  # Make sure containers are running
```

**"No owner found"**
```bash
python setup_test_data.py  # Create test data
```

## 📊 Expected Responses

### Owner Setup Flow
1. **"setup"** → Timezone question
2. **"Asia/Jerusalem"** → Work days question  
3. **"1"** → Work hours question
4. **"9:00-17:00"** → Intent mode question
5. **"2"** → Reminders question
6. **"24,2"** → Lead time question
7. **"60"** → Setup complete confirmation

### Client Booking Flow
1. **"book"** → Name request
2. **"John Doe"** → Service selection menu
3. **"1"** → Time preference question
4. **"2"** → Available slots (placeholder)
5. **"1"** → Booking confirmation (placeholder)

## 🔄 Continuous Testing

### Auto-reload Testing
The server runs with `--reload`, so you can:
1. Make code changes
2. Server automatically restarts
3. Re-run tests immediately
4. See changes in real-time

### Test Data Reset
```bash
# Reset database (careful - deletes all data!)
docker compose down
docker compose up -d
alembic upgrade head
python setup_test_data.py
```

## 🎯 Success Criteria

Your system is working correctly if:

- ✅ Health endpoint shows all services connected
- ✅ Owner messages route to owner flow
- ✅ Client messages route to client flow  
- ✅ Sessions persist between messages
- ✅ Multi-step conversations work smoothly
- ✅ Error handling is graceful
- ✅ Database operations succeed
- ✅ Redis sessions are created/updated

## 🚀 Next Steps

Once basic testing works:

1. **Add real Twilio credentials** to `.env`
2. **Use ngrok** to expose localhost: `ngrok http 8000`
3. **Set Twilio webhook** to `https://your-ngrok-url.ngrok.io/webhooks/whatsapp`
4. **Test with real WhatsApp** messages

The system is designed to work identically with real WhatsApp messages once Twilio is configured!
