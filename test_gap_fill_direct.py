#!/usr/bin/env python3
"""
Test gap-fill optimization by directly booking appointments (bypass WhatsApp).
This simulates what would happen if clients accepted the WhatsApp offers.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Appointment, AppointmentStatus, Waitlist
from app.services.scheduler import AppointmentScheduler
from app.utils.time import now_in_timezone, format_datetime_for_user

async def test_gap_fill_direct():
    """Test gap-fill by directly booking appointments (simulating client acceptance)."""
    print("🧪 Testing Gap-Fill Optimization (Direct Booking)")
    print("="*60)
    
    db = SessionLocal()
    try:
        owner = db.query(Owner).first()
        if not owner:
            print("❌ No owner found")
            return
        
        scheduler = AppointmentScheduler(db)
        
        # Find cancelled appointments
        cancelled_appointments = db.query(Appointment).filter(
            Appointment.owner_id == owner.id,
            Appointment.status == AppointmentStatus.CANCELLED
        ).all()
        
        if not cancelled_appointments:
            print("ℹ️  No cancelled appointments found. Cancel an appointment first.")
            return
        
        print(f"🚫 Found {len(cancelled_appointments)} cancelled appointments:")
        for apt in cancelled_appointments:
            apt_local = apt.start_dt.astimezone()
            print(f"  • {apt_local.strftime('%H:%M')} - {apt.client.name} ({apt.service.name})")
        
        # For each cancelled appointment, find and book the highest priority waitlist client
        bookings_made = 0
        
        for cancelled_apt in cancelled_appointments:
            print(f"\n🔄 Processing gap: {cancelled_apt.client.name}'s {cancelled_apt.service.name}")
            
            # Find matching waitlist entries (same logic as optimizer)
            matching_entries = db.query(Waitlist).filter(
                Waitlist.owner_id == owner.id,
                Waitlist.window_start_dt <= cancelled_apt.start_dt,
                Waitlist.window_end_dt >= cancelled_apt.end_dt,
                Waitlist.service_id == cancelled_apt.service.id
            ).order_by(
                Waitlist.priority.desc(),
                Waitlist.created_at.asc()
            ).all()
            
            if matching_entries:
                # Take the highest priority client
                best_match = matching_entries[0]
                priority_text = "HIGH PRIORITY" if best_match.priority > 0 else "Normal"
                
                print(f"  ✅ Best match: {best_match.client.name} ({priority_text})")
                
                try:
                    # Create new appointment for the waitlisted client
                    new_appointment = Appointment(
                        owner_id=owner.id,
                        client_id=best_match.client.id,
                        service_id=best_match.service.id,
                        start_dt=cancelled_apt.start_dt,
                        end_dt=cancelled_apt.end_dt,
                        status=AppointmentStatus.CONFIRMED,
                        channel="Gap-Fill Test",
                        notes=f"Moved from waitlist to fill cancelled slot (was {cancelled_apt.client.name})"
                    )
                    
                    db.add(new_appointment)
                    
                    # Remove from waitlist
                    db.delete(best_match)
                    
                    db.commit()
                    
                    apt_time = cancelled_apt.start_dt.astimezone().strftime('%H:%M')
                    print(f"  🎉 Booked: {best_match.client.name} at {apt_time}")
                    bookings_made += 1
                    
                except Exception as e:
                    print(f"  ❌ Failed to book: {e}")
                    db.rollback()
            else:
                print(f"  ❌ No matching waitlist entries found")
        
        print(f"\n📊 Gap-Fill Test Results:")
        print(f"  • Cancelled appointments processed: {len(cancelled_appointments)}")
        print(f"  • New bookings made: {bookings_made}")
        print(f"  • Success rate: {(bookings_made/len(cancelled_appointments)*100):.0f}%")
        
        if bookings_made > 0:
            print(f"\n✅ Gap-fill optimization successful!")
            print(f"🔄 Now run: python check_gap_fill_results.py")
        else:
            print(f"\n⚠️  No appointments were filled from waitlist")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_gap_fill_direct())
