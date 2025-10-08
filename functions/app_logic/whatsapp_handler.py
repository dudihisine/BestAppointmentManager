"""
WhatsApp Message Handler
Processes incoming WhatsApp messages and routes them to appropriate handlers
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from .firestore_db import FirestoreDB
from .twilio_client import send_whatsapp_message
from .scheduler import AppointmentScheduler
from .optimizer import OptimizationEngine

logger = logging.getLogger(__name__)


def handle_whatsapp_message(phone: str, message: str, db: FirestoreDB) -> str:
    """
    Main entry point for handling WhatsApp messages
    Returns the response message to send back
    """
    try:
        logger.info(f"Processing message from {phone}: {message}")
        
        # Determine if this is from a client or owner
        # For now, assume all messages are from clients
        # In production, you'd have a way to identify owners (special number or command)
        
        # Check if it's an owner command (starts with /owner)
        if message.strip().lower().startswith('/owner'):
            return handle_owner_message(phone, message[6:].strip(), db)
        
        # Otherwise, treat as client message
        return handle_client_message(phone, message, db)
        
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}", exc_info=True)
        return "❌ Sorry, I encountered an error. Please try again or contact support."


def handle_client_message(phone: str, message: str, db: FirestoreDB) -> str:
    """Handle messages from clients"""
    try:
        # Get or create client
        client = db.get_client_by_phone(phone)
        
        # Get session
        session = db.get_session(phone)
        
        # Clean message
        message_lower = message.lower().strip()
        
        # Global commands
        if message_lower in ['help', 'menu', 'start']:
            return get_client_help_message()
        
        if message_lower in ['stop', 'exit', 'cancel']:
            if session:
                db.clear_session(phone)
                return "❌ Cancelled. Send 'book' to make a new appointment."
            return "👋 Hello! Send 'book' to schedule an appointment."
        
        # If in session, continue the flow
        if session:
            return handle_client_session(phone, message, session, db)
        
        # No session - handle commands
        if message_lower in ['book', 'appointment', 'schedule']:
            return start_booking_flow(phone, db)
        
        elif message_lower in ['my appointments', 'appointments', 'bookings']:
            return show_client_appointments(phone, db)
        
        elif message_lower in ['reschedule', 'change']:
            return start_reschedule_flow(phone, db)
        
        elif 'cancel' in message_lower and 'appointment' in message_lower:
            return start_cancel_flow(phone, db)
        
        elif 'waitlist' in message_lower:
            return handle_waitlist_command(phone, message, db)
        
        # Natural language detection
        if any(word in message_lower for word in ['book', 'appointment', 'schedule', 'haircut', 'trim']):
            return start_booking_flow(phone, db)
        
        elif any(word in message_lower for word in ['show', 'my', 'upcoming']):
            return show_client_appointments(phone, db)
        
        # Default help message
        return get_client_help_message()
        
    except Exception as e:
        logger.error(f"Error handling client message: {str(e)}", exc_info=True)
        return "❌ Sorry, I encountered an error. Please try again."


def handle_owner_message(phone: str, message: str, db: FirestoreDB) -> str:
    """Handle messages from business owners"""
    try:
        # Owner commands start with /owner
        message_lower = message.lower().strip()
        
        # Get owner by phone
        owner = None
        owners = db.db.collection('owners').where('phone', '==', phone).limit(1).stream()
        for o in owners:
            owner_data = o.to_dict()
            owner_data['id'] = o.id
            owner = owner_data
            break
        
        if not owner:
            return "❌ You are not registered as a business owner. Contact support to set up your account."
        
        if message_lower in ['help', 'menu']:
            return get_owner_help_message()
        
        elif 'schedule' in message_lower or 'today' in message_lower:
            return show_owner_schedule(owner['id'], db)
        
        elif 'mode' in message_lower:
            return show_owner_mode(owner['id'], db)
        
        elif 'stats' in message_lower or 'report' in message_lower:
            return show_owner_stats(owner['id'], db)
        
        elif 'waitlist' in message_lower:
            return show_owner_waitlist(owner['id'], db)
        
        else:
            return get_owner_help_message()
        
    except Exception as e:
        logger.error(f"Error handling owner message: {str(e)}", exc_info=True)
        return "❌ Sorry, I encountered an error. Please try again."


# Client flow handlers
def start_booking_flow(phone: str, db: FirestoreDB) -> str:
    """Start the booking flow"""
    try:
        # Get first owner (single-owner system)
        owner = db.get_first_owner()
        if not owner:
            return "❌ No business found. Please contact support."
        
        # Get or create client
        client = db.get_client_by_phone(phone)
        if not client:
            # Start name collection
            db.set_session(phone, {
                'state_type': 'client_booking',
                'step': 'name',
                'data': {'owner_id': owner['id']}
            })
            return f"👋 Hello! I'm {owner['name']}'s booking assistant.\\n\\nTo get started, what's your name?"
        
        # Client exists, show services
        db.set_session(phone, {
            'state_type': 'client_booking',
            'step': 'service',
            'data': {'owner_id': owner['id'], 'client_id': client['id'], 'name': client['name']}
        })
        
        return get_services_message(owner['id'], db)
        
    except Exception as e:
        logger.error(f"Error starting booking flow: {str(e)}", exc_info=True)
        return "❌ Sorry, I couldn't start the booking process. Please try again."


def handle_client_session(phone: str, message: str, session: Dict[str, Any], db: FirestoreDB) -> str:
    """Handle client session based on current step"""
    try:
        state_type = session.get('state_type')
        step = session.get('step')
        data = session.get('data', {})
        
        if state_type == 'client_booking':
            return handle_booking_session(phone, message, step, data, db)
        
        elif state_type == 'client_reschedule':
            return handle_reschedule_session(phone, message, step, data, db)
        
        elif state_type == 'client_cancel':
            return handle_cancel_session(phone, message, step, data, db)
        
        else:
            db.clear_session(phone)
            return "❌ Session expired. Please try again."
            
    except Exception as e:
        logger.error(f"Error handling session: {str(e)}", exc_info=True)
        db.clear_session(phone)
        return "❌ Sorry, I encountered an error. Please start over."


def handle_booking_session(phone: str, message: str, step: str, data: Dict[str, Any], db: FirestoreDB) -> str:
    """Handle booking session steps"""
    try:
        if step == 'name':
            name = message.strip()
            if len(name) < 2:
                return "Please enter your full name."
            
            # Create client
            client_id = db.create_client({
                'owner_id': data['owner_id'],
                'phone': phone,
                'name': name
            })
            
            data['client_id'] = client_id
            data['name'] = name
            
            db.update_session(phone, {
                'step': 'service',
                'data': data
            })
            
            return get_services_message(data['owner_id'], db)
        
        elif step == 'service':
            try:
                service_choice = int(message.strip())
                services = db.get_services(data['owner_id'])
                
                if 1 <= service_choice <= len(services):
                    selected_service = services[service_choice - 1]
                    data['service_id'] = selected_service['id']
                    
                    db.update_session(phone, {
                        'step': 'time_preference',
                        'data': data
                    })
                    
                    return (f"Great! You selected: **{selected_service['name']}**\\n"
                           f"Duration: {selected_service['duration_min']} minutes\\n"
                           f"Price: ${selected_service['price_cents'] / 100:.0f}\\n\\n"
                           f"When would you prefer your appointment?\\n\\n"
                           f"1. Today\\n"
                           f"2. Tomorrow\\n"
                           f"3. This week\\n"
                           f"4. Next week")
                else:
                    return "❌ Please enter a valid number for your chosen service."
            except ValueError:
                return "❌ Please enter the number of your chosen service."
        
        elif step == 'time_preference':
            preference_map = {'1': 'today', '2': 'tomorrow', '3': 'this_week', '4': 'next_week'}
            preference = preference_map.get(message.strip())
            
            if not preference:
                return "❌ Invalid choice. Please select 1, 2, 3, or 4."
            
            # Find available slots
            scheduler = AppointmentScheduler(db)
            service = db.get_service(data['service_id'])
            owner = db.get_owner(data['owner_id'])
            
            slots = scheduler.find_available_slots(owner, service, preference)
            
            if not slots:
                return (f"😔 Sorry, no slots available for {preference.replace('_', ' ')}.\\n\\n"
                       f"Would you like to:\\n"
                       f"1. Try a different time\\n"
                       f"2. Join the waitlist\\n\\n"
                       f"Reply with 1 or 2")
            
            # Store slots and show them
            data['available_slots'] = [
                {
                    'start_dt': slot['start_dt'].isoformat(),
                    'end_dt': slot['end_dt'].isoformat()
                }
                for slot in slots[:5]
            ]
            
            db.update_session(phone, {
                'step': 'confirm',
                'data': data
            })
            
            slots_text = []
            for i, slot in enumerate(slots[:5]):
                time_str = slot['start_dt'].strftime('%A, %B %d at %H:%M')
                slots_text.append(f"{i+1}. {time_str}")
            
            return (f"📅 **Available slots for {service['name']}:**\\n\\n" +
                   "\\n".join(slots_text) + "\\n\\n"
                   f"Reply with the number of your preferred time.")
        
        elif step == 'confirm':
            try:
                slot_choice = int(message.strip())
                available_slots = data.get('available_slots', [])
                
                if not (1 <= slot_choice <= len(available_slots)):
                    return "❌ Please enter a valid slot number."
                
                selected_slot = available_slots[slot_choice - 1]
                
                # Book the appointment
                start_dt = datetime.fromisoformat(selected_slot['start_dt'])
                end_dt = datetime.fromisoformat(selected_slot['end_dt'])
                
                appointment_id = db.create_appointment({
                    'owner_id': data['owner_id'],
                    'client_id': data['client_id'],
                    'service_id': data['service_id'],
                    'start_dt': start_dt,
                    'end_dt': end_dt,
                    'status': 'CONFIRMED',
                    'channel': 'whatsapp'
                })
                
                db.clear_session(phone)
                
                service = db.get_service(data['service_id'])
                owner = db.get_owner(data['owner_id'])
                
                return (f"✅ **Appointment Confirmed!**\\n\\n"
                       f"📋 **Service:** {service['name']}\\n"
                       f"📅 **When:** {start_dt.strftime('%A, %B %d at %H:%M')}\\n"
                       f"⏱️ **Duration:** {service['duration_min']}m\\n"
                       f"💰 **Price:** ${service['price_cents'] / 100:.0f}\\n\\n"
                       f"👤 **Business:** {owner['name']}\\n\\n"
                       f"🔔 You'll receive reminders before your appointment.")
                
            except ValueError:
                return "❌ Please enter a valid number."
        
    except Exception as e:
        logger.error(f"Error in booking session: {str(e)}", exc_info=True)
        db.clear_session(phone)
        return "❌ Sorry, there was an error. Please try again by sending 'book'."


# Helper functions
def get_client_help_message() -> str:
    """Get client help message"""
    return ("👋 **Hello! I can help you with your appointments.**\\n\\n"
           "Available commands:\\n"
           "• **book** - Schedule new appointment\\n"
           "• **reschedule** - Change existing appointment\\n"
           "• **cancel** - Cancel appointment\\n"
           "• **appointments** - View your bookings\\n"
           "• **help** - Show this message\\n\\n"
           "What would you like to do?")


def get_owner_help_message() -> str:
    """Get owner help message"""
    return ("👨‍💼 **Owner Commands** (prefix with /owner)\\n\\n"
           "• **/owner schedule** - View today's schedule\\n"
           "• **/owner mode** - Check current intent mode\\n"
           "• **/owner stats** - View business statistics\\n"
           "• **/owner waitlist** - View waitlist\\n"
           "• **/owner help** - Show this message")


def get_services_message(owner_id: str, db: FirestoreDB) -> str:
    """Get formatted services message"""
    services = db.get_services(owner_id)
    
    if not services:
        return "❌ No services available for booking."
    
    service_list = []
    for i, service in enumerate(services):
        service_list.append(
            f"{i+1}. **{service['name']}** - {service['duration_min']}min - ${service['price_cents'] / 100:.0f}"
        )
    
    return (f"💼 **Available Services:**\\n\\n" +
           "\\n".join(service_list) + "\\n\\n"
           f"Reply with the number of the service you'd like to book.")


def show_client_appointments(phone: str, db: FirestoreDB) -> str:
    """Show client's appointments"""
    try:
        client = db.get_client_by_phone(phone)
        if not client:
            return "❌ No appointments found. Send 'book' to schedule one!"
        
        now = datetime.utcnow()
        appointments = db.get_client_appointments(client['id'], from_date=now)
        
        if not appointments:
            return "📅 You have no upcoming appointments.\\n\\nSend 'book' to schedule one!"
        
        apt_list = []
        for apt in appointments[:5]:  # Show max 5
            service = db.get_service(apt['service_id'])
            time_str = apt['start_dt'].strftime('%A, %B %d at %H:%M')
            apt_list.append(
                f"📋 **{service['name']}**\\n"
                f"   {time_str}\\n"
                f"   {service['duration_min']}min - ${service['price_cents'] / 100:.0f}"
            )
        
        return (f"📅 **Your Appointments**\\n\\n" +
               "\\n\\n".join(apt_list))
        
    except Exception as e:
        logger.error(f"Error showing appointments: {str(e)}", exc_info=True)
        return "❌ Error loading appointments."


def start_reschedule_flow(phone: str, db: FirestoreDB) -> str:
    """Start reschedule flow"""
    return "🔄 Reschedule feature coming soon! For now, please cancel and rebook."


def start_cancel_flow(phone: str, db: FirestoreDB) -> str:
    """Start cancel flow"""
    return "❌ Cancel feature coming soon! Please contact us directly."


def handle_waitlist_command(phone: str, message: str, db: FirestoreDB) -> str:
    """Handle waitlist commands"""
    return "📋 Waitlist feature coming soon!"


def show_owner_schedule(owner_id: str, db: FirestoreDB) -> str:
    """Show owner's daily schedule"""
    try:
        today = datetime.utcnow().date()
        appointments = db.get_owner_appointments(owner_id, today)
        
        if not appointments:
            return "📅 No appointments scheduled for today."
        
        apt_list = []
        for apt in appointments:
            client = db.get_client_by_phone(apt.get('client_phone', 'Unknown'))
            service = db.get_service(apt['service_id'])
            time_str = apt['start_dt'].strftime('%H:%M')
            apt_list.append(f"• {time_str} - {client['name'] if client else 'Unknown'} - {service['name']}")
        
        return (f"📅 **Today's Schedule ({len(appointments)} appointments)**\\n\\n" +
               "\\n".join(apt_list))
        
    except Exception as e:
        logger.error(f"Error showing schedule: {str(e)}", exc_info=True)
        return "❌ Error loading schedule."


def show_owner_mode(owner_id: str, db: FirestoreDB) -> str:
    """Show current intent mode"""
    settings = db.get_settings(owner_id)
    mode = settings.get('default_intent', 'balanced') if settings else 'balanced'
    return f"⚙️ Current mode: **{mode.title()}**"


def show_owner_stats(owner_id: str, db: FirestoreDB) -> str:
    """Show business statistics"""
    return "📊 Stats feature coming soon!"


def show_owner_waitlist(owner_id: str, db: FirestoreDB) -> str:
    """Show waitlist"""
    entries = db.get_waitlist_entries(owner_id)
    if not entries:
        return "📋 Waitlist is empty."
    return f"📋 **Waitlist:** {len(entries)} entries"
