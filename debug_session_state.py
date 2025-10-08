#!/usr/bin/env python3
"""
Debug the current session state for a phone number.
"""

import asyncio
import sys
import os

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.utils.session import get_session, clear_session
from app.services.test_messaging import enable_test_mode, get_captured_messages, clear_captured_messages

async def debug_session_state():
    """Debug current session state."""
    print("🔍 Debugging Session State")
    print("=" * 40)
    
    phone = "+1234567890"
    
    # Check current session
    session = get_session(phone)
    if session:
        print(f"📱 Active session found for {phone}:")
        print(f"  - State Type: {session.state_type}")
        print(f"  - Step: {session.step}")
        print(f"  - Data: {session.data}")
        print(f"  - Created: {session.created_at}")
        
        # Clear the session to reset
        print("\n🧹 Clearing session...")
        clear_session(phone)
        print("✅ Session cleared")
    else:
        print(f"📱 No active session for {phone}")

if __name__ == "__main__":
    asyncio.run(debug_session_state())
