"""
Client flow handlers for appointment booking via WhatsApp.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models import (
    Owner, Client, Service, Appointment, Waitlist,
    AppointmentStatus, IntentMode
)
from app.services.messaging import send_whatsapp, send_whatsapp_with_quick_replies
from app.utils.session import get_session, set_session, update_session, clear_session
from app.utils.time import (
    parse_human_time, format_datetime_for_user, now_in_timezone
)

logger = logging.getLogger(__name__)


async def handle_client_message(phone: str, message: str, db: Session):
    """
    Handle incoming message from client.
    
    Args:
        phone: Client's phone number
        message: Message text
        db: Database session
    """
    try:
        # Get current session if any
        session = get_session(phone)
        
        # Check for global commands
        if message.lower() in ['help', 'menu']:
            await send_client_help(phone)
            return
        
        if message.lower() in ['stop', 'exit']:
            if session:
                clear_session(phone)
                await send_whatsapp(phone, "❌ Cancelled. Send 'book' to make a new appointment.")
            else:
                await send_whatsapp(phone, "👋 Hello! Send 'book' to schedule an appointment.")
            return
        
        if message.lower() in ['restart', 'start over', 'new conversation']:
            if session:
                clear_session(phone)
                await send_whatsapp(phone, "🔄 Starting fresh! How can I help you today?")
            else:
                await send_whatsapp(phone, "👋 Hello! Send 'book' to schedule an appointment.")
            return
        
        # If in a session, continue the flow
        if session:
            await handle_client_session(phone, message, session, db)
        else:
            # No session - handle direct commands or start booking
            await handle_client_command(phone, message, db)
            
    except Exception as e:
        logger.error(f"Error handling client message from {phone}: {e}", exc_info=True)
        await send_whatsapp(phone, "❌ Sorry, I encountered an error. Please try again.")


async def handle_client_command(phone: str, message: str, db: Session):
    """Handle direct client commands (no active session)."""
    
    # Clean the command - remove markdown formatting and extra whitespace
    command = message.lower().strip()
    # Remove markdown formatting like **text** or *text*
    command = command.replace('**', '').replace('*', '').strip()
    
    logger.info(f"Processing client command: '{command}' (original: '{message}')")
    
    if command in ['book', 'appointment', 'schedule']:
        await start_booking_flow(phone, db)
    
    elif command in ['reschedule', 'change', 'move']:
        await start_reschedule_flow(phone, db)
    
    elif command in ['cancel', 'cancel appointment']:
        await start_cancel_flow(phone, db)
    
    elif command in ['waitlist', 'wait list', 'waiting list', 'my waitlist', 'show waitlist', 'remove waitlist', 'leave waitlist', 'cancel waitlist']:
        from app.services.waitlist import process_waitlist_command
        
        # Find owner for this client (use first owner if multiple)
        client = db.query(Client).filter(Client.phone == phone).first()
        owner_id = client.owner_id if client else None
        
        if not owner_id:
            await send_whatsapp(phone, "❌ No booking history found. Please book an appointment first.")
            return
        
        response = await process_waitlist_command(db, phone, command, owner_id)
        await send_whatsapp(phone, response)
    
    elif command in ['my appointments', 'appointments', 'bookings']:
        await show_client_appointments(phone, db)
    
    else:
        # Check for natural language patterns
        if _is_appointment_request(message):
            await show_client_appointments(phone, db)
        elif _is_booking_request(message):
            await start_booking_flow(phone, db)
        elif _is_cancel_request(message):
            await start_cancel_flow(phone, db)
        elif _is_reschedule_request(message):
            await start_reschedule_flow(phone, db)
        else:
            # Unknown command - assume they want to book
            await send_whatsapp(
                phone,
                f"👋 Hello! I can help you book an appointment.\n\n"
                f"Available commands:\n"
                f"• **book** - Schedule new appointment\n"
                f"• **reschedule** - Change existing appointment\n"
                f"• **cancel** - Cancel appointment\n"
                f"• **appointments** - View your bookings\n\n"
                f"What would you like to do?"
            )


async def handle_client_session(phone: str, message: str, session, db: Session):
    """Handle client message within an active session."""
    
    # Check if user is trying to start fresh with natural language
    if _is_natural_language_command(message):
        # Check if it's a specific request that should be handled directly
        if _is_appointment_request(message):
            clear_session(phone)
            await show_client_appointments(phone, db)
            return
        elif _is_booking_request(message):
            clear_session(phone)
            await start_booking_flow(phone, db)
            return
        elif _is_cancel_request(message):
            clear_session(phone)
            await start_cancel_flow(phone, db)
            return
        elif _is_reschedule_request(message):
            clear_session(phone)
            await start_reschedule_flow(phone, db)
            return
        else:
            # Generic natural language - offer help
            await send_whatsapp(
                phone,
                f"🔄 I see you're in the middle of a {session.state_type.replace('_', ' ')} process.\n\n"
                f"Would you like to:\n"
                f"• **Continue** - Reply with a number or specific answer\n"
                f"• **Start fresh** - Type 'restart' to begin a new conversation\n"
                f"• **Cancel** - Type 'cancel' to stop and return to main menu\n\n"
                f"Or just tell me what you'd like to do and I'll help you!"
            )
            return
    
    if session.state_type == 'client_booking':
        await handle_booking_session(phone, message, session, db)
    
    elif session.state_type == 'client_reschedule':
        await handle_reschedule_session(phone, message, session, db)
    
    elif session.state_type == 'client_cancel':
        await handle_cancel_session(phone, message, session, db)
    
    elif session.state_type == 'client_waitlist':
        await handle_waitlist_session(phone, message, session, db)
    
    else:
        logger.warning(f"Unknown client session type: {session.state_type}")
        clear_session(phone)
        await send_whatsapp(phone, "❌ Session expired. Please try again.")


def _is_natural_language_command(message: str) -> bool:
    """Check if message is natural language vs. a specific command/number."""
    message_lower = message.lower().strip()
    
    # Check for natural language patterns
    natural_patterns = [
        'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening',
        'i would like', 'i want', 'i need', 'can you', 'could you', 'please',
        'book', 'appointment', 'schedule', 'cancel', 'reschedule', 'change',
        'waitlist', 'wait list', 'my appointments', 'show me', 'help me'
    ]
    
    # Check if message contains natural language patterns
    for pattern in natural_patterns:
        if pattern in message_lower:
            return True
    
    # Check if it's not just a number (which would be a valid session response)
    try:
        int(message.strip())
        return False  # It's a number, not natural language
    except ValueError:
        pass
    
    # Check if it's a short command
    if message_lower in ['yes', 'no', 'y', 'n', 'confirm', 'cancel', 'restart']:
        return False
    
    # If it's longer than 10 characters and contains spaces, likely natural language
    if len(message) > 10 and ' ' in message:
        return True
    
    return False


def _is_appointment_request(message: str) -> bool:
    """Check if message is requesting to see appointments."""
    message_lower = message.lower().strip()
    
    appointment_patterns = [
        'show me my appointments', 'my appointments', 'my bookings', 'upcoming appointments',
        'can you show me my appointments', 'show appointments', 'view appointments', 'see appointments',
        'what appointments', 'list appointments', 'appointment list', 'show me appointments'
    ]
    
    for pattern in appointment_patterns:
        if pattern in message_lower:
            return True
    
    # Check for single word "appointments" but not if it's part of other commands
    if message_lower == 'appointments' or message_lower == 'my appointments':
        return True
    
    return False


def _is_booking_request(message: str) -> bool:
    """Check if message is requesting to book an appointment."""
    message_lower = message.lower().strip()
    
    # More specific booking patterns to avoid false positives
    booking_patterns = [
        'i would like to book', 'i want to book', 'book an appointment',
        'make an appointment', 'schedule an appointment', 'book me',
        'schedule me', 'book a haircut', 'book a trim'
    ]
    
    # Check for specific booking phrases
    for pattern in booking_patterns:
        if pattern in message_lower:
            return True
    
    # Check for single word "book" but not if it's part of other commands
    if message_lower == 'book' or message_lower == 'book appointment':
        return True
    
    return False


def _is_cancel_request(message: str) -> bool:
    """Check if message is requesting to cancel an appointment."""
    message_lower = message.lower().strip()
    
    cancel_patterns = [
        'cancel', 'cancel appointment', 'cancel my appointment', 'i need to cancel',
        'can i cancel', 'cancel booking', 'remove appointment'
    ]
    
    for pattern in cancel_patterns:
        if pattern in message_lower:
            return True
    
    return False


def _is_reschedule_request(message: str) -> bool:
    """Check if message is requesting to reschedule an appointment."""
    message_lower = message.lower().strip()
    
    reschedule_patterns = [
        'reschedule', 'change appointment', 'change time', 'move appointment',
        'i need to reschedule', 'can i reschedule', 'change my appointment'
    ]
    
    for pattern in reschedule_patterns:
        if pattern in message_lower:
            return True
    
    return False


async def start_booking_flow(phone: str, db: Session):
    """Start the appointment booking flow."""
    
    # For now, assume single owner system - in multi-tenant, we'd need to identify the business
    owner = db.query(Owner).first()
    if not owner:
        await send_whatsapp(phone, "❌ No business found. Please contact support.")
        return
    
    # Get active services
    services = db.query(Service).filter(
        Service.owner_id == owner.id,
        Service.active == True
    ).all()
    
    if not services:
        await send_whatsapp(
            phone,
            f"❌ Sorry, no services are available for booking right now. "
            f"Please contact {owner.name} directly."
        )
        return
    
    # Start booking session
    set_session(phone, 'client_booking', 'name', {'owner_id': owner.id})
    
    await send_whatsapp(
        phone,
        f"👋 Hello! I'm {owner.name}'s booking assistant.\n\n"
        f"To get started, what's your name?"
    )


async def handle_booking_session(phone: str, message: str, session, db: Session):
    """Handle booking session steps."""
    
    step = session.step
    owner_id = session.data['owner_id']
    
    if step == 'name':
        name = message.strip()
        if len(name) < 2:
            await send_whatsapp(phone, "Please enter your full name.")
            return
        
        # Check if client exists
        client = db.query(Client).filter(
            Client.owner_id == owner_id,
            Client.phone == phone
        ).first()
        
        if not client:
            # Create new client
            client = Client(
                owner_id=owner_id,
                phone=phone,
                name=name
            )
            db.add(client)
            db.commit()
        else:
            # Update name if different
            client.name = name
            db.commit()
        
        update_session(phone, 'service', {'client_id': client.id, 'name': name})
        
        # Show available services
        await show_services_for_booking(phone, owner_id, db)
    
    elif step == 'service':
        try:
            service_choice = int(message.strip())
            services = db.query(Service).filter(
                Service.owner_id == owner_id,
                Service.active == True
            ).all()
            
            if 1 <= service_choice <= len(services):
                selected_service = services[service_choice - 1]
                update_session(phone, 'time_preference', {'service_id': selected_service.id})
                
                await send_whatsapp_with_quick_replies(
                    phone,
                    f"Great! You selected: **{selected_service.name}**\n"
                    f"Duration: {selected_service.duration_min} minutes\n"
                    f"Price: ${selected_service.price_cents / 100:.0f}\n\n"
                    f"When would you prefer your appointment?",
                    ["Today", "Tomorrow", "This week", "Next week"]
                )
            else:
                await send_whatsapp(phone, "❌ Invalid choice. Please select a number from the list.")
                
        except ValueError:
            await send_whatsapp(phone, "❌ Please enter the number of your chosen service.")
    
    elif step == 'time_preference':
        # Map number choices to preference strings
        preference_map = {'1': 'today', '2': 'tomorrow', '3': 'this_week', '4': 'next_week'}
        preference = preference_map.get(message.strip())
        
        if not preference:
            await send_whatsapp(phone, "❌ Invalid choice. Please select 1, 2, 3, or 4.")
            return
        
        logger.info(f"Time preference selected: {message.strip()} -> {preference}")
        
        # Get service from session
        service_id = session.data.get('service_id')
        if not service_id:
            await send_whatsapp(phone, "❌ Session error. Please start over with 'book'.")
            clear_session(phone)
            return
        
        service = db.query(Service).get(service_id)
        if not service:
            await send_whatsapp(phone, "❌ Service not found. Please start over with 'book'.")
            clear_session(phone)
            return
        
        # Find available slots using the scheduling engine
        from app.services.scheduler import suggest_slots
        
        try:
            slot_suggestion = suggest_slots(db, service.owner, service, preference)
            
            if not slot_suggestion.slots:
                # No slots available
                update_session(phone, 'waitlist_offer', {'preference': preference})
                await send_whatsapp(phone, slot_suggestion.message)
            else:
                # Store slots in session and show them
                slots_data = []
                for slot in slot_suggestion.slots:
                    slots_data.append({
                        'start_dt': slot.start_dt.isoformat(),
                        'end_dt': slot.end_dt.isoformat(),
                        'service_id': slot.service_id,
                        'price_cents': slot.price_cents
                    })
                
                update_session(phone, 'confirm', {
                    'preference': preference,
                    'available_slots': slots_data
                })
                
                await send_whatsapp(phone, slot_suggestion.message)
                
        except Exception as e:
            logger.error(f"Error finding slots: {e}")
            await send_whatsapp(
                phone,
                "❌ Sorry, I encountered an error finding available times. Please try again or contact us directly."
            )
            clear_session(phone)
    
    elif step == 'confirm':
        if message.strip().lower() == 'waitlist':
            await start_waitlist_from_booking(phone, session, db)
            return
        
        try:
            slot_choice = int(message.strip())
            available_slots = session.data.get('available_slots', [])
            
            if 1 <= slot_choice <= len(available_slots):
                # Get selected slot
                selected_slot_data = available_slots[slot_choice - 1]
                
                # Get client and service
                client_id = session.data.get('client_id')
                service_id = selected_slot_data['service_id']
                
                client = db.query(Client).get(client_id)
                service = db.query(Service).get(service_id)
                
                if not client or not service:
                    await send_whatsapp(phone, "❌ Error retrieving booking details. Please try again.")
                    clear_session(phone)
                    return
                
                # Parse datetime
                from datetime import datetime
                start_dt = datetime.fromisoformat(selected_slot_data['start_dt'])
                
                # Book the appointment
                from app.services.scheduler import book_appointment
                
                try:
                    appointment = book_appointment(
                        db, service.owner, client, service, start_dt,
                        notes=f"Booked via WhatsApp by {client.name}"
                    )
                    
                    # Format confirmation message
                    from app.utils.time import format_datetime_for_user, get_duration_string
                    
                    time_str = format_datetime_for_user(appointment.start_dt, service.owner.timezone)
                    duration_str = get_duration_string(service.duration_min)
                    price_str = f"${service.price_cents / 100:.0f}"
                    
                    clear_session(phone)
                    
                    await send_whatsapp(
                        phone,
                        f"✅ **Appointment Confirmed!**\n\n"
                        f"📋 **Service:** {service.name}\n"
                        f"📅 **When:** {time_str}\n"
                        f"⏱️ **Duration:** {duration_str}\n"
                        f"💰 **Price:** {price_str}\n\n"
                        f"👤 **Business:** {service.owner.name}\n\n"
                        f"🔔 You'll receive reminders before your appointment.\n\n"
                        f"💡 **Need to make changes?**\n"
                        f"• Send 'reschedule' to change time\n"
                        f"• Send 'cancel' to cancel\n"
                        f"• Send 'appointments' to view all bookings"
                    )
                    
                except Exception as e:
                    logger.error(f"Error booking appointment: {e}")
                    await send_whatsapp(
                        phone,
                        f"❌ Sorry, that time slot is no longer available. Please try a different time.\n\n"
                        f"Send 'book' to see updated availability."
                    )
                    clear_session(phone)
            else:
                await send_whatsapp(phone, f"❌ Invalid choice. Please select a number between 1 and {len(available_slots)}.")
                
        except ValueError:
            await send_whatsapp(phone, "❌ Please enter the number of your preferred time.")
        except Exception as e:
            logger.error(f"Error in booking confirmation: {e}")
            await send_whatsapp(phone, "❌ An error occurred. Please try booking again.")
            clear_session(phone)


async def show_services_for_booking(phone: str, owner_id: int, db: Session):
    """Show available services with numbered options."""
    
    services = db.query(Service).filter(
        Service.owner_id == owner_id,
        Service.active == True
    ).all()
    
    if not services:
        await send_whatsapp(phone, "❌ No services available for booking.")
        return
    
    service_list = []
    for i, service in enumerate(services, 1):
        duration = f"{service.duration_min}min"
        price = f"${service.price_cents / 100:.0f}"
        service_list.append(f"{i}. **{service.name}** - {duration} - {price}")
    
    message = (
        f"💼 **Available Services:**\n\n" +
        "\n".join(service_list) +
        f"\n\nReply with the number of the service you'd like to book."
    )
    
    await send_whatsapp(phone, message)


async def start_reschedule_flow(phone: str, db: Session):
    """Start appointment rescheduling flow."""
    
    # Find client's upcoming appointments
    client = db.query(Client).filter(Client.phone == phone).first()
    if not client:
        await send_whatsapp(
            phone,
            "❌ No appointments found. Send 'book' to schedule your first appointment."
        )
        return
    
    from app.utils.time import now_in_timezone, to_utc, format_datetime_for_user
    
    # Get current time in UTC for comparison
    now_utc = to_utc(now_in_timezone())
    
    upcoming_appointments = db.query(Appointment).filter(
        Appointment.client_id == client.id,
        Appointment.start_dt > now_utc,
        Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
    ).order_by(Appointment.start_dt).all()
    
    if not upcoming_appointments:
        await send_whatsapp(
            phone,
            "❌ No upcoming appointments to reschedule. Send 'book' to schedule a new one."
        )
        return
    
    # Show appointments to reschedule
    if len(upcoming_appointments) == 1:
        # Only one appointment, start rescheduling directly
        appointment = upcoming_appointments[0]
        set_session(phone, 'client_reschedule', 'new_time', {
            'appointment_id': appointment.id
        })
        
        time_str = format_datetime_for_user(appointment.start_dt, appointment.owner.timezone)
        
        await send_whatsapp(
            phone,
            f"🔄 **Reschedule Appointment**\n\n"
            f"📋 Current: {appointment.service.name}\n"
            f"📅 {time_str}\n\n"
            f"When would you prefer your new appointment?\n"
            f"1. Today\n"
            f"2. Tomorrow\n"
            f"3. This week\n"
            f"4. Next week\n\n"
            f"Reply with the number of your preference."
        )
    else:
        # Multiple appointments, let client choose which to reschedule
        apt_list = []
        for i, apt in enumerate(upcoming_appointments, 1):
            time_str = format_datetime_for_user(apt.start_dt, apt.owner.timezone)
            apt_list.append(f"{i}. {apt.service.name} - {time_str}")
        
        # Store appointments in session
        apt_data = [{'id': apt.id} for apt in upcoming_appointments]
        set_session(phone, 'client_reschedule', 'select_appointment', {
            'appointments': apt_data
        })
        
        message = (
            f"🔄 **Which appointment would you like to reschedule?**\n\n" +
            "\n".join(apt_list) +
            f"\n\nReply with the number of the appointment to reschedule."
        )
        
        await send_whatsapp(phone, message)


async def start_cancel_flow(phone: str, db: Session):
    """Start appointment cancellation flow."""
    
    # Find client's upcoming appointments
    client = db.query(Client).filter(Client.phone == phone).first()
    if not client:
        await send_whatsapp(
            phone,
            "❌ No appointments found. Send 'book' to schedule your first appointment."
        )
        return
    
    from app.utils.time import now_in_timezone, to_utc, format_datetime_for_user
    
    # Get current time in UTC for comparison
    now_utc = to_utc(now_in_timezone())
    
    upcoming_appointments = db.query(Appointment).filter(
        Appointment.client_id == client.id,
        Appointment.start_dt > now_utc,
        Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
    ).order_by(Appointment.start_dt).all()
    
    if not upcoming_appointments:
        await send_whatsapp(
            phone,
            "❌ No upcoming appointments to cancel. Send 'book' to schedule a new one."
        )
        return
    
    # Show appointments to cancel
    if len(upcoming_appointments) == 1:
        # Only one appointment, confirm cancellation
        appointment = upcoming_appointments[0]
        set_session(phone, 'client_cancel', 'confirm', {
            'appointment_id': appointment.id
        })
        
        time_str = format_datetime_for_user(appointment.start_dt, appointment.owner.timezone)
        
        await send_whatsapp(
            phone,
            f"❌ **Cancel Appointment**\n\n"
            f"📋 Service: {appointment.service.name}\n"
            f"📅 {time_str}\n"
            f"💰 ${appointment.service.price_cents / 100:.0f}\n\n"
            f"⚠️ Are you sure you want to cancel this appointment?\n\n"
            f"Reply 'yes' to confirm cancellation or 'no' to keep the appointment."
        )
    else:
        # Multiple appointments, let client choose which to cancel
        apt_list = []
        for i, apt in enumerate(upcoming_appointments, 1):
            time_str = format_datetime_for_user(apt.start_dt, apt.owner.timezone)
            price_str = f"${apt.service.price_cents / 100:.0f}"
            apt_list.append(f"{i}. {apt.service.name} - {time_str} - {price_str}")
        
        # Store appointments in session
        apt_data = [{'id': apt.id} for apt in upcoming_appointments]
        set_session(phone, 'client_cancel', 'select_appointment', {
            'appointments': apt_data
        })
        
        message = (
            f"❌ **Which appointment would you like to cancel?**\n\n" +
            "\n".join(apt_list) +
            f"\n\nReply with the number of the appointment to cancel."
        )
        
        await send_whatsapp(phone, message)


async def start_waitlist_flow(phone: str, db: Session):
    """Start waitlist signup flow."""
    
    # TODO: Implement waitlist flow in Task 6
    await send_whatsapp(phone, "📋 Waitlist feature coming soon!")


async def start_waitlist_from_booking(phone: str, session, db: Session):
    """Start waitlist from booking session when no slots available."""
    
    try:
        # Get booking context from session
        service_id = session.data.get('service_id')
        preference = session.data.get('preference', 'this_week')
        
        if not service_id:
            await send_whatsapp(phone, "❌ Session error. Please start over with 'book'.")
            clear_session(phone)
            return
        
        service = db.query(Service).get(service_id)
        if not service:
            await send_whatsapp(phone, "❌ Service not found. Please start over with 'book'.")
            clear_session(phone)
            return
        
        # Process waitlist signup
        from app.services.waitlist import WaitlistManager
        
        manager = WaitlistManager(db)
        result = await manager.process_waitlist_signup(
            phone, service.owner_id, service_id, preference
        )
        
        if result["success"]:
            clear_session(phone)
            # Confirmation message is sent by the waitlist manager
        else:
            await send_whatsapp(
                phone,
                f"❌ Error adding to waitlist: {result.get('error', 'Unknown error')}\n\n"
                f"Please try again or contact us directly."
            )
            clear_session(phone)
            
    except Exception as e:
        logger.error(f"Error in waitlist signup: {e}")
        await send_whatsapp(
            phone,
            "❌ Error processing waitlist signup. Please try again or contact us directly."
        )
        clear_session(phone)


async def show_client_appointments(phone: str, db: Session):
    """Show client's current appointments."""
    
    client = db.query(Client).filter(Client.phone == phone).first()
    if not client:
        await send_whatsapp(
            phone,
            "❌ No appointments found. Send 'book' to schedule your first appointment."
        )
        return
    
    # Get upcoming appointments
    upcoming = db.query(Appointment).filter(
        Appointment.client_id == client.id,
        Appointment.start_dt > datetime.utcnow(),
        Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
    ).order_by(Appointment.start_dt).all()
    
    if not upcoming:
        await send_whatsapp(
            phone,
            f"📅 Hi {client.name}!\n\n"
            f"You have no upcoming appointments.\n\n"
            f"Send 'book' to schedule a new appointment."
        )
        return
    
    # Format appointments
    apt_list = []
    for apt in upcoming:
        owner = apt.owner
        time_str = format_datetime_for_user(apt.start_dt, owner.timezone)
        status_emoji = "⏳" if apt.status == AppointmentStatus.PENDING else "✅"
        
        apt_list.append(
            f"{status_emoji} **{apt.service.name}**\n"
            f"   📅 {time_str}\n"
            f"   ⏱️ {apt.service.duration_min} minutes\n"
            f"   💰 ${apt.service.price_cents / 100:.0f}"
        )
    
    message = (
        f"📅 **Your Appointments**\n\n" +
        "\n\n".join(apt_list) +
        f"\n\n💡 Send 'reschedule' to change or 'cancel' to cancel an appointment."
    )
    
    await send_whatsapp(phone, message)


async def send_client_help(phone: str):
    """Send help message for clients."""
    
    help_text = (
        "🤖 **Appointment Assistant**\n\n"
        "**Available Commands:**\n"
        "• `book` - Schedule new appointment\n"
        "• `reschedule` - Change existing appointment\n"
        "• `cancel` - Cancel appointment\n"
        "• `appointments` - View your bookings\n"
        "• `waitlist` - View your waitlist status\n"
        "• `remove waitlist` - Leave all waitlists\n"
        "• `help` - Show this help\n\n"
        "💡 **Tips:**\n"
        "• Just send 'book' to get started\n"
        "• I'll guide you through the process\n"
        "• Get instant notifications when slots open up!\n"
        "• Send 'cancel' anytime to stop\n\n"
        "Need human help? Contact us directly!"
    )
    
    await send_whatsapp(phone, help_text)


# Session handlers for reschedule and cancel flows
async def handle_reschedule_session(phone: str, message: str, session, db: Session):
    """Handle reschedule session steps."""
    
    step = session.step
    
    if step == 'select_appointment':
        try:
            choice = int(message.strip())
            appointments = session.data.get('appointments', [])
            
            if 1 <= choice <= len(appointments):
                appointment_id = appointments[choice - 1]['id']
                appointment = db.query(Appointment).get(appointment_id)
                
                if not appointment:
                    await send_whatsapp(phone, "❌ Appointment not found. Please try again.")
                    clear_session(phone)
                    return
                
                update_session(phone, 'new_time', {'appointment_id': appointment_id})
                
                from app.utils.time import format_datetime_for_user
                time_str = format_datetime_for_user(appointment.start_dt, appointment.owner.timezone)
                
                await send_whatsapp(
                    phone,
                    f"🔄 **Reschedule Appointment**\n\n"
                    f"📋 Current: {appointment.service.name}\n"
                    f"📅 {time_str}\n\n"
                    f"When would you prefer your new appointment?\n"
                    f"1. Today\n"
                    f"2. Tomorrow\n"
                    f"3. This week\n"
                    f"4. Next week\n\n"
                    f"Reply with the number of your preference."
                )
            else:
                await send_whatsapp(phone, f"❌ Invalid choice. Please select 1-{len(appointments)}.")
                
        except ValueError:
            await send_whatsapp(phone, "❌ Please enter a valid number.")
    
    elif step == 'new_time':
        preference_map = {'1': 'today', '2': 'tomorrow', '3': 'this_week', '4': 'next_week'}
        preference = preference_map.get(message.strip())
        
        if not preference:
            await send_whatsapp(phone, "❌ Invalid choice. Please select 1, 2, 3, or 4.")
            return
        
        appointment_id = session.data.get('appointment_id')
        appointment = db.query(Appointment).get(appointment_id)
        
        if not appointment:
            await send_whatsapp(phone, "❌ Appointment not found. Please try again.")
            clear_session(phone)
            return
        
        # Find new slots
        from app.services.scheduler import suggest_slots
        
        try:
            slot_suggestion = suggest_slots(db, appointment.owner, appointment.service, preference)
            
            if not slot_suggestion.slots:
                await send_whatsapp(phone, slot_suggestion.message)
                clear_session(phone)
            else:
                # Store slots for confirmation
                slots_data = []
                for slot in slot_suggestion.slots:
                    slots_data.append({
                        'start_dt': slot.start_dt.isoformat(),
                        'end_dt': slot.end_dt.isoformat(),
                        'service_id': slot.service_id,
                        'price_cents': slot.price_cents
                    })
                
                update_session(phone, 'confirm_reschedule', {
                    'available_slots': slots_data
                })
                
                await send_whatsapp(phone, slot_suggestion.message)
                
        except Exception as e:
            logger.error(f"Error finding reschedule slots: {e}")
            await send_whatsapp(phone, "❌ Error finding new times. Please try again.")
            clear_session(phone)
    
    elif step == 'confirm_reschedule':
        try:
            slot_choice = int(message.strip())
            available_slots = session.data.get('available_slots', [])
            appointment_id = session.data.get('appointment_id')
            
            if 1 <= slot_choice <= len(available_slots):
                selected_slot_data = available_slots[slot_choice - 1]
                appointment = db.query(Appointment).get(appointment_id)
                
                if not appointment:
                    await send_whatsapp(phone, "❌ Appointment not found.")
                    clear_session(phone)
                    return
                
                # Parse new datetime
                from datetime import datetime
                new_start_dt = datetime.fromisoformat(selected_slot_data['start_dt'])
                
                # Reschedule the appointment
                from app.services.scheduler import AppointmentScheduler
                scheduler = AppointmentScheduler(db)
                
                try:
                    updated_appointment = scheduler.reschedule_appointment(appointment, new_start_dt)
                    
                    from app.utils.time import format_datetime_for_user
                    new_time_str = format_datetime_for_user(updated_appointment.start_dt, appointment.owner.timezone)
                    
                    clear_session(phone)
                    
                    await send_whatsapp(
                        phone,
                        f"✅ **Appointment Rescheduled!**\n\n"
                        f"📋 **Service:** {appointment.service.name}\n"
                        f"📅 **New Time:** {new_time_str}\n"
                        f"💰 **Price:** ${appointment.service.price_cents / 100:.0f}\n\n"
                        f"🔔 You'll receive updated reminders for your new appointment time."
                    )
                    
                except Exception as e:
                    logger.error(f"Error rescheduling appointment: {e}")
                    await send_whatsapp(
                        phone,
                        "❌ Sorry, that time slot is no longer available. Please try a different time."
                    )
                    clear_session(phone)
            else:
                await send_whatsapp(phone, f"❌ Invalid choice. Please select 1-{len(available_slots)}.")
                
        except ValueError:
            await send_whatsapp(phone, "❌ Please enter a valid number.")


async def handle_cancel_session(phone: str, message: str, session, db: Session):
    """Handle cancel session steps."""
    
    step = session.step
    
    if step == 'select_appointment':
        try:
            choice = int(message.strip())
            appointments = session.data.get('appointments', [])
            
            if 1 <= choice <= len(appointments):
                appointment_id = appointments[choice - 1]['id']
                appointment = db.query(Appointment).get(appointment_id)
                
                if not appointment:
                    await send_whatsapp(phone, "❌ Appointment not found. Please try again.")
                    clear_session(phone)
                    return
                
                update_session(phone, 'confirm', {'appointment_id': appointment_id})
                
                from app.utils.time import format_datetime_for_user
                time_str = format_datetime_for_user(appointment.start_dt, appointment.owner.timezone)
                
                await send_whatsapp(
                    phone,
                    f"❌ **Cancel Appointment**\n\n"
                    f"📋 Service: {appointment.service.name}\n"
                    f"📅 {time_str}\n"
                    f"💰 ${appointment.service.price_cents / 100:.0f}\n\n"
                    f"⚠️ Are you sure you want to cancel this appointment?\n\n"
                    f"Reply 'yes' to confirm cancellation or 'no' to keep the appointment."
                )
            else:
                await send_whatsapp(phone, f"❌ Invalid choice. Please select 1-{len(appointments)}.")
                
        except ValueError:
            await send_whatsapp(phone, "❌ Please enter a valid number.")
    
    elif step == 'confirm':
        response = message.strip().lower()
        
        if response in ['yes', 'y', 'confirm', 'cancel it']:
            appointment_id = session.data.get('appointment_id')
            appointment = db.query(Appointment).get(appointment_id)
            
            if not appointment:
                await send_whatsapp(phone, "❌ Appointment not found.")
                clear_session(phone)
                return
            
            # Cancel the appointment
            from app.services.scheduler import AppointmentScheduler
            scheduler = AppointmentScheduler(db)
            
            try:
                scheduler.cancel_appointment(appointment, "Client requested cancellation via WhatsApp")
                
                from app.utils.time import format_datetime_for_user
                time_str = format_datetime_for_user(appointment.start_dt, appointment.owner.timezone)
                
                clear_session(phone)
                
                await send_whatsapp(
                    phone,
                    f"✅ **Appointment Cancelled**\n\n"
                    f"📋 Service: {appointment.service.name}\n"
                    f"📅 {time_str}\n\n"
                    f"Your appointment has been successfully cancelled.\n\n"
                    f"💡 **Need to book again?**\n"
                    f"Send 'book' to schedule a new appointment."
                )
                
            except Exception as e:
                logger.error(f"Error cancelling appointment: {e}")
                await send_whatsapp(
                    phone,
                    f"❌ Unable to cancel appointment: {str(e)}\n\n"
                    f"Please contact us directly for assistance."
                )
                clear_session(phone)
        
        elif response in ['no', 'n', 'keep', 'don\'t cancel']:
            clear_session(phone)
            await send_whatsapp(
                phone,
                "👍 Appointment kept! Your booking remains unchanged.\n\n"
                "Send 'appointments' to view your bookings."
            )
        
        else:
            await send_whatsapp(phone, "❌ Please reply 'yes' to cancel or 'no' to keep the appointment.")


async def handle_waitlist_session(phone: str, message: str, session, db: Session):
    """Handle waitlist session - placeholder for Task 6."""
    await send_whatsapp(phone, "📋 Waitlist coming in Task 6!")
