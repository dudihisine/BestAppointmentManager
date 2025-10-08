#!/usr/bin/env python3
"""
Test script for gap-fill optimization after appointment cancellation.

This script demonstrates:
1. Cancelling an appointment
2. System automatically filling the gap from waitlist
3. Cascading optimization when clients move to earlier slots
4. Backfilling the moved client's original slot

Usage:
    python test_gap_fill_optimization.py
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, time, date
from typing import Optional

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, engine, Base
from app.models import (
    Owner, OwnerSetting, Service, Client, Appointment, AppointmentStatus, 
    Availability, Block, Waitlist, IntentMode, AuditLog
)
from app.services.scheduler import AppointmentScheduler
from app.services.optimizer import OptimizationEngine, handle_appointment_cancellation
from app.services.waitlist import WaitlistManager
from app.utils.time import to_utc, now_in_timezone, get_owner_timezone, format_datetime_for_user

class GapFillTester:
    def __init__(self):
        self.db = SessionLocal()
        self.scheduler = AppointmentScheduler(self.db)
        self.optimizer = OptimizationEngine(self.db)
        self.waitlist_manager = WaitlistManager(self.db)
        
    def setup_test_scenario(self):
        """Set up a test scenario with appointments and waitlist entries."""
        print("🚀 Setting up gap-fill test scenario...")
        
        # Ensure tables are created
        Base.metadata.create_all(bind=engine)
        
        # Clear existing data for clean test
        self.db.query(AuditLog).delete()
        self.db.query(Waitlist).delete()
        self.db.query(Appointment).delete()
        self.db.query(Block).delete()
        self.db.query(Client).delete()
        self.db.query(Service).delete()
        self.db.query(Availability).delete()
        self.db.query(OwnerSetting).delete()
        self.db.query(Owner).delete()
        self.db.commit()
        
        # Create owner
        owner = Owner(
            name="David's Barbershop",
            phone="+972501234567",
            timezone="Asia/Jerusalem",
            default_intent=IntentMode.BALANCED
        )
        self.db.add(owner)
        self.db.commit()
        self.db.refresh(owner)
        
        # Create owner settings
        settings = OwnerSetting(
            owner_id=owner.id,
            lead_time_min=60,
            cancel_window_hr=2,
            max_outreach_per_gap=3
        )
        self.db.add(settings)
        
        # Add availability (9 AM - 5 PM, Mon-Fri)
        for weekday in range(5):
            availability = Availability(
                owner_id=owner.id,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(17, 0),
                active=True
            )
            self.db.add(availability)
        
        # Create services
        services = [
            Service(owner_id=owner.id, name="Haircut", duration_min=30, buffer_min=10, price_cents=2500),
            Service(owner_id=owner.id, name="Haircut + Beard", duration_min=45, buffer_min=15, price_cents=4000),
            Service(owner_id=owner.id, name="Quick Trim", duration_min=15, buffer_min=5, price_cents=1500),
        ]
        for service in services:
            self.db.add(service)
        self.db.commit()
        
        # Create clients
        clients = [
            Client(owner_id=owner.id, name="John Smith", phone="+1234567890"),
            Client(owner_id=owner.id, name="Sarah Johnson", phone="+1234567891"),
            Client(owner_id=owner.id, name="Mike Wilson", phone="+1234567892"),
            Client(owner_id=owner.id, name="Emma Davis", phone="+1234567893"),
            Client(owner_id=owner.id, name="Alex Brown", phone="+1234567894"),
            Client(owner_id=owner.id, name="Lisa Garcia", phone="+1234567895"),
        ]
        for client in clients:
            self.db.add(client)
        self.db.commit()
        
        # Get references
        haircut_service = self.db.query(Service).filter(Service.name == "Haircut").first()
        beard_service = self.db.query(Service).filter(Service.name == "Haircut + Beard").first()
        trim_service = self.db.query(Service).filter(Service.name == "Quick Trim").first()
        
        john = self.db.query(Client).filter(Client.name == "John Smith").first()
        sarah = self.db.query(Client).filter(Client.name == "Sarah Johnson").first()
        mike = self.db.query(Client).filter(Client.name == "Mike Wilson").first()
        emma = self.db.query(Client).filter(Client.name == "Emma Davis").first()
        alex = self.db.query(Client).filter(Client.name == "Alex Brown").first()
        lisa = self.db.query(Client).filter(Client.name == "Lisa Garcia").first()
        
        # Create appointments for tomorrow
        owner_tz = get_owner_timezone(owner.timezone)
        tomorrow = now_in_timezone(owner.timezone).date() + timedelta(days=1)
        
        appointments = [
            # 9:00 AM - John (Haircut) - THIS WILL BE CANCELLED
            (john, haircut_service, tomorrow, time(9, 0)),
            # 10:00 AM - Sarah (Haircut + Beard)  
            (sarah, beard_service, tomorrow, time(10, 0)),
            # 12:00 PM - Mike (Haircut)
            (mike, haircut_service, tomorrow, time(12, 0)),
            # 2:00 PM - Emma (Quick Trim)
            (emma, trim_service, tomorrow, time(14, 0)),
        ]
        
        created_appointments = []
        for client, service, apt_date, apt_time in appointments:
            start_dt_local = datetime.combine(apt_date, apt_time)
            start_dt_utc = to_utc(start_dt_local, owner.timezone)
            end_dt_utc = to_utc(start_dt_local + timedelta(minutes=service.duration_min + service.buffer_min), owner.timezone)
            
            appointment = Appointment(
                owner_id=owner.id,
                client_id=client.id,
                service_id=service.id,
                start_dt=start_dt_utc,
                end_dt=end_dt_utc,
                status=AppointmentStatus.CONFIRMED,
                channel="Test"
            )
            self.db.add(appointment)
            created_appointments.append((client.name, service.name, start_dt_local.strftime("%H:%M")))
        
        self.db.commit()
        
        # Create waitlist entries
        waitlist_entries = [
            # Alex wants a haircut anytime tomorrow 9 AM - 5 PM (HIGH PRIORITY)
            (alex, haircut_service, 
             to_utc(datetime.combine(tomorrow, time(9, 0)), owner.timezone),
             to_utc(datetime.combine(tomorrow, time(17, 0)), owner.timezone), 1),
            
            # Lisa wants a quick trim anytime tomorrow 10 AM - 4 PM
            (lisa, trim_service,
             to_utc(datetime.combine(tomorrow, time(10, 0)), owner.timezone),
             to_utc(datetime.combine(tomorrow, time(16, 0)), owner.timezone), 0),
        ]
        
        for client, service, window_start, window_end, priority in waitlist_entries:
            waitlist = Waitlist(
                owner_id=owner.id,
                client_id=client.id,
                service_id=service.id,
                window_start_dt=window_start,
                window_end_dt=window_end,
                priority=priority
            )
            self.db.add(waitlist)
        
        self.db.commit()
        
        print("✅ Test scenario created!")
        print("\n📅 Initial Schedule for Tomorrow:")
        for client_name, service_name, time_str in created_appointments:
            print(f"  • {time_str} - {client_name} ({service_name})")
        
        print("\n📋 Waitlist:")
        print(f"  • Alex Brown - Haircut (HIGH PRIORITY, 9:00-17:00)")
        print(f"  • Lisa Garcia - Quick Trim (10:00-16:00)")
        
        return owner, created_appointments[0]  # Return owner and the appointment to cancel
    
    async def test_cancellation_and_gap_fill(self, owner, appointment_to_cancel_info):
        """Test appointment cancellation and gap-fill process."""
        
        print(f"\n🔥 TESTING: Cancelling {appointment_to_cancel_info[0]}'s {appointment_to_cancel_info[1]} at {appointment_to_cancel_info[2]}")
        
        # Find the appointment to cancel (John's 9 AM haircut)
        john = self.db.query(Client).filter(Client.name == "John Smith").first()
        appointment_to_cancel = self.db.query(Appointment).filter(
            Appointment.client_id == john.id,
            Appointment.status == AppointmentStatus.CONFIRMED
        ).first()
        
        if not appointment_to_cancel:
            print("❌ Could not find appointment to cancel!")
            return
        
        print(f"📍 Found appointment ID {appointment_to_cancel.id} to cancel")
        
        # Cancel the appointment
        try:
            success = self.scheduler.cancel_appointment(appointment_to_cancel, "Client requested cancellation")
            if success:
                print("✅ Appointment cancelled successfully!")
            else:
                print("❌ Failed to cancel appointment")
                return
        except Exception as e:
            print(f"❌ Error cancelling appointment: {e}")
            return
        
        # Wait a moment for async gap-fill to process
        print("\n⏳ Waiting for gap-fill optimization to process...")
        await asyncio.sleep(2)
        
        # Manually trigger gap-fill to ensure it runs (since async task might not complete in test)
        print("🔄 Manually triggering gap-fill optimization...")
        try:
            result = await handle_appointment_cancellation(self.db, appointment_to_cancel.id)
            print(f"📊 Gap-fill result: {result}")
        except Exception as e:
            print(f"❌ Gap-fill error: {e}")
        
        # Show the results
        await self.show_results(owner)
    
    async def show_results(self, owner):
        """Show the results after gap-fill optimization."""
        
        print("\n" + "="*60)
        print("📊 RESULTS AFTER GAP-FILL OPTIMIZATION")
        print("="*60)
        
        # Show updated schedule
        tomorrow = now_in_timezone(owner.timezone).date() + timedelta(days=1)
        appointments = self.scheduler.get_daily_schedule(owner, tomorrow)
        
        print(f"\n📅 Updated Schedule for {tomorrow.strftime('%A, %B %d')}:")
        if appointments:
            for apt in appointments:
                start_time = format_datetime_for_user(apt.start_dt, owner.timezone, include_date=False)
                status_emoji = "✅" if apt.status == AppointmentStatus.CONFIRMED else "❌"
                print(f"  {status_emoji} {start_time} - {apt.client.name} ({apt.service.name}) [{apt.status.value}]")
        else:
            print("  📭 No appointments scheduled")
        
        # Show updated waitlist
        waitlist_entries = self.db.query(Waitlist).filter(Waitlist.owner_id == owner.id).all()
        print(f"\n📋 Updated Waitlist:")
        if waitlist_entries:
            for entry in waitlist_entries:
                priority_text = "HIGH PRIORITY" if entry.priority > 0 else "Normal"
                window_start = format_datetime_for_user(entry.window_start_dt, owner.timezone, include_date=False)
                window_end = format_datetime_for_user(entry.window_end_dt, owner.timezone, include_date=False)
                print(f"  • {entry.client.name} - {entry.service.name} ({priority_text}, {window_start}-{window_end})")
        else:
            print("  📭 Waitlist is empty")
        
        # Show audit log
        audit_logs = self.db.query(AuditLog).filter(AuditLog.owner_id == owner.id).order_by(AuditLog.created_at.desc()).limit(5).all()
        print(f"\n📜 Recent System Actions:")
        if audit_logs:
            for log in audit_logs:
                timestamp = format_datetime_for_user(log.created_at, owner.timezone)
                print(f"  • {timestamp} - {log.action} by {log.actor.value}")
                if log.after:
                    print(f"    Details: {log.after}")
        else:
            print("  📭 No audit logs found")
        
        # Calculate optimization impact
        filled_appointments = len([apt for apt in appointments if apt.status == AppointmentStatus.CONFIRMED])
        cancelled_appointments = len([apt for apt in appointments if apt.status == AppointmentStatus.CANCELLED])
        
        print(f"\n📈 Optimization Impact:")
        print(f"  • Confirmed appointments: {filled_appointments}")
        print(f"  • Cancelled appointments: {cancelled_appointments}")
        print(f"  • Waitlist entries remaining: {len(waitlist_entries)}")
        
        if filled_appointments > 0:
            total_revenue = sum(apt.service.price_cents for apt in appointments if apt.status == AppointmentStatus.CONFIRMED)
            print(f"  • Total revenue: ${total_revenue / 100:.0f}")
    
    def cleanup(self):
        """Clean up database session."""
        self.db.close()

async def main():
    """Main test function."""
    print("🧪 Gap-Fill Optimization Test")
    print("="*50)
    
    tester = GapFillTester()
    
    try:
        # Set up the test scenario
        owner, appointment_to_cancel = tester.setup_test_scenario()
        
        # Test cancellation and gap-fill
        await tester.test_cancellation_and_gap_fill(owner, appointment_to_cancel)
        
        print("\n✅ Test completed!")
        print("\n💡 What should have happened:")
        print("  1. John's 9:00 AM appointment was cancelled")
        print("  2. System found Alex on waitlist (HIGH PRIORITY)")
        print("  3. Alex was offered the 9:00 AM slot")
        print("  4. If Alex accepted, his waitlist entry was removed")
        print("  5. System looked for other optimization opportunities")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        tester.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
