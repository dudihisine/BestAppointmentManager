#!/bin/bash

# WhatsApp Flow Testing Script
# This simulates a complete booking conversation

echo "🧪 Testing Complete WhatsApp Booking Flow"
echo "=========================================="

BASE_URL="http://localhost:8000/webhooks/whatsapp"

echo "1. 👤 Client starts booking..."
curl -s -X POST $BASE_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=book&MessageSid=test1"

sleep 1

echo "2. 👤 Client provides name..."
curl -s -X POST $BASE_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=John Doe&MessageSid=test2"

sleep 1

echo "3. 👤 Client selects service (Haircut)..."
curl -s -X POST $BASE_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=1&MessageSid=test3"

sleep 1

echo "4. 👤 Client chooses time preference (Tomorrow)..."
curl -s -X POST $BASE_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=2&MessageSid=test4"

sleep 1

echo "5. 👤 Client confirms time slot..."
curl -s -X POST $BASE_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972509876543&WaId=972509876543&Body=1&MessageSid=test5"

sleep 1

echo ""
echo "6. 👔 Owner checks summary..."
curl -s -X POST $BASE_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972501234567&WaId=972501234567&Body=summary&MessageSid=test6"

sleep 1

echo ""
echo "7. 👔 Owner gets optimization suggestions..."
curl -s -X POST $BASE_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+972501234567&WaId=972501234567&Body=optimize&MessageSid=test7"

echo ""
echo "✅ Complete flow tested! Check the FastAPI logs to see all the processing."
echo "📱 The system is ready for real WhatsApp testing!"
