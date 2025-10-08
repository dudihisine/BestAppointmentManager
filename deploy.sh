#!/bin/bash

# Firebase Deployment Script
# This script deploys your WhatsApp Appointment Manager to Firebase

set -e  # Exit on error

echo "🚀 Starting Firebase Deployment..."
echo "=================================="

# Check if Firebase CLI is installed
if ! command -v firebase &> /dev/null; then
    echo "❌ Firebase CLI not found!"
    echo "Install it with: npm install -g firebase-tools"
    exit 1
fi

echo "✅ Firebase CLI found"

# Check if logged in
if ! firebase projects:list &> /dev/null; then
    echo "🔑 Please login to Firebase..."
    firebase login
fi

echo "✅ Firebase authentication successful"

# Initialize Firebase if not done
if [ ! -f ".firebaserc" ]; then
    echo "🔧 Initializing Firebase project..."
    firebase init
fi

# Deploy Firestore rules and indexes
echo "📁 Deploying Firestore configuration..."
firebase deploy --only firestore

# Deploy Cloud Functions
echo "⚡ Deploying Cloud Functions..."
firebase deploy --only functions

echo ""
echo "=================================="
echo "✅ Deployment Complete!"
echo "=================================="
echo ""
echo "📱 Your Twilio Webhook URL:"
echo "   https://YOUR-REGION-YOUR-PROJECT.cloudfunctions.net/whatsapp_webhook"
echo ""
echo "🔧 Next Steps:"
echo "   1. Copy the webhook URL from the output above"
echo "   2. Go to Twilio Console: https://console.twilio.com"
echo "   3. Configure WhatsApp webhook with your URL"
echo "   4. Test by sending 'book' to your WhatsApp number"
echo ""
echo "📊 View logs:"
echo "   firebase functions:log --only whatsapp_webhook"
echo ""
echo "🎉 Your WhatsApp bot is now live!"
echo ""
