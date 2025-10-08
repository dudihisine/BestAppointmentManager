#!/usr/bin/env python3
"""
Test natural language command detection.
"""

import asyncio
import sys
import os

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.routes.client import handle_client_message
from app.services.test_messaging import enable_test_mode, get_captured_messages, clear_captured_messages
from app.utils.session import clear_session

async def test_natural_language():
    """Test natural language command detection."""
    print("🧪 Testing Natural Language Commands")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        phone = "+1234567890"
        
        # Clear any existing session and messages
        clear_session(phone)
        clear_captured_messages(phone)
        enable_test_mode()
        
        test_cases = [
            ("Hi! Can you show me my upcoming appointments?", "appointments"),
            ("I'd like to book a Haircut appointment", "booking"),
            ("I need to cancel my appointment", "cancel"),
            ("Can I reschedule my appointment?", "reschedule"),
            ("cancel", "cancel"),
            ("appointments", "appointments"),
        ]
        
        for message, expected_action in test_cases:
            print(f"\n📋 Testing: '{message}'")
            clear_captured_messages(phone)
            
            await handle_client_message(phone, message, db)
            
            captured = get_captured_messages(phone)
            if captured:
                response = captured[0]['content']
                print(f"  📱 Response: {response[:100]}...")
                
                # Check if response matches expected action
                if expected_action == "appointments" and ("appointments" in response.lower() or "bookings" in response.lower()):
                    print(f"  ✅ SUCCESS: Correctly detected appointment request")
                elif expected_action == "booking" and ("name" in response.lower() or "booking" in response.lower()):
                    print(f"  ✅ SUCCESS: Correctly detected booking request")
                elif expected_action == "cancel" and ("cancel" in response.lower() and "appointment" in response.lower()):
                    print(f"  ✅ SUCCESS: Correctly detected cancel request")
                elif expected_action == "reschedule" and ("reschedule" in response.lower() or "change" in response.lower()):
                    print(f"  ✅ SUCCESS: Correctly detected reschedule request")
                else:
                    print(f"  ❌ UNEXPECTED: Response doesn't match expected action")
            else:
                print(f"  ❌ ERROR: No response captured")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        clear_session(phone)
        db.close()

if __name__ == "__main__":
    asyncio.run(test_natural_language())
