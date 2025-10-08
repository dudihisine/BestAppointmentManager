#!/usr/bin/env python3
"""
Check the results of gap-fill optimization after cancelling an appointment.
Shows what the system did behind the scenes.
"""

import sys
import os
from datetime import datetime, timedelta, date

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Appointment, AppointmentStatus, Waitlist, AuditLog
from app.utils.time import now_in_timezone, format_datetime_for_user

def check_gap_fill_results():
    """Check what happened after gap-fill optimization."""
    print("🔍 Checking Gap-Fill Optimization Results")
    print("="*50)
    
    db = SessionLocal()
    try:
        owner = db.query(Owner).first()
        if not owner:
            print("❌ No owner found")
            return
        
        tomorrow = now_in_timezone(owner.timezone).date() + timedelta(days=1)
        
        # Show current appointments
        appointments = db.query(Appointment).filter(
            Appointment.owner_id == owner.id
        ).all()
        
        tomorrow_appointments = []
        cancelled_appointments = []
        
        for apt in appointments:
            apt_local = apt.start_dt.astimezone()
            if apt_local.date() == tomorrow:
                apt_info = {
                    "id": apt.id,
                    "client": apt.client.name,
                    "service": apt.service.name,
                    "time": apt_local.strftime("%H:%M"),
                    "status": apt.status.value
                }
                
                if apt.status == AppointmentStatus.CONFIRMED:
                    tomorrow_appointments.append(apt_info)
                elif apt.status == AppointmentStatus.CANCELLED:
                    cancelled_appointments.append(apt_info)
        
        print(f"📅 Current Schedule for {tomorrow.strftime('%A, %B %d')}:")
        if tomorrow_appointments:
            for apt in tomorrow_appointments:
                print(f"  ✅ {apt['time']} - {apt['client']} ({apt['service']}) [ID: {apt['id']}]")
        else:
            print("  📭 No confirmed appointments")
        
        if cancelled_appointments:
            print(f"\n❌ Cancelled Appointments:")
            for apt in cancelled_appointments:
                print(f"  🚫 {apt['time']} - {apt['client']} ({apt['service']}) [ID: {apt['id']}]")
        
        # Show waitlist status
        waitlist_entries = db.query(Waitlist).filter(Waitlist.owner_id == owner.id).all()
        print(f"\n📋 Current Waitlist:")
        if waitlist_entries:
            for entry in waitlist_entries:
                priority_text = "HIGH PRIORITY" if entry.priority > 0 else "Normal"
                window_start = format_datetime_for_user(entry.window_start_dt, owner.timezone, include_date=False)
                window_end = format_datetime_for_user(entry.window_end_dt, owner.timezone, include_date=False)
                print(f"  • {entry.client.name} - {entry.service.name} ({priority_text}, {window_start}-{window_end})")
        else:
            print("  📭 Waitlist is empty")
        
        # Show recent system actions (last 10)
        recent_logs = db.query(AuditLog).filter(
            AuditLog.owner_id == owner.id
        ).order_by(AuditLog.created_at.desc()).limit(10).all()
        
        print(f"\n📜 Recent System Actions (Last 10):")
        if recent_logs:
            for log in recent_logs:
                timestamp = format_datetime_for_user(log.created_at, owner.timezone)
                print(f"  • {timestamp} - {log.action} by {log.actor.value}")
                if log.after and isinstance(log.after, dict):
                    # Show key details
                    if 'appointments_filled' in log.after:
                        print(f"    📊 Appointments filled: {log.after.get('appointments_filled', 0)}")
                    if 'waitlist_notifications' in log.after:
                        print(f"    📨 Waitlist notifications: {log.after.get('waitlist_notifications', 0)}")
                    if 'move_earlier_offers' in log.after:
                        print(f"    🔄 Move earlier offers: {log.after.get('move_earlier_offers', 0)}")
        else:
            print("  📭 No recent system actions")
        
        # Analysis
        print(f"\n📈 Gap-Fill Analysis:")
        total_confirmed = len(tomorrow_appointments)
        total_cancelled = len(cancelled_appointments)
        waitlist_remaining = len(waitlist_entries)
        
        print(f"  • Confirmed appointments: {total_confirmed}")
        print(f"  • Cancelled appointments: {total_cancelled}")
        print(f"  • Waitlist entries remaining: {waitlist_remaining}")
        
        if total_cancelled > 0 and waitlist_remaining > 0:
            print(f"  ⚠️  There are {total_cancelled} cancelled slots and {waitlist_remaining} waitlist entries")
            print(f"     The gap-fill system should have tried to match them.")
        elif total_cancelled > 0 and waitlist_remaining == 0:
            print(f"  ✅ Gap-fill may have worked! Cancelled slots were filled from waitlist.")
        elif total_cancelled == 0:
            print(f"  ℹ️  No cancelled appointments found.")
        
        # Revenue impact
        if tomorrow_appointments:
            total_revenue = sum(
                db.query(Appointment).get(apt["id"]).service.price_cents 
                for apt in tomorrow_appointments
            )
            print(f"  💰 Current revenue: ${total_revenue / 100:.0f}")
        
    except Exception as e:
        print(f"❌ Error checking results: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_gap_fill_results()
