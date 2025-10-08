#!/usr/bin/env python3
"""
Debug the cancel flow to see why it's not working.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Service, Client, Appointment, AppointmentStatus
from app.routes.client import start_cancel_flow
from app.services.test_messaging import enable_test_mode, get_captured_messages, clear_captured_messages

async def debug_cancel_flow():
    """Debug why cancel flow is not working."""
    print("🔍 Debugging Cancel Flow")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        phone = "+1234567890"
        
        # Clear any existing messages
        clear_captured_messages(phone)
        enable_test_mode()
        
        # Check what appointments exist for this client
        client = db.query(Client).filter(Client.phone == phone).first()
        if not client:
            print("❌ No client found for phone:", phone)
            return
        
        print(f"👤 Client found: {client.name} (ID: {client.id})")
        
        # Check all appointments for this client
        all_appointments = db.query(Appointment).filter(
            Appointment.client_id == client.id
        ).all()
        
        print(f"📅 Total appointments: {len(all_appointments)}")
        
        for apt in all_appointments:
            print(f"  - ID: {apt.id}, Status: {apt.status}, Start: {apt.start_dt}")
        
        # Check upcoming appointments (what cancel flow looks for)
        from app.utils.time import now_in_timezone, to_utc
        now_utc = to_utc(now_in_timezone())
        print(f"🕐 Current UTC time: {now_utc}")
        
        upcoming_appointments = db.query(Appointment).filter(
            Appointment.client_id == client.id,
            Appointment.start_dt > now_utc,
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
        ).order_by(Appointment.start_dt).all()
        
        print(f"📅 Upcoming appointments: {len(upcoming_appointments)}")
        
        for apt in upcoming_appointments:
            print(f"  - ID: {apt.id}, Status: {apt.status}, Start: {apt.start_dt}")
            print(f"    Time diff: {(apt.start_dt - now_utc).total_seconds() / 3600:.1f} hours")
        
        # Try the cancel flow
        print("\n🚀 Testing cancel flow...")
        await start_cancel_flow(phone, db)
        
        # Check captured messages
        captured = get_captured_messages(phone)
        print(f"\n📱 Captured {len(captured)} messages:")
        
        for i, msg in enumerate(captured):
            print(f"  {i+1}. {msg['content']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(debug_cancel_flow())
