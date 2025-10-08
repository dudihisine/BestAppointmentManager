#!/usr/bin/env python3
"""
Test the WhatsApp message capture system.
"""

import asyncio
import sys
import os

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.test_messaging import (
    enable_test_mode, disable_test_mode, get_captured_messages, 
    clear_captured_messages, capture_message, get_message_count
)
from app.services.messaging import send_whatsapp

async def test_message_capture():
    """Test the message capture system."""
    print("🧪 Testing WhatsApp Message Capture")
    print("=" * 40)
    
    # Test 1: Normal mode (should not capture)
    print("\n1️⃣ Testing normal mode (should not capture):")
    disable_test_mode()
    await send_whatsapp("+1234567890", "This should not be captured")
    captured = get_captured_messages("+1234567890")
    print(f"   Captured messages: {len(captured)}")
    assert len(captured) == 0, "Messages should not be captured in normal mode"
    print("   ✅ Normal mode works correctly")
    
    # Test 2: Test mode (should capture)
    print("\n2️⃣ Testing test mode (should capture):")
    enable_test_mode()
    await send_whatsapp("+1234567890", "Hello! This is a test message.")
    await send_whatsapp("whatsapp:+1234567890", "This is a second test message.")
    captured = get_captured_messages("+1234567890")
    print(f"   Captured messages: {len(captured)}")
    assert len(captured) == 2, f"Expected 2 messages, got {len(captured)}"
    print(f"   Message 1: {captured[0]['content']}")
    print(f"   Message 2: {captured[1]['content']}")
    print("   ✅ Test mode captures messages correctly")
    
    # Test 3: Clear messages
    print("\n3️⃣ Testing message clearing:")
    clear_captured_messages("+1234567890")
    captured = get_captured_messages("+1234567890")
    print(f"   Captured messages after clear: {len(captured)}")
    assert len(captured) == 0, "Messages should be cleared"
    print("   ✅ Message clearing works correctly")
    
    # Test 4: Multiple phone numbers
    print("\n4️⃣ Testing multiple phone numbers:")
    await send_whatsapp("+1111111111", "Message for phone 1")
    await send_whatsapp("+1111111111", "Another message for phone 1")
    await send_whatsapp("+2222222222", "Message for phone 2")
    
    phone1_messages = get_captured_messages("+1111111111")
    phone2_messages = get_captured_messages("+2222222222")
    
    print(f"   Phone 1 messages: {len(phone1_messages)}")
    print(f"   Phone 2 messages: {len(phone2_messages)}")
    
    assert len(phone1_messages) == 2, f"Expected 2 messages for phone 1, got {len(phone1_messages)}"
    assert len(phone2_messages) == 1, f"Expected 1 message for phone 2, got {len(phone2_messages)}"
    print("   ✅ Multiple phone numbers work correctly")
    
    # Clean up
    disable_test_mode()
    clear_captured_messages()
    
    print("\n🎉 All tests passed!")
    print("✅ WhatsApp message capture system is working correctly")

if __name__ == "__main__":
    asyncio.run(test_message_capture())
