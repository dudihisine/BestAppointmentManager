# ⚡ Quick Firebase Setup Guide

## 🚀 Deploy Your WhatsApp Bot in 5 Steps

### **Step 1: Install Firebase CLI**
```bash
npm install -g firebase-tools
firebase login
```

### **Step 2: Initialize Firebase Project**
```bash
cd /Users/dudihisine/BestAppointmentManager
firebase init

# Select:
# ✓ Functions (Python)
# ✓ Firestore
# Use existing project or create new one
```

### **Step 3: Configure Twilio Credentials**
```bash
firebase functions:config:set \
  twilio.account_sid="YOUR_TWILIO_ACCOUNT_SID" \
  twilio.auth_token="YOUR_TWILIO_AUTH_TOKEN" \
  twilio.whatsapp_from="whatsapp:+14155238886"
```

### **Step 4: Deploy**
```bash
./deploy.sh

# Or manually:
firebase deploy
```

### **Step 5: Configure Twilio Webhook**

After deployment, you'll get a URL like:
```
https://us-central1-your-project.cloudfunctions.net/whatsapp_webhook
```

**Configure in Twilio:**
1. Go to https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox
2. Set "WHEN A MESSAGE COMES IN" to your webhook URL
3. Method: POST
4. Save

## ✅ Test Your Bot

Send to your WhatsApp Sandbox number:
- `book` - Start booking
- `my appointments` - View appointments  
- `help` - Show menu

## 📊 Monitor

```bash
# View logs
firebase functions:log --only whatsapp_webhook

# Real-time logs
firebase functions:log --follow
```

## 🎯 Your Production Webhook URL

```
https://YOUR-REGION-YOUR-PROJECT.cloudfunctions.net/whatsapp_webhook
```

**This is the URL you'll give to Twilio!**

---

## 🆘 Troubleshooting

**Q: Function not deploying?**
```bash
firebase deploy --only functions --force
```

**Q: Can't see logs?**
```bash
firebase functions:log
```

**Q: Twilio not receiving messages?**
- Check webhook URL in Twilio console
- Verify it's set to POST method
- Check function logs for errors

**Q: Need to update config?**
```bash
firebase functions:config:get
firebase functions:config:set twilio.account_sid="NEW_VALUE"
firebase deploy --only functions
```

---

## 🎉 Success!

Your WhatsApp AI Appointment Manager is now live and ready to accept bookings!
