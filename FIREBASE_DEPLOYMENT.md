# 🚀 Firebase Deployment Guide

## Complete WhatsApp-Only System with Twilio Integration

This guide will deploy your entire appointment management system to Firebase, creating a production-ready WhatsApp bot.

## 📋 Prerequisites

✅ Firebase CLI installed (`npm install -g firebase-tools`)  
✅ Twilio account with WhatsApp sandbox or approved number  
✅ Google Cloud project with billing enabled  
✅ All features from local development working  

## 🔧 Step 1: Initialize Firebase Project

```bash
cd /Users/dudihisine/BestAppointmentManager

# Login to Firebase
firebase login

# Initialize Firebase project
firebase init

# Select the following options:
# ✓ Functions: Configure for Cloud Functions
# ✓ Firestore: Configure Firestore database
# ✓ Hosting: Configure hosting (optional, for status page)
#
# When prompted:
# - Use Python for Functions
# - Use existing project or create new one
# - Accept default file names
```

## 🗄️ Step 2: Set Up Firestore Database

```bash
# Create Firestore database (if not exists)
firebase firestore:databases:create --database="(default)" --location=us-central

# Deploy Firestore rules and indexes
firebase deploy --only firestore
```

## 🔑 Step 3: Configure Environment Variables

```bash
# Set Firebase environment variables for Twilio
firebase functions:config:set \
  twilio.account_sid="YOUR_TWILIO_ACCOUNT_SID" \
  twilio.auth_token="YOUR_TWILIO_AUTH_TOKEN" \
  twilio.whatsapp_from="whatsapp:+14155238886"

# Set timezone
firebase functions:config:set \
  app.timezone="America/New_York" \
  app.business_name="Your Business Name"

# View current config
firebase functions:config:get
```

## 📦 Step 4: Deploy Cloud Functions

```bash
# Deploy all functions
firebase deploy --only functions

# This will deploy:
# - whatsapp_webhook (main Twilio webhook)
# - send_reminders (scheduled reminders)
# - check_waitlist (waitlist notifications)
# - daily_report (daily business reports)
# - health_check (health monitoring)
```

## 🌐 Step 5: Get Your Webhook URL

After deployment, you'll see output like:

```
✔  functions: Finished running predeploy script.
✔  functions[whatsapp_webhook(us-central1)]: Successful create operation.
Function URL (whatsapp_webhook): https://us-central1-YOUR_PROJECT.cloudfunctions.net/whatsapp_webhook
```

**Copy this webhook URL!** You'll need it for Twilio configuration.

## 📱 Step 6: Configure Twilio Webhook

### Option A: WhatsApp Sandbox (Testing)

1. Go to https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox
2. Under "Sandbox Configuration":
   - **WHEN A MESSAGE COMES IN**: `https://us-central1-YOUR_PROJECT.cloudfunctions.net/whatsapp_webhook`
   - **METHOD**: POST
3. Click "Save"

### Option B: Production WhatsApp Number

1. Go to https://console.twilio.com/us1/develop/sms/services
2. Select your WhatsApp-enabled number
3. Under "Messaging Configuration":
   - **WHEN A MESSAGE COMES IN**: `https://us-central1-YOUR_PROJECT.cloudfunctions.net/whatsapp_webhook`
   - **METHOD**: POST
4. Click "Save"

## 🏗️ Step 7: Initialize Database with Sample Data

Create an initialization script:

```bash
# Create setup script
cat > setup_firestore.py << 'EOF'
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, time

# Initialize Firebase
cred = credentials.Certificate('path/to/serviceAccountKey.json')
firebase_admin.initialize_app(cred)

db = firestore.client()

# Create sample owner
owner_ref = db.collection('owners').document()
owner_ref.set({
    'name': 'David\'s Barbershop',
    'phone': '+1234567890',  # Owner's phone for /owner commands
    'timezone': 'America/New_York',
    'default_intent': 'balanced',
    'created_at': datetime.utcnow()
})

owner_id = owner_ref.id

# Create services
services = [
    {
        'owner_id': owner_id,
        'name': 'Haircut',
        'duration_min': 30,
        'buffer_min': 10,
        'price_cents': 3000,
        'active': True
    },
    {
        'owner_id': owner_id,
        'name': 'Haircut + Beard',
        'duration_min': 45,
        'buffer_min': 15,
        'price_cents': 4000,
        'active': True
    },
    {
        'owner_id': owner_id,
        'name': 'Quick Trim',
        'duration_min': 15,
        'buffer_min': 5,
        'price_cents': 1500,
        'active': True
    }
]

for service in services:
    db.collection('services').add(service)

# Create settings
db.collection('settings').document(owner_id).set({
    'business_hours_start': '09:00',
    'business_hours_end': '18:00',
    'quiet_hours_start': '22:00',
    'quiet_hours_end': '08:00',
    'max_daily_appointments': 20,
    'allow_same_day_booking': True,
    'min_advance_booking_hours': 1
})

print("✅ Database initialized successfully!")
print(f"Owner ID: {owner_id}")
EOF

# Run setup
python setup_firestore.py
```

## ⏰ Step 8: Set Up Cloud Scheduler (Optional)

For automated reminders and reports:

```bash
# Enable Cloud Scheduler API
gcloud services enable cloudscheduler.googleapis.com

# Create reminder job (runs every hour)
gcloud scheduler jobs create http send-reminders \
  --schedule="0 * * * *" \
  --uri="https://us-central1-YOUR_PROJECT.cloudfunctions.net/send_reminders" \
  --http-method=POST

# Create waitlist check job (runs every 30 minutes)
gcloud scheduler jobs create http check-waitlist \
  --schedule="*/30 * * * *" \
  --uri="https://us-central1-YOUR_PROJECT.cloudfunctions.net/check_waitlist" \
  --http-method=POST

# Create daily report job (runs at 8 AM daily)
gcloud scheduler jobs create http daily-report \
  --schedule="0 8 * * *" \
  --time-zone="America/New_York" \
  --uri="https://us-central1-YOUR_PROJECT.cloudfunctions.net/daily_report" \
  --http-method=POST
```

## 🧪 Step 9: Test Your WhatsApp Bot

### Test with Twilio Sandbox:

1. Send the sandbox join code to your WhatsApp Sandbox number
2. Send: `book`
3. Follow the booking flow!

### Test Commands:

**Client Commands:**
- `book` - Start booking process
- `my appointments` - View appointments
- `help` - Show help menu

**Owner Commands** (from owner's phone):
- `/owner schedule` - View today's schedule
- `/owner mode` - Check current mode
- `/owner stats` - View statistics
- `/owner waitlist` - View waitlist

## 📊 Step 10: Monitor Your Deployment

```bash
# View function logs
firebase functions:log --only whatsapp_webhook

# View all logs
firebase functions:log

# Monitor in real-time
firebase functions:log --only whatsapp_webhook --follow
```

## 🔗 Your Production URLs

After deployment, you'll have these endpoints:

| Function | URL |
|----------|-----|
| **Twilio Webhook** | `https://us-central1-YOUR_PROJECT.cloudfunctions.net/whatsapp_webhook` |
| **Health Check** | `https://us-central1-YOUR_PROJECT.cloudfunctions.net/health_check` |
| **Send Reminders** | `https://us-central1-YOUR_PROJECT.cloudfunctions.net/send_reminders` |
| **Check Waitlist** | `https://us-central1-YOUR_PROJECT.cloudfunctions.net/check_waitlist` |
| **Daily Report** | `https://us-central1-YOUR_PROJECT.cloudfunctions.net/daily_report` |

## 🎯 Quick Deployment Commands

```bash
# Full deployment
firebase deploy

# Deploy only functions
firebase deploy --only functions

# Deploy only Firestore
firebase deploy --only firestore

# Deploy specific function
firebase deploy --only functions:whatsapp_webhook
```

## 🆘 Troubleshooting

### Issue: Function not deploying

```bash
# Check logs
firebase functions:log

# Redeploy
firebase deploy --only functions --force
```

### Issue: Twilio webhook not working

1. Check webhook URL in Twilio console
2. Verify POST method is selected
3. Check function logs: `firebase functions:log --only whatsapp_webhook`

### Issue: Database not accessible

```bash
# Check Firestore rules
firebase firestore:rules

# Update rules if needed
firebase deploy --only firestore:rules
```

### Issue: Environment variables not set

```bash
# View current config
firebase functions:config:get

# Reset config
firebase functions:config:unset twilio
firebase functions:config:set twilio.account_sid="YOUR_SID"
```

## 📈 Scaling & Performance

- **Free Tier**: 2M function invocations/month
- **Firestore**: 50K reads, 20K writes, 20K deletes per day (free)
- **Upgrade**: For production use, upgrade to Blaze plan (pay-as-you-go)

## 🎉 Success!

Your WhatsApp AI Appointment Manager is now live! 🚀

**Webhook URL:** `https://us-central1-YOUR_PROJECT.cloudfunctions.net/whatsapp_webhook`

Configure this in Twilio, and you're ready to accept real WhatsApp bookings!

---

## 📞 Support

- **Firebase Docs**: https://firebase.google.com/docs
- **Twilio Docs**: https://www.twilio.com/docs/whatsapp
- **Function Logs**: `firebase functions:log`
