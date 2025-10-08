#!/bin/bash
# Firebase initialization script

echo "🔥 Initializing Firebase project..."

# Check if Firebase CLI is installed
if ! command -v firebase &> /dev/null; then
    echo "❌ Firebase CLI not found. Installing..."
    npm install -g firebase-tools
fi

# Login to Firebase
echo "🔐 Logging in to Firebase..."
firebase login

# Initialize project
echo "⚙️ Initializing Firebase project..."
firebase init

echo "✅ Firebase initialization complete!"
echo ""
echo "Next steps:"
echo "1. Configure environment variables"
echo "2. Deploy with: firebase deploy"
echo "3. Set up Twilio webhook"
