"""
Professional message templates for WhatsApp conversations.
"""
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from app.utils.time import format_datetime_for_user, now_in_timezone


class MessageTemplates:
    """Professional message templates for different conversation flows."""
    
    @staticmethod
    def welcome_message(owner_name: str) -> str:
        """Welcome message for new clients."""
        return (
            f"👋 **Welcome to {owner_name}!**\n\n"
            f"I'm your AI booking assistant. I can help you:\n\n"
            f"📅 **Book appointments** - Schedule your next visit\n"
            f"🔄 **Reschedule** - Change existing appointments\n"
            f"❌ **Cancel** - Cancel if needed\n"
            f"📋 **View bookings** - See your upcoming appointments\n\n"
            f"💡 **Quick start:** Type 'book' to schedule an appointment!\n\n"
            f"How can I help you today? 😊"
        )
    
    @staticmethod
    def booking_start(owner_name: str) -> str:
        """Start of booking flow."""
        return (
            f"👋 **Hello! I'm {owner_name}'s booking assistant.**\n\n"
            f"Let's get you scheduled! To start, what's your name?"
        )
    
    @staticmethod
    def service_selection(services: List[Dict[str, Any]]) -> str:
        """Service selection message."""
        service_list = []
        for i, service in enumerate(services, 1):
            duration = f"{service['duration_min']}min"
            price = f"${service['price_cents'] / 100:.0f}"
            service_list.append(f"{i}. **{service['name']}** - {duration} - {price}")
        
        return (
            f"💼 **Available Services:**\n\n" +
            "\n".join(service_list) + "\n\n"
            f"Reply with the number of the service you'd like to book."
        )
    
    @staticmethod
    def time_preference(service_name: str, duration: int, price: float) -> str:
        """Time preference selection."""
        return (
            f"Great! You selected: **{service_name}**\n"
            f"Duration: {duration} minutes\n"
            f"Price: ${price:.0f}\n\n"
            f"When would you prefer your appointment?\n\n"
            f"1. Today\n"
            f"2. Tomorrow\n"
            f"3. This week\n"
            f"4. Next week\n\n"
            f"Reply with the number of your choice."
        )
    
    @staticmethod
    def available_slots(service_name: str, slots: List[Dict[str, Any]], owner_timezone: str) -> str:
        """Available time slots."""
        if not slots:
            return (
                f"😔 **No available slots for {service_name}**\n\n"
                f"Unfortunately, we don't have any open slots for your preferred time.\n\n"
                f"💡 **What would you like to do?**\n"
                f"• Try a different time preference\n"
                f"• Join our waitlist for priority booking\n"
                f"• Contact us directly for special arrangements\n\n"
                f"Reply with your choice!"
            )
        
        slots_text = []
        for i, slot in enumerate(slots[:5]):  # Show max 5 slots
            slot_time = format_datetime_for_user(slot['start_dt'], owner_timezone)
            slots_text.append(f"{i+1}. {slot_time} - ${slot['price_cents'] / 100:.0f}")
        
        return (
            f"📅 **Available slots for {service_name}:**\n\n" +
            "\n".join(slots_text) + "\n\n"
            f"Reply with the number of your preferred time."
        )
    
    @staticmethod
    def appointment_confirmed(appointment: Dict[str, Any], owner_name: str, owner_timezone: str) -> str:
        """Appointment confirmation message."""
        appointment_time = format_datetime_for_user(appointment['start_dt'], owner_timezone)
        
        return (
            f"✅ **Appointment Confirmed!**\n\n"
            f"📋 **Service:** {appointment['service_name']}\n"
            f"📅 **When:** {appointment_time}\n"
            f"⏱️ **Duration:** {appointment['duration_min']}m\n"
            f"💰 **Price:** ${appointment['price_cents'] / 100:.0f}\n\n"
            f"👤 **Business:** {owner_name}\n\n"
            f"🔔 **You'll receive reminders before your appointment.**\n\n"
            f"💡 **Need to make changes?**\n"
            f"• Send 'reschedule' to change time\n"
            f"• Send 'cancel' to cancel\n"
            f"• Send 'appointments' to view all bookings\n\n"
            f"See you soon! 😊"
        )
    
    @staticmethod
    def appointment_reminder_24h(appointment: Dict[str, Any], owner_name: str, owner_timezone: str) -> str:
        """24-hour appointment reminder."""
        appointment_time = format_datetime_for_user(appointment['start_dt'], owner_timezone)
        
        return (
            f"🔔 **Appointment Reminder**\n\n"
            f"Hi {appointment['client_name']}! This is a friendly reminder about your appointment tomorrow.\n\n"
            f"📋 **Service:** {appointment['service_name']}\n"
            f"📅 **When:** {appointment_time}\n"
            f"⏱️ **Duration:** {appointment['duration_min']} minutes\n"
            f"💰 **Price:** ${appointment['price_cents'] / 100:.0f}\n\n"
            f"👤 **Business:** {owner_name}\n\n"
            f"💡 **Need to make changes?**\n"
            f"• Send 'reschedule' to change time\n"
            f"• Send 'cancel' to cancel\n"
            f"• Send 'appointments' to view all bookings"
        )
    
    @staticmethod
    def appointment_reminder_2h(appointment: Dict[str, Any], owner_timezone: str) -> str:
        """2-hour appointment reminder."""
        appointment_time = format_datetime_for_user(appointment['start_dt'], owner_timezone)
        
        return (
            f"⏰ **Appointment Reminder**\n\n"
            f"Hi {appointment['client_name']}! Your appointment is in 2 hours.\n\n"
            f"📋 **Service:** {appointment['service_name']}\n"
            f"📅 **When:** {appointment_time}\n"
            f"⏱️ **Duration:** {appointment['duration_min']} minutes\n\n"
            f"See you soon! 🎉"
        )
    
    @staticmethod
    def appointment_reminder_30m(appointment: Dict[str, Any], owner_timezone: str) -> str:
        """30-minute appointment reminder."""
        appointment_time = format_datetime_for_user(appointment['start_dt'], owner_timezone)
        
        return (
            f"🚀 **Final Reminder**\n\n"
            f"Hi {appointment['client_name']}! Your appointment is in 30 minutes.\n\n"
            f"📋 **Service:** {appointment['service_name']}\n"
            f"📅 **When:** {appointment_time}\n\n"
            f"See you shortly! 😊"
        )
    
    @staticmethod
    def client_appointments(appointments: List[Dict[str, Any]], owner_timezone: str) -> str:
        """Client's appointments list."""
        if not appointments:
            return (
                f"📅 **Your Appointments**\n\n"
                f"You have no upcoming appointments.\n\n"
                f"💡 **Ready to book?**\n"
                f"Send 'book' to schedule a new appointment!"
            )
        
        appointment_list = []
        for apt in appointments:
            time_str = format_datetime_for_user(apt['start_dt'], owner_timezone)
            status_emoji = "⏳" if apt['status'] == 'PENDING' else "✅"
            
            appointment_list.append(
                f"{status_emoji} **{apt['service_name']}**\n"
                f"   📅 {time_str}\n"
                f"   ⏱️ {apt['duration_min']} minutes\n"
                f"   💰 ${apt['price_cents'] / 100:.0f}"
            )
        
        return (
            f"📅 **Your Appointments**\n\n" +
            "\n\n".join(appointment_list) + "\n\n"
            f"💡 Send 'reschedule' to change or 'cancel' to cancel an appointment."
        )
    
    @staticmethod
    def cancel_appointment_selection(appointments: List[Dict[str, Any]], owner_timezone: str) -> str:
        """Appointment selection for cancellation."""
        if len(appointments) == 1:
            apt = appointments[0]
            time_str = format_datetime_for_user(apt['start_dt'], owner_timezone)
            
            return (
                f"❌ **Cancel Appointment**\n\n"
                f"📋 Service: {apt['service_name']}\n"
                f"📅 {time_str}\n"
                f"💰 ${apt['price_cents'] / 100:.0f}\n\n"
                f"⚠️ Are you sure you want to cancel this appointment?\n\n"
                f"Reply 'yes' to confirm cancellation or 'no' to keep the appointment."
            )
        else:
            apt_list = []
            for i, apt in enumerate(appointments, 1):
                time_str = format_datetime_for_user(apt['start_dt'], owner_timezone)
                price_str = f"${apt['price_cents'] / 100:.0f}"
                apt_list.append(f"{i}. {apt['service_name']} - {time_str} - {price_str}")
            
            return (
                f"❌ **Which appointment would you like to cancel?**\n\n" +
                "\n".join(apt_list) + "\n\n"
                f"Reply with the number of the appointment to cancel."
            )
    
    @staticmethod
    def appointment_cancelled(appointment: Dict[str, Any], owner_timezone: str) -> str:
        """Appointment cancellation confirmation."""
        time_str = format_datetime_for_user(appointment['start_dt'], owner_timezone)
        
        return (
            f"✅ **Appointment Cancelled**\n\n"
            f"📋 Service: {appointment['service_name']}\n"
            f"📅 {time_str}\n\n"
            f"Your appointment has been successfully cancelled.\n\n"
            f"💡 **Need to book again?**\n"
            f"Send 'book' to schedule a new appointment."
        )
    
    @staticmethod
    def waitlist_notification(service_name: str, slots: List[Dict[str, Any]], owner_timezone: str) -> str:
        """Waitlist opportunity notification."""
        slots_text = []
        for i, slot in enumerate(slots[:3]):  # Show first 3 slots
            slot_time = format_datetime_for_user(slot['start_dt'], owner_timezone)
            slots_text.append(f"{i+1}. {slot_time} - ${slot['price_cents'] / 100:.0f}")
        
        return (
            f"🎉 **Great News!**\n\n"
            f"A slot has opened up for your waitlisted service.\n\n"
            f"📋 **Service:** {service_name}\n"
            f"📅 **Available Times:**\n" + "\n".join(slots_text) + "\n\n"
            f"⚡ **Quick Action:**\n"
            f"Reply with the number of your preferred time to book immediately!\n\n"
            f"⏰ **Limited Time:** This offer expires in 30 minutes."
        )
    
    @staticmethod
    def daily_report(owner_name: str, yesterday_stats: Dict[str, Any], today_schedule: Dict[str, Any]) -> str:
        """Daily report for owner."""
        return (
            f"📊 **Daily Report - {yesterday_stats['date']}**\n\n"
            f"📈 **Yesterday's Performance:**\n"
            f"• Total Appointments: {yesterday_stats['total_appointments']}\n"
            f"• Confirmed: {yesterday_stats['confirmed_appointments']}\n"
            f"• Cancelled: {yesterday_stats['cancelled_appointments']}\n"
            f"• Revenue: ${yesterday_stats['total_revenue']:.0f}\n\n"
            f"📅 **Today's Schedule:**\n"
            f"• Appointments: {today_schedule['appointment_count']}\n"
            f"• First: {today_schedule.get('first_appointment', 'None')}\n"
            f"• Last: {today_schedule.get('last_appointment', 'None')}\n\n"
            f"💡 **AI Suggestions:**\n"
            f"Check your dashboard for optimization recommendations!\n\n"
            f"🌐 **Dashboard:** http://localhost:8000/owner/dashboard"
        )
    
    @staticmethod
    def error_message(error_type: str = "general") -> str:
        """Error messages for different scenarios."""
        error_messages = {
            "general": "❌ Sorry, I encountered an error. Please try again.",
            "no_appointments": "❌ No appointments found. Send 'book' to schedule your first appointment.",
            "service_unavailable": "❌ Sorry, this service is not available right now. Please try another option.",
            "slot_unavailable": "❌ This time slot is no longer available. Please choose another time.",
            "session_expired": "❌ Session expired. Please try again.",
            "invalid_choice": "❌ Please enter a valid number from the options provided.",
            "booking_failed": "❌ Sorry, I couldn't book your appointment. Please try again or contact us directly."
        }
        
        return error_messages.get(error_type, error_messages["general"])
    
    @staticmethod
    def help_message(owner_name: str) -> str:
        """Help message with available commands."""
        return (
            f"👋 **Hello! I can help you with your appointments at {owner_name}.**\n\n"
            f"📋 **Available commands:**\n"
            f"• **book** - Schedule new appointment\n"
            f"• **reschedule** - Change existing appointment\n"
            f"• **cancel** - Cancel appointment\n"
            f"• **appointments** - View your bookings\n"
            f"• **help** - Show this message\n\n"
            f"💡 **Quick start:** Type 'book' to schedule an appointment!\n\n"
            f"What would you like to do?"
        )
