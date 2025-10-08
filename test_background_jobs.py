#!/usr/bin/env python3
"""
Test the background jobs system for appointment reminders and notifications.
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Service, Client, Appointment, AppointmentStatus
from app.services.background_jobs import (
    send_appointment_reminder, 
    check_waitlist_opportunities, 
    send_daily_report,
    schedule_appointment_reminders
)
from app.services.test_messaging import enable_test_mode, get_captured_messages, clear_captured_messages

async def test_background_jobs():
    """Test the background jobs system."""
    print("🧪 Testing Background Jobs System")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        # Enable test mode for message capture
        enable_test_mode()
        
        # Get test data
        owner = db.query(Owner).first()
        if not owner:
            print("❌ No owner found. Please run add_test_data.py first.")
            return
        
        client = db.query(Client).first()
        if not client:
            print("❌ No client found. Please run add_test_data.py first.")
            return
        
        service = db.query(Service).filter(Service.owner_id == owner.id).first()
        if not service:
            print("❌ No service found. Please run add_test_data.py first.")
            return
        
        print(f"📋 Using test data:")
        print(f"  - Owner: {owner.name}")
        print(f"  - Client: {client.name} ({client.phone})")
        print(f"  - Service: {service.name}")
        
        # Test 1: Create a test appointment for tomorrow
        print(f"\n📅 Test 1: Creating test appointment...")
        
        from app.utils.time import now_in_timezone, to_utc
        tomorrow = now_in_timezone(owner.timezone).date() + timedelta(days=1)
        appointment_time = to_utc(datetime.combine(tomorrow, datetime.min.time().replace(hour=14, minute=0)))
        
        appointment = Appointment(
            owner_id=owner.id,
            client_id=client.id,
            service_id=service.id,
            start_dt=appointment_time,
            end_dt=appointment_time + timedelta(minutes=service.duration_min),
            status=AppointmentStatus.CONFIRMED,
            channel="test"
        )
        
        db.add(appointment)
        db.commit()
        
        print(f"✅ Created appointment {appointment.id} for {tomorrow} at 14:00")
        
        # Test 2: Schedule reminder jobs
        print(f"\n⏰ Test 2: Scheduling reminder jobs...")
        
        try:
            schedule_appointment_reminders(appointment.id)
            print("✅ Reminder jobs scheduled successfully")
        except Exception as e:
            print(f"❌ Failed to schedule reminders: {e}")
        
        # Test 3: Test 24-hour reminder
        print(f"\n🔔 Test 3: Testing 24-hour reminder...")
        
        clear_captured_messages(client.phone)
        await send_appointment_reminder(appointment.id, '24h')
        
        captured = get_captured_messages(client.phone)
        if captured:
            print("✅ 24-hour reminder sent:")
            print(f"  {captured[0]['content'][:100]}...")
        else:
            print("❌ No 24-hour reminder captured")
        
        # Test 4: Test 2-hour reminder
        print(f"\n⏰ Test 4: Testing 2-hour reminder...")
        
        clear_captured_messages(client.phone)
        await send_appointment_reminder(appointment.id, '2h')
        
        captured = get_captured_messages(client.phone)
        if captured:
            print("✅ 2-hour reminder sent:")
            print(f"  {captured[0]['content'][:100]}...")
        else:
            print("❌ No 2-hour reminder captured")
        
        # Test 5: Test 30-minute reminder
        print(f"\n🚀 Test 5: Testing 30-minute reminder...")
        
        clear_captured_messages(client.phone)
        await send_appointment_reminder(appointment.id, '30m')
        
        captured = get_captured_messages(client.phone)
        if captured:
            print("✅ 30-minute reminder sent:")
            print(f"  {captured[0]['content'][:100]}...")
        else:
            print("❌ No 30-minute reminder captured")
        
        # Test 6: Test waitlist opportunities
        print(f"\n📋 Test 6: Testing waitlist opportunities...")
        
        clear_captured_messages(client.phone)
        result = await check_waitlist_opportunities(owner.id)
        
        print(f"✅ Waitlist check result: {result}")
        
        # Test 7: Test daily report
        print(f"\n📊 Test 7: Testing daily report...")
        
        # Add owner phone for testing
        if not hasattr(owner, 'phone') or not owner.phone:
            owner.phone = "+1234567890"  # Use test phone
            db.commit()
        
        clear_captured_messages(owner.phone)
        await send_daily_report(owner.id)
        
        captured = get_captured_messages(owner.phone)
        if captured:
            print("✅ Daily report sent:")
            print(f"  {captured[0]['content'][:100]}...")
        else:
            print("❌ No daily report captured")
        
        print(f"\n🎉 Background jobs testing completed!")
        print(f"\n💡 To run the worker in production:")
        print(f"   python worker.py")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_background_jobs())
