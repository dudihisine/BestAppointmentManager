"""
Appointment Reminder System
"""
import logging
from datetime import datetime, timedelta
from .twilio_client import send_whatsapp_message

logger = logging.getLogger(__name__)


def send_due_reminders(db) -> dict:
    """Send reminders for appointments"""
    try:
        # Get all owners
        owners_ref = db.db.collection('owners').stream()
        reminders_sent = 0
        
        for owner_doc in owners_ref:
            owner = owner_doc.to_dict()
            owner['id'] = owner_doc.id
            
            # Check appointments for this owner
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            # Get appointments for next 24 hours
            appointments = db.get_owner_appointments(owner['id'], today)
            appointments.extend(db.get_owner_appointments(owner['id'], tomorrow))
            
            for apt in appointments:
                if apt['status'] != 'CONFIRMED':
                    continue
                
                now = datetime.utcnow()
                time_until = apt['start_dt'] - now
                hours_until = time_until.total_seconds() / 3600
                
                # Send reminder if within reminder window
                if 23 < hours_until < 25:  # 24-hour reminder
                    send_reminder(apt, '24h', db)
                    reminders_sent += 1
                elif 1.5 < hours_until < 2.5:  # 2-hour reminder
                    send_reminder(apt, '2h', db)
                    reminders_sent += 1
                elif 0.4 < hours_until < 0.6:  # 30-min reminder
                    send_reminder(apt, '30m', db)
                    reminders_sent += 1
        
        return {'success': True, 'reminders_sent': reminders_sent}
        
    except Exception as e:
        logger.error(f"Error sending reminders: {str(e)}", exc_info=True)
        return {'success': False, 'error': str(e)}


def send_reminder(apt: dict, reminder_type: str, db):
    """Send individual reminder"""
    try:
        service = db.get_service(apt['service_id'])
        client_id = apt['client_id']
        
        # Get client phone
        client_doc = db.db.collection('clients').document(client_id).get()
        if not client_doc.exists:
            return
        
        client = client_doc.to_dict()
        
        time_str = apt['start_dt'].strftime('%A, %B %d at %H:%M')
        
        if reminder_type == '24h':
            message = (
                f"🔔 **Appointment Reminder**\\n\\n"
                f"Hi {client['name']}! This is a friendly reminder about your appointment tomorrow.\\n\\n"
                f"📋 **Service:** {service['name']}\\n"
                f"📅 **When:** {time_str}\\n"
                f"⏱️ **Duration:** {service['duration_min']} minutes\\n\\n"
                f"See you soon! 😊"
            )
        elif reminder_type == '2h':
            message = (
                f"⏰ **Appointment Reminder**\\n\\n"
                f"Hi {client['name']}! Your appointment is in 2 hours.\\n\\n"
                f"📋 **Service:** {service['name']}\\n"
                f"📅 **When:** {time_str}\\n\\n"
                f"See you soon! 🎉"
            )
        else:  # 30m
            message = (
                f"🚀 **Final Reminder**\\n\\n"
                f"Hi {client['name']}! Your appointment is in 30 minutes.\\n\\n"
                f"📋 **Service:** {service['name']}\\n"
                f"📅 **When:** {time_str}\\n\\n"
                f"See you shortly! 😊"
            )
        
        send_whatsapp_message(client['phone'], message)
        logger.info(f"Sent {reminder_type} reminder for appointment {apt.get('id')}")
        
    except Exception as e:
        logger.error(f"Error sending reminder: {str(e)}", exc_info=True)
