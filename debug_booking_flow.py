#!/usr/bin/env python3
"""
Debug the booking flow to see why "book" command is not working.
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

async def debug_booking_flow():
    """Debug why the booking flow is not starting."""
    print("🔍 Debugging Booking Flow")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        # Test phone number
        phone = "+1234567890"
        
        # Clear any existing session
        clear_session(phone)
        clear_captured_messages(phone)
        
        # Check if owner exists
        owner = db.query(Owner).first()
        print(f"📊 Owner found: {owner.name if owner else 'None'}")
        
        # Check services
        if owner:
            services = db.query(Service).filter(
                Service.owner_id == owner.id,
                Service.active == True
            ).all()
            print(f"📊 Active services: {len(services)}")
            for service in services:
                print(f"  • {service.name} ({service.duration_min}min, ${service.price_cents/100:.0f})")
        
        # Test different command variations
        test_commands = [
            "book",
            "**book**",
            "Book",
            "BOOK",
            "appointment",
            "schedule"
        ]
        
        for command in test_commands:
            print(f"\n🧪 Testing command: '{command}'")
            
            # Clear previous state
            clear_session(phone)
            clear_captured_messages(phone)
            enable_test_mode()
            
            try:
                # Send the command
                await handle_client_message(phone, command, db)
                
                # Check session state
                session = get_session(phone)
                if session:
                    print(f"  ✅ Session created: {session.state_type}/{session.step}")
                    print(f"  📊 Session data: {session.data}")
                else:
                    print(f"  ❌ No session created")
                
                # Check captured messages
                captured = get_captured_messages(phone)
                print(f"  📱 Captured messages: {len(captured)}")
                for i, msg in enumerate(captured):
                    print(f"    {i+1}. {msg['content'][:100]}...")
                
            except Exception as e:
                print(f"  ❌ Error: {e}")
        
        print(f"\n🔍 Final Test - Check if client exists:")
        client = db.query(Client).filter(Client.phone == phone).first()
        if client:
            print(f"  ✅ Client exists: {client.name} (ID: {client.id})")
        else:
            print(f"  ❌ No client found for {phone}")
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(debug_booking_flow())
