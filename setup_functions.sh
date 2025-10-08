#!/bin/bash
# Setup script for Firebase Functions

echo "🔧 Setting up Firebase Functions environment..."

cd functions

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and install dependencies
echo "Installing dependencies..."
source venv/bin/activate
python3.12 -m pip install --upgrade pip
python3.12 -m pip install -r requirements.txt

echo "✅ Setup complete!"
echo ""
echo "Now run: firebase deploy"
