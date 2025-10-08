#!/usr/bin/env python3
"""
Debug why gap-fill isn't working by checking the exact matching logic.
"""

import sys
import os
from datetime import datetime, timedelta

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Appointment, AppointmentStatus, Waitlist
from app.utils.time import now_in_timezone, format_datetime_for_user

def debug_gap_fill():
    """Debug the gap-fill matching logic."""
    print("🔍 Debugging Gap-Fill Matching Logic")
    print("="*50)
    
    db = SessionLocal()
    try:
        owner = db.query(Owner).first()
        if not owner:
            print("❌ No owner found")
            return
        
        # Find cancelled appointments
        cancelled_appointments = db.query(Appointment).filter(
            Appointment.owner_id == owner.id,
            Appointment.status == AppointmentStatus.CANCELLED
        ).all()
        
        print(f"🚫 Cancelled Appointments:")
        for apt in cancelled_appointments:
            apt_local_start = apt.start_dt.astimezone()
            apt_local_end = apt.end_dt.astimezone()
            print(f"  • {apt.client.name} - {apt.service.name}")
            print(f"    Gap: {apt_local_start.strftime('%Y-%m-%d %H:%M')} to {apt_local_end.strftime('%Y-%m-%d %H:%M')}")
            print(f"    Service ID: {apt.service.id}")
            print()
            
            # Check waitlist matches for this gap
            print(f"    🔍 Checking waitlist matches:")
            
            # This is the exact query from the optimizer
            matching_entries = db.query(Waitlist).filter(
                Waitlist.owner_id == owner.id,
                Waitlist.window_start_dt <= apt.start_dt,  # Waitlist window starts before/at gap
                Waitlist.window_end_dt >= apt.end_dt,      # Waitlist window ends after/at gap
                Waitlist.service_id == apt.service.id      # Same service
            ).order_by(
                Waitlist.priority.desc(),
                Waitlist.created_at.asc()
            ).all()
            
            if matching_entries:
                print(f"    ✅ Found {len(matching_entries)} matching waitlist entries:")
                for entry in matching_entries:
                    window_start = entry.window_start_dt.astimezone()
                    window_end = entry.window_end_dt.astimezone()
                    priority_text = "HIGH PRIORITY" if entry.priority > 0 else "Normal"
                    print(f"      • {entry.client.name} ({priority_text})")
                    print(f"        Window: {window_start.strftime('%Y-%m-%d %H:%M')} to {window_end.strftime('%Y-%m-%d %H:%M')}")
                    print(f"        Service: {entry.service.name} (ID: {entry.service.id})")
            else:
                print(f"    ❌ No matching waitlist entries found")
                
                # Check why no matches
                print(f"    🔍 Debugging why no matches:")
                
                all_waitlist = db.query(Waitlist).filter(Waitlist.owner_id == owner.id).all()
                for entry in all_waitlist:
                    window_start = entry.window_start_dt.astimezone()
                    window_end = entry.window_end_dt.astimezone()
                    
                    print(f"      • {entry.client.name} - {entry.service.name}")
                    print(f"        Window: {window_start.strftime('%Y-%m-%d %H:%M')} to {window_end.strftime('%Y-%m-%d %H:%M')}")
                    print(f"        Service ID: {entry.service.id} (need: {apt.service.id})")
                    
                    # Check each condition
                    window_starts_before = entry.window_start_dt <= apt.start_dt
                    window_ends_after = entry.window_end_dt >= apt.end_dt
                    service_matches = entry.service.id == apt.service.id
                    
                    print(f"        ✓ Window starts before gap: {window_starts_before}")
                    print(f"        ✓ Window ends after gap: {window_ends_after}")
                    print(f"        ✓ Service matches: {service_matches}")
                    
                    if window_starts_before and window_ends_after and service_matches:
                        print(f"        ✅ This should match!")
                    else:
                        print(f"        ❌ This doesn't match")
                    print()
            
            print("-" * 40)
        
    except Exception as e:
        print(f"❌ Error debugging: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_gap_fill()
