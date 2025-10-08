#!/usr/bin/env python3
"""
Setup script for testing gap-fill optimization via web interface.

This script creates:
1. Appointments for tomorrow with one that can be cancelled
2. Waitlist entries that should match the cancelled slot
3. Clear scenario for testing gap-fill via the web dashboard

Usage:
    python setup_gap_fill_test.py
"""

import sys
import os
from datetime import datetime, timedelta, time, date

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, engine, Base
from app.models import (
    Owner, OwnerSetting, Service, Client, Appointment, AppointmentStatus, 
    Availability, Waitlist, IntentMode
)
from app.utils.time import to_utc, now_in_timezone, get_owner_timezone

def setup_gap_fill_test():
    """Set up test data for gap-fill optimization testing."""
    print("🚀 Setting up gap-fill test data...")
    
    db = SessionLocal()
    try:
        # Get existing owner or create one
        owner = db.query(Owner).first()
        if not owner:
            print("❌ No owner found. Please run add_test_data.py first.")
            return
        
        print(f"✅ Using owner: {owner.name}")
        
        # Clear existing waitlist entries for clean test
        db.query(Waitlist).filter(Waitlist.owner_id == owner.id).delete()
        db.commit()
        
        # Get services
        haircut_service = db.query(Service).filter(
            Service.owner_id == owner.id,
            Service.name == "Haircut"
        ).first()
        
        trim_service = db.query(Service).filter(
            Service.owner_id == owner.id,
            Service.name == "Quick Trim"
        ).first()
        
        if not haircut_service or not trim_service:
            print("❌ Required services not found. Please run add_test_data.py first.")
            return
        
        # Get clients
        alex = db.query(Client).filter(
            Client.owner_id == owner.id,
            Client.name == "Alex Brown"
        ).first()
        
        lisa = db.query(Client).filter(
            Client.owner_id == owner.id,
            Client.name == "Lisa Garcia"
        ).first()
        
        if not alex or not lisa:
            print("❌ Required clients not found. Please run add_test_data.py first.")
            return
        
        # Calculate tomorrow's date
        tomorrow = now_in_timezone(owner.timezone).date() + timedelta(days=1)
        
        # Create waitlist entries that will match cancelled appointments
        waitlist_entries = [
            # Alex wants a haircut anytime tomorrow 8 AM - 6 PM (HIGH PRIORITY)
            # This should match if we cancel John's 9 AM haircut
            {
                "client": alex,
                "service": haircut_service,
                "window_start": to_utc(datetime.combine(tomorrow, time(8, 0)), owner.timezone),
                "window_end": to_utc(datetime.combine(tomorrow, time(18, 0)), owner.timezone),
                "priority": 1,
                "description": "Alex - Haircut (HIGH PRIORITY, 8:00-18:00)"
            },
            
            # Lisa wants a quick trim anytime tomorrow 9 AM - 5 PM
            # This should match if we cancel Emma's 2 PM quick trim
            {
                "client": lisa,
                "service": trim_service,
                "window_start": to_utc(datetime.combine(tomorrow, time(9, 0)), owner.timezone),
                "window_end": to_utc(datetime.combine(tomorrow, time(17, 0)), owner.timezone),
                "priority": 0,
                "description": "Lisa - Quick Trim (9:00-17:00)"
            }
        ]
        
        print(f"\n📋 Creating waitlist entries for {tomorrow.strftime('%A, %B %d')}:")
        
        for entry_data in waitlist_entries:
            waitlist = Waitlist(
                owner_id=owner.id,
                client_id=entry_data["client"].id,
                service_id=entry_data["service"].id,
                window_start_dt=entry_data["window_start"],
                window_end_dt=entry_data["window_end"],
                priority=entry_data["priority"]
            )
            db.add(waitlist)
            print(f"  ✅ {entry_data['description']}")
        
        db.commit()
        
        # Show current appointments for tomorrow
        appointments = db.query(Appointment).filter(
            Appointment.owner_id == owner.id,
            Appointment.status == AppointmentStatus.CONFIRMED
        ).all()
        
        tomorrow_appointments = []
        for apt in appointments:
            apt_local = apt.start_dt.astimezone(get_owner_timezone(owner.timezone))
            if apt_local.date() == tomorrow:
                tomorrow_appointments.append({
                    "id": apt.id,
                    "client": apt.client.name,
                    "service": apt.service.name,
                    "time": apt_local.strftime("%H:%M")
                })
        
        print(f"\n📅 Current appointments for {tomorrow.strftime('%A, %B %d')}:")
        if tomorrow_appointments:
            for apt in tomorrow_appointments:
                print(f"  • {apt['time']} - {apt['client']} ({apt['service']}) [ID: {apt['id']}]")
        else:
            print("  📭 No appointments scheduled")
        
        print(f"\n🧪 GAP-FILL TEST SETUP COMPLETE!")
        print(f"="*50)
        print(f"📋 How to test gap-fill optimization:")
        print(f"")
        print(f"1. 🌐 Go to: http://localhost:8000/owner/dashboard")
        print(f"2. 📅 Navigate to {tomorrow.strftime('%A, %B %d')}")
        print(f"3. 🎯 Cancel any appointment (click the 3-dot menu → 'Cancel & Fill Gap')")
        print(f"4. 🔍 Watch for:")
        print(f"   • Success message about gap-fill optimization")
        print(f"   • Waitlist entries should be processed")
        print(f"   • System should try to fill the cancelled slot")
        print(f"")
        print(f"💡 Expected behavior:")
        print(f"   • If you cancel a Haircut → Alex should be notified (HIGH PRIORITY)")
        print(f"   • If you cancel a Quick Trim → Lisa should be notified")
        print(f"   • System will log all actions in the audit trail")
        print(f"")
        print(f"🔧 Note: WhatsApp notifications may fail due to Twilio limits,")
        print(f"   but the gap-fill logic should still run and be logged.")
        
    except Exception as e:
        print(f"❌ Error setting up test data: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    setup_gap_fill_test()
