"""
Owner flow handlers for business management via WhatsApp.
"""
import logging
from datetime import datetime, time, date, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    Owner, OwnerSetting, Availability, Block, Service, 
    Appointment, Client, IntentMode, AppointmentStatus
)
from app.services.messaging import send_whatsapp, send_whatsapp_with_quick_replies
from app.utils.session import get_session, set_session, update_session, clear_session
from app.utils.time import (
    parse_human_time, format_datetime_for_user, now_in_timezone,
    get_duration_string, to_utc
)

logger = logging.getLogger(__name__)


async def handle_owner_message(phone: str, message: str, owner: Owner, db: Session):
    """
    Handle incoming message from business owner.
    
    Args:
        phone: Owner's phone number
        message: Message text
        owner: Owner database object
        db: Database session
    """
    try:
        # Get current session if any
        session = get_session(phone)
        
        # Check for global commands that work regardless of session
        if message.lower() in ['help', 'menu', 'commands']:
            await send_owner_help(phone)
            return
        
        if message.lower() in ['cancel', 'stop', 'exit']:
            if session:
                clear_session(phone)
                await send_whatsapp(phone, "❌ Cancelled current operation.")
            else:
                await send_whatsapp(phone, "👋 Hello! Send 'help' to see available commands.")
            return
        
        # If in a session, continue the flow
        if session:
            await handle_owner_session(phone, message, owner, session, db)
        else:
            # No session - handle direct commands
            await handle_owner_command(phone, message, owner, db)
            
    except Exception as e:
        logger.error(f"Error handling owner message from {phone}: {e}", exc_info=True)
        await send_whatsapp(phone, "❌ Sorry, I encountered an error. Please try again.")


async def handle_owner_command(phone: str, message: str, owner: Owner, db: Session):
    """Handle direct owner commands (no active session)."""
    
    command = message.lower().strip()
    
    if command == 'setup':
        await start_owner_setup(phone, owner, db)
    
    elif command in ['summary', 'today']:
        await send_daily_summary(phone, owner, db)
    
    elif command in ['optimize', 'suggestions', 'optimize today']:
        await send_optimization_suggestions(phone, owner, db)
    
    elif command.startswith('intent'):
        await handle_intent_change(phone, message, owner, db)
    
    elif command.startswith('block'):
        await handle_block_command(phone, message, owner, db)
    
    elif command.startswith('service'):
        await start_service_management(phone, owner, db)
    
    elif command.startswith('reminders'):
        await handle_reminders_command(phone, message, owner, db)
    
    elif command.startswith('settings'):
        await show_owner_settings(phone, owner, db)
    
    else:
        # Unknown command or casual message
        await send_whatsapp(
            phone, 
            f"👋 Hello {owner.name}! I didn't understand that command.\n\n"
            "Send 'help' to see available commands, or 'summary' for today's schedule."
        )


async def handle_owner_session(phone: str, message: str, owner: Owner, session, db: Session):
    """Handle owner message within an active session."""
    
    if session.state_type == 'owner_setup':
        await handle_setup_session(phone, message, owner, session, db)
    
    elif session.state_type == 'service_management':
        await handle_service_session(phone, message, owner, session, db)
    
    elif session.state_type == 'block_creation':
        await handle_block_session(phone, message, owner, session, db)
    
    else:
        logger.warning(f"Unknown session type: {session.state_type}")
        clear_session(phone)
        await send_whatsapp(phone, "❌ Session expired. Please try again.")


async def start_owner_setup(phone: str, owner: Owner, db: Session):
    """Start the owner setup flow."""
    
    # Check if owner already has settings
    settings = db.query(OwnerSetting).filter(OwnerSetting.owner_id == owner.id).first()
    
    if settings:
        await send_whatsapp(
            phone,
            f"⚙️ You already have settings configured.\n\n"
            f"Send 'settings' to view current configuration, or continue with setup to modify them."
        )
    
    # Start setup session
    set_session(phone, 'owner_setup', 'timezone')
    
    await send_whatsapp(
        phone,
        f"🚀 Let's set up your business!\n\n"
        f"First, what's your timezone?\n"
        f"Current: {owner.timezone}\n\n"
        f"Reply with a timezone (e.g., 'Asia/Jerusalem', 'America/New_York') or 'keep' to keep current."
    )


async def handle_setup_session(phone: str, message: str, owner: Owner, session, db: Session):
    """Handle owner setup session steps."""
    
    step = session.step
    
    if step == 'timezone':
        if message.lower() == 'keep':
            timezone = owner.timezone
        else:
            # TODO: Validate timezone
            timezone = message.strip()
        
        update_session(phone, 'work_hours', {'timezone': timezone})
        
        await send_whatsapp(
            phone,
            f"🕐 Great! Now let's set your work hours.\n\n"
            f"What days do you work? Reply with:\n"
            f"1. Monday-Friday\n"
            f"2. Monday-Saturday\n"
            f"3. Sunday-Thursday\n"
            f"4. Custom (I'll ask for each day)"
        )
    
    elif step == 'work_hours':
        work_pattern = message.strip()
        update_session(phone, 'work_times', {'work_pattern': work_pattern})
        
        await send_whatsapp(
            phone,
            f"⏰ What are your typical work hours?\n\n"
            f"Reply in format: START-END\n"
            f"Examples:\n"
            f"• 9:00-17:00\n"
            f"• 8am-6pm\n"
            f"• 10:00-19:30"
        )
    
    elif step == 'work_times':
        work_times = message.strip()
        update_session(phone, 'intent_mode', {'work_times': work_times})
        
        await send_whatsapp_with_quick_replies(
            phone,
            "🎯 How would you like me to optimize your schedule?",
            [
                "Max Profit - Pack appointments tightly, prioritize high-revenue services",
                "Balanced - Even spacing with micro-breaks between appointments", 
                "Free Time - Protect your free blocks, pack remaining time sensibly"
            ]
        )
    
    elif step == 'intent_mode':
        intent_map = {'1': 'profit', '2': 'balanced', '3': 'free_time'}
        intent = intent_map.get(message.strip(), 'balanced')
        
        update_session(phone, 'reminders', {'intent': intent})
        
        await send_whatsapp(
            phone,
            f"⏰ When should I send appointment reminders?\n\n"
            f"Reply with hours before appointment (comma-separated):\n"
            f"Examples:\n"
            f"• 24,2 (24 hours and 2 hours before)\n"
            f"• 48,24,1 (2 days, 1 day, and 1 hour before)\n"
            f"• 2 (just 2 hours before)"
        )
    
    elif step == 'reminders':
        try:
            reminder_hours = [int(h.strip()) for h in message.split(',')]
            update_session(phone, 'policies', {'reminder_hours': reminder_hours})
            
            await send_whatsapp(
                phone,
                f"📋 Almost done! A few policy questions:\n\n"
                f"What's the minimum lead time for bookings? (in minutes)\n"
                f"Examples:\n"
                f"• 60 (1 hour advance notice)\n"
                f"• 120 (2 hours advance notice)\n"
                f"• 1440 (24 hours advance notice)"
            )
        except ValueError:
            await send_whatsapp(phone, "❌ Please enter valid numbers separated by commas (e.g., 24,2)")
            return
    
    elif step == 'policies':
        try:
            lead_time = int(message.strip())
            update_session(phone, 'complete', {'lead_time': lead_time})
            
            # Save all settings to database
            await complete_owner_setup(phone, owner, session, db)
            
        except ValueError:
            await send_whatsapp(phone, "❌ Please enter a valid number of minutes.")
            return


async def complete_owner_setup(phone: str, owner: Owner, session, db: Session):
    """Complete owner setup and save to database."""
    
    try:
        data = session.data
        
        # Update owner
        owner.timezone = data.get('timezone', owner.timezone)
        owner.default_intent = IntentMode(data.get('intent', 'balanced'))
        
        # Create or update settings
        settings = db.query(OwnerSetting).filter(OwnerSetting.owner_id == owner.id).first()
        if not settings:
            settings = OwnerSetting(owner_id=owner.id)
            db.add(settings)
        
        settings.lead_time_min = data.get('lead_time', 60)
        settings.reminder_hours = data.get('reminder_hours', [24, 2])
        
        # TODO: Parse and create availability records from work_pattern and work_times
        
        db.commit()
        clear_session(phone)
        
        await send_whatsapp(
            phone,
            f"✅ Setup complete! Your business is ready.\n\n"
            f"🎯 Intent: {owner.default_intent.value.title()}\n"
            f"⏰ Lead time: {settings.lead_time_min} minutes\n"
            f"🔔 Reminders: {', '.join(map(str, settings.reminder_hours))} hours before\n\n"
            f"Next steps:\n"
            f"• Send 'service add [name]' to add your first service\n"
            f"• Send 'summary' to see today's schedule\n"
            f"• Send 'help' for all commands"
        )
        
    except Exception as e:
        logger.error(f"Error completing owner setup: {e}")
        await send_whatsapp(phone, "❌ Error saving settings. Please try setup again.")


async def send_daily_summary(phone: str, owner: Owner, db: Session):
    """Send daily summary to owner."""
    
    try:
        today = date.today()
        
        # Get today's appointments
        appointments = db.query(Appointment).filter(
            Appointment.owner_id == owner.id,
            func.date(Appointment.start_dt) == today,
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
        ).order_by(Appointment.start_dt).all()
        
        if not appointments:
            await send_whatsapp(
                phone,
                f"📅 **Today's Schedule** - {today.strftime('%A, %B %d')}\n\n"
                f"🆓 No appointments scheduled\n\n"
                f"Perfect day to relax or reach out to clients!"
            )
            return
        
        # Calculate summary stats
        total_revenue = sum(apt.service.price_cents for apt in appointments)
        first_apt = appointments[0]
        last_apt = appointments[-1]
        
        # Format appointment list
        apt_list = []
        for apt in appointments:
            time_str = format_datetime_for_user(apt.start_dt, owner.timezone, include_date=False)
            duration = get_duration_string(apt.service.duration_min)
            price = f"${apt.service.price_cents / 100:.0f}"
            
            apt_list.append(f"• {time_str} - {apt.service.name} ({duration}) - {price}")
        
        # Get waitlist count
        waitlist_count = db.query(func.count()).select_from(
            db.query(Waitlist).filter(Waitlist.owner_id == owner.id)
        ).scalar()
        
        summary = (
            f"📅 **Today's Schedule** - {today.strftime('%A, %B %d')}\n\n"
            f"📊 **Summary:**\n"
            f"• {len(appointments)} appointments\n"
            f"• ${total_revenue / 100:.0f} projected revenue\n"
            f"• {format_datetime_for_user(first_apt.start_dt, owner.timezone, False)} - "
            f"{format_datetime_for_user(last_apt.end_dt, owner.timezone, False)}\n"
        )
        
        if waitlist_count > 0:
            summary += f"• {waitlist_count} clients on waitlist\n"
        
        summary += f"\n📋 **Appointments:**\n" + "\n".join(apt_list)
        
        await send_whatsapp(phone, summary)
        
    except Exception as e:
        logger.error(f"Error sending daily summary: {e}")
        await send_whatsapp(phone, "❌ Error generating summary. Please try again.")


async def send_optimization_suggestions(phone: str, owner: Owner, db: Session):
    """Send optimization suggestions to owner."""
    
    try:
        from app.services.optimizer import get_optimization_suggestions
        from app.utils.time import now_in_timezone
        
        # Get suggestions for today
        today = now_in_timezone(owner.timezone).date()
        result = await get_optimization_suggestions(db, owner.id, today)
        
        if not result["success"]:
            await send_whatsapp(phone, f"❌ Error getting suggestions: {result.get('error', 'Unknown error')}")
            return
        
        suggestions = result["suggestions"]
        
        if not suggestions:
            await send_whatsapp(
                phone,
                f"✨ **Schedule Optimization** - {today.strftime('%A, %B %d')}\n\n"
                f"🎯 Your schedule looks well optimized!\n\n"
                f"💡 **Current mode:** {owner.default_intent.value.title()}\n\n"
                f"**Tips:**\n"
                f"• Send 'intent: profit' to maximize revenue\n"
                f"• Send 'intent: balanced' for even spacing\n"
                f"• Send 'intent: free_time' to protect breaks"
            )
            return
        
        # Format suggestions
        message_parts = [
            f"✨ **Schedule Optimization** - {today.strftime('%A, %B %d')}\n",
            f"🎯 **Current mode:** {owner.default_intent.value.title()}\n",
            f"📊 **Found {len(suggestions)} optimization opportunities:**\n"
        ]
        
        for i, suggestion in enumerate(suggestions, 1):
            if suggestion["type"] == "fill_gap":
                gap_minutes = suggestion["gap_minutes"]
                message_parts.append(
                    f"{i}. **Fill Gap** - {gap_minutes}min gap available\n"
                    f"   💡 Perfect for shorter services or consultations"
                )
            elif suggestion["type"] == "revenue_optimization":
                message_parts.append(
                    f"{i}. **Revenue Boost** - {suggestion['suggestion']}\n"
                    f"   💰 Focus on higher-value services"
                )
        
        message_parts.extend([
            f"\n🚀 **Quick Actions:**",
            f"• Gaps will auto-fill from waitlist when appointments cancel",
            f"• Send 'intent: profit' to prioritize high-revenue services",
            f"• Send 'summary' to see today's full schedule"
        ])
        
        await send_whatsapp(phone, "\n".join(message_parts))
        
    except Exception as e:
        logger.error(f"Error sending optimization suggestions: {e}")
        await send_whatsapp(phone, "❌ Error generating optimization suggestions. Please try again.")


async def handle_intent_change(phone: str, message: str, owner: Owner, db: Session):
    """Handle intent mode change command."""
    
    parts = message.lower().split()
    if len(parts) < 2:
        await send_whatsapp_with_quick_replies(
            phone,
            "🎯 Choose your scheduling intent:",
            ["Profit", "Balanced", "Free Time"]
        )
        return
    
    intent_map = {
        'profit': IntentMode.PROFIT,
        'balanced': IntentMode.BALANCED,
        'free': IntentMode.FREE_TIME,
        'free_time': IntentMode.FREE_TIME
    }
    
    new_intent = intent_map.get(parts[1])
    if not new_intent:
        await send_whatsapp(phone, "❌ Invalid intent. Choose: profit, balanced, or free_time")
        return
    
    owner.default_intent = new_intent
    db.commit()
    
    await send_whatsapp(
        phone,
        f"✅ Intent changed to: **{new_intent.value.title()}**\n\n"
        f"This will affect how I suggest appointment times going forward."
    )


async def send_owner_help(phone: str):
    """Send help message with available commands."""
    
    help_text = (
        "🤖 **Owner Commands**\n\n"
        "**Setup & Settings:**\n"
        "• `setup` - Initial business setup\n"
        "• `settings` - View current settings\n"
        "• `intent [profit/balanced/free_time]` - Change scheduling mode\n\n"
        "**Schedule Management:**\n"
        "• `summary` or `today` - Today's schedule\n"
        "• `block [time] [reason]` - Block time (e.g., 'block 2-3pm lunch')\n\n"
        "**Services:**\n"
        "• `service add [name]` - Add new service\n"
        "• `service list` - View all services\n\n"
        "**Other:**\n"
        "• `help` - Show this help\n"
        "• `cancel` - Cancel current operation\n\n"
        "💡 **Tips:**\n"
        "• Most commands work conversationally\n"
        "• I'll guide you through multi-step processes\n"
        "• Send 'cancel' anytime to stop"
    )
    
    await send_whatsapp(phone, help_text)


async def show_owner_settings(phone: str, owner: Owner, db: Session):
    """Show current owner settings."""
    
    settings = db.query(OwnerSetting).filter(OwnerSetting.owner_id == owner.id).first()
    
    if not settings:
        await send_whatsapp(
            phone,
            "⚙️ No settings configured yet.\n\nSend 'setup' to get started!"
        )
        return
    
    # Count services and availability
    service_count = db.query(func.count()).select_from(
        db.query(Service).filter(Service.owner_id == owner.id, Service.active == True)
    ).scalar()
    
    availability_count = db.query(func.count()).select_from(
        db.query(Availability).filter(Availability.owner_id == owner.id, Availability.active == True)
    ).scalar()
    
    settings_text = (
        f"⚙️ **Your Settings**\n\n"
        f"👤 **Business Info:**\n"
        f"• Name: {owner.name}\n"
        f"• Phone: {owner.phone}\n"
        f"• Timezone: {owner.timezone}\n\n"
        f"🎯 **Scheduling:**\n"
        f"• Intent: {owner.default_intent.value.title()}\n"
        f"• Lead time: {settings.lead_time_min} minutes\n"
        f"• Cancel window: {settings.cancel_window_hr} hours\n"
        f"• Reminders: {', '.join(map(str, settings.reminder_hours))} hours before\n\n"
        f"📊 **Current Setup:**\n"
        f"• {service_count} active services\n"
        f"• {availability_count} availability slots\n\n"
        f"To modify, send 'setup' to reconfigure."
    )
    
    await send_whatsapp(phone, settings_text)


# Placeholder functions for other owner flows
async def start_service_management(phone: str, owner: Owner, db: Session):
    """Start service management flow."""
    await send_whatsapp(phone, "🔧 Service management coming in Task 5!")


async def handle_block_command(phone: str, message: str, owner: Owner, db: Session):
    """Handle block time command."""
    await send_whatsapp(phone, "🚫 Block management coming in Task 5!")


async def handle_reminders_command(phone: str, message: str, owner: Owner, db: Session):
    """Handle reminders configuration."""
    await send_whatsapp(phone, "⏰ Reminder configuration coming in Task 5!")
