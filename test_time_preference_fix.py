#!/usr/bin/env python3
"""
Test the time preference fix to ensure "2" maps to "tomorrow" correctly.
"""

import asyncio
import sys
import os

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Service, Client
from app.routes.client import handle_client_message
from app.services.test_messaging import enable_test_mode, get_captured_messages, clear_captured_messages
from app.utils.session import get_session, clear_session

async def test_time_preference_fix():
    """Test that time preference numbers are mapped correctly."""
    print("🧪 Testing Time Preference Fix")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        phone = "+1234567890"
        
        # Clear any existing session and messages
        clear_session(phone)
        clear_captured_messages(phone)
        enable_test_mode()
        
        print("📋 Step 1: Start booking flow")
        await handle_client_message(phone, "book", db)
        
        print("📋 Step 2: Provide name")
        await handle_client_message(phone, "Test User", db)
        
        print("📋 Step 3: Select service (Haircut)")
        await handle_client_message(phone, "1", db)
        
        print("📋 Step 4: Select time preference (2 = Tomorrow)")
        clear_captured_messages(phone)  # Clear previous messages
        await handle_client_message(phone, "2", db)
        
        # Check the captured response
        captured = get_captured_messages(phone)
        print(f"\n📱 Captured {len(captured)} messages after selecting '2' for tomorrow:")
        
        for i, msg in enumerate(captured):
            print(f"  {i+1}. {msg['content'][:100]}...")
            
            # Check if the message mentions "Tomorrow" instead of "Today"
            if "Tomorrow" in msg['content']:
                print(f"  ✅ SUCCESS: Found 'Tomorrow' in response!")
            elif "Today" in msg['content']:
                print(f"  ❌ BUG: Still showing 'Today' instead of 'Tomorrow'")
            
        # Check session state
        session = get_session(phone)
        if session:
            print(f"\n📊 Session state: {session.state_type}/{session.step}")
            print(f"📊 Session data: {session.data}")
            
            preference = session.data.get('preference')
            if preference == 'tomorrow':
                print(f"  ✅ SUCCESS: Preference correctly set to 'tomorrow'")
            else:
                print(f"  ❌ BUG: Preference is '{preference}', should be 'tomorrow'")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        clear_session(phone)
        db.close()

if __name__ == "__main__":
    asyncio.run(test_time_preference_fix())
