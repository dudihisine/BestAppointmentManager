#!/usr/bin/env python3
"""
Setup test data for the appointment system.
Creates a sample owner with services for testing.
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

from datetime import time, datetime
from app.db import SessionLocal
from app.models import (
    Owner, OwnerSetting, Service, Availability, 
    IntentMode
)

def create_test_owner():
    """Create a test business owner with services."""
    db = SessionLocal()
    
    try:
        # Check if owner already exists
        existing_owner = db.query(Owner).filter(Owner.phone == "+972501234567").first()
        if existing_owner:
            print(f"✅ Owner already exists: {existing_owner.name}")
            return existing_owner
        
        # Create owner
        owner = Owner(
            phone="+972501234567",
            name="David's Barbershop",
            timezone="Asia/Jerusalem",
            default_intent=IntentMode.BALANCED,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0)
        )
        db.add(owner)
        db.flush()  # Get the ID
        
        # Create owner settings
        settings = OwnerSetting(
            owner_id=owner.id,
            lead_time_min=60,
            cancel_window_hr=24,
            reminder_hours=[24, 2],
            max_outreach_per_gap=5
        )
        db.add(settings)
        
        # Create availability (Monday-Friday, 9-17)
        for weekday in range(5):  # 0=Monday, 4=Friday
            availability = Availability(
                owner_id=owner.id,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(17, 0),
                active=True
            )
            db.add(availability)
        
        # Create services
        services_data = [
            {"name": "Haircut", "duration": 30, "price": 5000, "buffer": 10},  # $50
            {"name": "Haircut + Beard", "duration": 45, "price": 7000, "buffer": 15},  # $70
            {"name": "Beard Trim", "duration": 20, "price": 3000, "buffer": 10},  # $30
            {"name": "Hair Wash", "duration": 15, "price": 2000, "buffer": 5},  # $20
        ]
        
        for service_data in services_data:
            service = Service(
                owner_id=owner.id,
                name=service_data["name"],
                duration_min=service_data["duration"],
                price_cents=service_data["price"],
                buffer_min=service_data["buffer"],
                active=True
            )
            db.add(service)
        
        db.commit()
        
        print(f"✅ Created test owner: {owner.name}")
        print(f"   Phone: {owner.phone}")
        print(f"   Services: {len(services_data)}")
        print(f"   Availability: Monday-Friday 9:00-17:00")
        
        return owner
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating test owner: {e}")
        raise
    finally:
        db.close()

def show_test_data():
    """Show existing test data."""
    db = SessionLocal()
    
    try:
        owners = db.query(Owner).all()
        
        if not owners:
            print("📭 No owners found in database")
            return
        
        for owner in owners:
            print(f"\n👔 Owner: {owner.name}")
            print(f"   Phone: {owner.phone}")
            print(f"   Timezone: {owner.timezone}")
            print(f"   Intent: {owner.default_intent.value}")
            
            # Show services
            services = db.query(Service).filter(
                Service.owner_id == owner.id,
                Service.active == True
            ).all()
            
            print(f"\n💼 Services ({len(services)}):")
            for service in services:
                price = f"${service.price_cents / 100:.0f}"
                duration = f"{service.duration_min}min"
                buffer = f"+{service.buffer_min}min buffer" if service.buffer_min > 0 else ""
                print(f"   • {service.name} - {duration} - {price} {buffer}")
            
            # Show availability
            availabilities = db.query(Availability).filter(
                Availability.owner_id == owner.id,
                Availability.active == True
            ).all()
            
            if availabilities:
                print(f"\n📅 Availability:")
                weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                for avail in availabilities:
                    day = weekdays[avail.weekday]
                    print(f"   • {day}: {avail.start_time.strftime('%H:%M')}-{avail.end_time.strftime('%H:%M')}")
        
    except Exception as e:
        print(f"❌ Error showing test data: {e}")
    finally:
        db.close()

def main():
    """Main function."""
    print("🔧 Test Data Setup")
    print("=" * 30)
    
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        show_test_data()
    else:
        create_test_owner()
        print("\n" + "=" * 30)
        show_test_data()
        
        print(f"\n💡 Tips:")
        print(f"   • Use phone +972501234567 to test as owner")
        print(f"   • Use any other phone to test as client")
        print(f"   • Run 'python setup_test_data.py show' to view data")

if __name__ == "__main__":
    main()
