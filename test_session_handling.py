#!/usr/bin/env python3
"""
Test the improved session handling with natural language detection.
"""

import asyncio
import sys
import os

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Service, Client, Appointment, AppointmentStatus
from app.routes.client import handle_client_message
from app.services.test_messaging import enable_test_mode, get_captured_messages, clear_captured_messages
from app.utils.session import get_session, clear_session, set_session

async def test_session_handling():
    """Test improved session handling."""
    print("🧪 Testing Session Handling")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        phone = "+1234567890"
        
        # Clear any existing session and messages
        clear_session(phone)
        clear_captured_messages(phone)
        enable_test_mode()
        
        # Simulate a stuck session (like the one we found)
        print("📋 Step 1: Simulating stuck session...")
        set_session(phone, 'client_cancel', 'select_appointment', {
            'appointments': [{'id': 17}, {'id': 20}]
        })
        
        print("📋 Step 2: Sending natural language message...")
        await handle_client_message(phone, "Hi! I'd like to book a Haircut appointment. When do you have availability?", db)
        
        # Check the response
        captured = get_captured_messages(phone)
        print(f"\n📱 Captured {len(captured)} messages:")
        
        for i, msg in enumerate(captured):
            print(f"  {i+1}. {msg['content']}")
            
            # Check if it offers to help with the stuck session
            if "middle of a" in msg['content'] and "process" in msg['content']:
                print(f"  ✅ SUCCESS: Detected stuck session and offered help!")
            elif "restart" in msg['content'].lower():
                print(f"  ✅ SUCCESS: Offered restart option!")
        
        # Test restart command
        print("\n📋 Step 3: Testing restart command...")
        clear_captured_messages(phone)
        await handle_client_message(phone, "restart", db)
        
        captured = get_captured_messages(phone)
        print(f"\n📱 Captured {len(captured)} messages after restart:")
        
        for i, msg in enumerate(captured):
            print(f"  {i+1}. {msg['content']}")
            
            if "Starting fresh" in msg['content']:
                print(f"  ✅ SUCCESS: Restart command worked!")
        
        # Check if session was cleared
        session = get_session(phone)
        if not session:
            print("  ✅ SUCCESS: Session was cleared!")
        else:
            print(f"  ❌ BUG: Session still exists: {session.state_type}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        clear_session(phone)
        db.close()

if __name__ == "__main__":
    asyncio.run(test_session_handling())
