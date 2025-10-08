#!/usr/bin/env python3
"""
Add comprehensive test data for testing all features.
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

from datetime import datetime, date, time, timedelta
from sqlalchemy.orm import Session
from app.db import SessionLocal, engine
from app.models import (
    Owner, OwnerSetting, Service, Availability, Block, 
    Client, Appointment, Waitlist, AuditLog,
    IntentMode, AppointmentStatus, AuditActor
)
from app.utils.time import to_utc, get_owner_timezone

def add_test_data():
    """Add comprehensive test data."""
    db = SessionLocal()
    
    try:
        print("🚀 Adding test data...")
        
        # Get existing owner or create if needed
        owner = db.query(Owner).first()
        if not owner:
            print("❌ No owner found. Please run the database migration first.")
            return
        
        print(f"✅ Using owner: {owner.name}")
        
        # Add more services
        services_data = [
            {"name": "Quick Trim", "duration_min": 15, "buffer_min": 5, "price_cents": 1500},
            {"name": "Deluxe Package", "duration_min": 90, "buffer_min": 15, "price_cents": 7500},
            {"name": "Beard Styling", "duration_min": 20, "buffer_min": 5, "price_cents": 2000},
            {"name": "Hair Wash", "duration_min": 10, "buffer_min": 5, "price_cents": 1000},
        ]
        
        for service_data in services_data:
            existing = db.query(Service).filter(
                Service.owner_id == owner.id,
                Service.name == service_data["name"]
            ).first()
            
            if not existing:
                service = Service(owner_id=owner.id, **service_data)
                db.add(service)
                print(f"  ➕ Added service: {service_data['name']}")
        
        db.commit()
        
        # Add test clients
        clients_data = [
            {"name": "John Smith", "phone": "+1234567890"},
            {"name": "Sarah Johnson", "phone": "+1234567891"},
            {"name": "Mike Wilson", "phone": "+1234567892"},
            {"name": "Emma Davis", "phone": "+1234567893"},
            {"name": "Alex Brown", "phone": "+1234567894"},
            {"name": "Lisa Garcia", "phone": "+1234567895"},
        ]
        
        for client_data in clients_data:
            existing = db.query(Client).filter(
                Client.owner_id == owner.id,
                Client.phone == client_data["phone"]
            ).first()
            
            if not existing:
                client = Client(owner_id=owner.id, **client_data)
                db.add(client)
                print(f"  ➕ Added client: {client_data['name']}")
        
        db.commit()
        
        # Add test appointments (mix of today, tomorrow, and future)
        services = db.query(Service).filter(Service.owner_id == owner.id).all()
        clients = db.query(Client).filter(Client.owner_id == owner.id).all()
        
        if services and clients:
            today = date.today()
            appointments_data = [
                # Today's appointments
                {"date": today, "time": time(10, 0), "service_idx": 0, "client_idx": 0, "status": AppointmentStatus.CONFIRMED},
                {"date": today, "time": time(14, 0), "service_idx": 1, "client_idx": 1, "status": AppointmentStatus.CONFIRMED},
                {"date": today, "time": time(16, 0), "service_idx": 2, "client_idx": 2, "status": AppointmentStatus.PENDING},
                
                # Tomorrow's appointments
                {"date": today + timedelta(days=1), "time": time(9, 0), "service_idx": 0, "client_idx": 3, "status": AppointmentStatus.CONFIRMED},
                {"date": today + timedelta(days=1), "time": time(11, 0), "service_idx": 3, "client_idx": 4, "status": AppointmentStatus.CONFIRMED},
                {"date": today + timedelta(days=1), "time": time(15, 0), "service_idx": 1, "client_idx": 5, "status": AppointmentStatus.CONFIRMED},
                
                # Future appointments
                {"date": today + timedelta(days=3), "time": time(10, 0), "service_idx": 2, "client_idx": 0, "status": AppointmentStatus.CONFIRMED},
                {"date": today + timedelta(days=5), "time": time(13, 0), "service_idx": 0, "client_idx": 1, "status": AppointmentStatus.CONFIRMED},
            ]
            
            for apt_data in appointments_data:
                service = services[apt_data["service_idx"] % len(services)]
                client = clients[apt_data["client_idx"] % len(clients)]
                
                start_dt_local = datetime.combine(apt_data["date"], apt_data["time"])
                start_dt_utc = to_utc(start_dt_local, owner.timezone)
                end_dt_utc = start_dt_utc + timedelta(minutes=service.duration_min + service.buffer_min)
                
                # Check if appointment already exists
                existing = db.query(Appointment).filter(
                    Appointment.owner_id == owner.id,
                    Appointment.start_dt == start_dt_utc
                ).first()
                
                if not existing:
                    appointment = Appointment(
                        owner_id=owner.id,
                        client_id=client.id,
                        service_id=service.id,
                        start_dt=start_dt_utc,
                        end_dt=end_dt_utc,
                        status=apt_data["status"],
                        channel="Test Data",
                        notes=f"Test appointment for {client.name}"
                    )
                    db.add(appointment)
                    print(f"  📅 Added appointment: {client.name} - {service.name} on {apt_data['date']}")
        
        db.commit()
        
        # Add waitlist entries
        if services and clients:
            tomorrow = today + timedelta(days=1)
            next_week = today + timedelta(days=7)
            
            waitlist_data = [
                {"client_idx": 2, "service_idx": 0, "window_start": datetime.combine(tomorrow, time(9, 0)), "window_end": datetime.combine(tomorrow, time(17, 0))},
                {"client_idx": 3, "service_idx": 1, "window_start": datetime.combine(next_week, time(10, 0)), "window_end": datetime.combine(next_week, time(16, 0))},
                {"client_idx": 4, "service_idx": 2, "window_start": datetime.combine(tomorrow, time(12, 0)), "window_end": datetime.combine(tomorrow, time(18, 0))},
            ]
            
            for wait_data in waitlist_data:
                service = services[wait_data["service_idx"] % len(services)]
                client = clients[wait_data["client_idx"] % len(clients)]
                
                window_start_utc = to_utc(wait_data["window_start"], owner.timezone)
                window_end_utc = to_utc(wait_data["window_end"], owner.timezone)
                
                existing = db.query(Waitlist).filter(
                    Waitlist.client_id == client.id,
                    Waitlist.service_id == service.id
                ).first()
                
                if not existing:
                    waitlist = Waitlist(
                        owner_id=owner.id,
                        client_id=client.id,
                        service_id=service.id,
                        window_start_dt=window_start_utc,
                        window_end_dt=window_end_utc,
                        priority=1 if wait_data["client_idx"] == 2 else 0,
                        notify_count=0
                    )
                    db.add(waitlist)
                    print(f"  📋 Added waitlist: {client.name} for {service.name}")
        
        db.commit()
        
        # Add some blocks (owner unavailable times)
        tomorrow = today + timedelta(days=1)
        blocks_data = [
            {"date": today, "start_time": time(12, 0), "end_time": time(13, 0), "reason": "Lunch Break"},
            {"date": tomorrow, "start_time": time(12, 30), "end_time": time(13, 30), "reason": "Personal Appointment"},
        ]
        
        for block_data in blocks_data:
            existing = db.query(Block).filter(
                Block.owner_id == owner.id,
                Block.date == block_data["date"],
                Block.start_time == block_data["start_time"]
            ).first()
            
            if not existing:
                block = Block(owner_id=owner.id, **block_data)
                db.add(block)
                print(f"  🚫 Added block: {block_data['reason']} on {block_data['date']}")
        
        db.commit()
        
        print("✅ Test data added successfully!")
        print("\n📊 Summary:")
        print(f"  • Services: {db.query(Service).filter(Service.owner_id == owner.id).count()}")
        print(f"  • Clients: {db.query(Client).filter(Client.owner_id == owner.id).count()}")
        print(f"  • Appointments: {db.query(Appointment).filter(Appointment.owner_id == owner.id).count()}")
        print(f"  • Waitlist entries: {db.query(Waitlist).filter(Waitlist.owner_id == owner.id).count()}")
        print(f"  • Blocks: {db.query(Block).filter(Block.owner_id == owner.id).count()}")
        
    except Exception as e:
        print(f"❌ Error adding test data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_test_data()
