"""
Background job system for appointment reminders and notifications.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Owner, Client, Appointment, AppointmentStatus, Waitlist
from app.services.messaging import send_whatsapp
from app.utils.time import now_in_timezone, from_utc, to_utc

logger = logging.getLogger(__name__)


class BackgroundJobManager:
    """Manages background jobs for appointment reminders and notifications."""
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
    
    def schedule_appointment_reminders(self, appointment_id: int):
        """Schedule all reminder jobs for an appointment."""
        try:
            from rq import Queue
            from redis import Redis
            
            # Connect to Redis
            redis_conn = Redis(host='localhost', port=6379, db=0)
            queue = Queue('appointment_reminders', connection=redis_conn)
            
            # Get appointment details
            appointment = self.db.query(Appointment).get(appointment_id)
            if not appointment:
                logger.error(f"Appointment {appointment_id} not found for reminder scheduling")
                return
            
            # Calculate reminder times
            appointment_time = from_utc(appointment.start_dt, appointment.owner.timezone)
            now = now_in_timezone(appointment.owner.timezone)
            
            # Schedule 24-hour reminder
            reminder_24h = appointment_time - timedelta(hours=24)
            if reminder_24h > now:
                queue.enqueue_at(
                    reminder_24h,
                    send_appointment_reminder,
                    appointment_id,
                    '24h',
                    job_timeout='5m'
                )
                logger.info(f"Scheduled 24h reminder for appointment {appointment_id} at {reminder_24h}")
            
            # Schedule 2-hour reminder
            reminder_2h = appointment_time - timedelta(hours=2)
            if reminder_2h > now:
                queue.enqueue_at(
                    reminder_2h,
                    send_appointment_reminder,
                    appointment_id,
                    '2h',
                    job_timeout='5m'
                )
                logger.info(f"Scheduled 2h reminder for appointment {appointment_id} at {reminder_2h}")
            
            # Schedule 30-minute reminder
            reminder_30m = appointment_time - timedelta(minutes=30)
            if reminder_30m > now:
                queue.enqueue_at(
                    reminder_30m,
                    send_appointment_reminder,
                    appointment_id,
                    '30m',
                    job_timeout='5m'
                )
                logger.info(f"Scheduled 30m reminder for appointment {appointment_id} at {reminder_30m}")
            
        except Exception as e:
            logger.error(f"Error scheduling reminders for appointment {appointment_id}: {e}")
    
    def schedule_waitlist_notifications(self, owner_id: int):
        """Schedule waitlist notifications for an owner."""
        try:
            from rq import Queue
            from redis import Redis
            
            # Connect to Redis
            redis_conn = Redis(host='localhost', port=6379, db=0)
            queue = Queue('waitlist_notifications', connection=redis_conn)
            
            # Schedule daily waitlist check
            queue.enqueue_in(
                timedelta(minutes=1),  # Run in 1 minute
                check_waitlist_opportunities,
                owner_id,
                job_timeout='10m'
            )
            
            logger.info(f"Scheduled waitlist check for owner {owner_id}")
            
        except Exception as e:
            logger.error(f"Error scheduling waitlist notifications for owner {owner_id}: {e}")
    
    def schedule_daily_reports(self, owner_id: int):
        """Schedule daily reports for an owner."""
        try:
            from rq import Queue
            from redis import Redis
            
            # Connect to Redis
            redis_conn = Redis(host='localhost', port=6379, db=0)
            queue = Queue('daily_reports', connection=redis_conn)
            
            # Schedule daily report for tomorrow at 8 AM
            owner = self.db.query(Owner).get(owner_id)
            if not owner:
                logger.error(f"Owner {owner_id} not found for daily report scheduling")
                return
            
            # Calculate next 8 AM in owner's timezone
            now = now_in_timezone(owner.timezone)
            next_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if next_8am <= now:
                next_8am += timedelta(days=1)
            
            # Convert to UTC for scheduling
            next_8am_utc = to_utc(next_8am)
            
            queue.enqueue_at(
                next_8am_utc,
                send_daily_report,
                owner_id,
                job_timeout='5m'
            )
            
            logger.info(f"Scheduled daily report for owner {owner_id} at {next_8am}")
            
        except Exception as e:
            logger.error(f"Error scheduling daily report for owner {owner_id}: {e}")


async def send_appointment_reminder(appointment_id: int, reminder_type: str):
    """Send appointment reminder to client."""
    db = SessionLocal()
    try:
        appointment = db.query(Appointment).get(appointment_id)
        if not appointment:
            logger.error(f"Appointment {appointment_id} not found for reminder")
            return
        
        if appointment.status != AppointmentStatus.CONFIRMED:
            logger.info(f"Appointment {appointment_id} is not confirmed, skipping reminder")
            return
        
        client = appointment.client
        owner = appointment.owner
        
        # Format appointment time
        appointment_time = from_utc(appointment.start_dt, owner.timezone)
        time_str = appointment_time.strftime("%A, %B %d at %H:%M")
        
        # Create reminder message based on type
        if reminder_type == '24h':
            message = (
                f"🔔 **Appointment Reminder**\n\n"
                f"Hi {client.name}! This is a friendly reminder about your appointment tomorrow.\n\n"
                f"📋 **Service:** {appointment.service.name}\n"
                f"📅 **When:** {time_str}\n"
                f"⏱️ **Duration:** {appointment.service.duration_min} minutes\n"
                f"💰 **Price:** ${appointment.service.price_cents / 100:.0f}\n\n"
                f"👤 **Business:** {owner.name}\n\n"
                f"💡 **Need to make changes?**\n"
                f"• Send 'reschedule' to change time\n"
                f"• Send 'cancel' to cancel\n"
                f"• Send 'appointments' to view all bookings"
            )
        elif reminder_type == '2h':
            message = (
                f"⏰ **Appointment Reminder**\n\n"
                f"Hi {client.name}! Your appointment is in 2 hours.\n\n"
                f"📋 **Service:** {appointment.service.name}\n"
                f"📅 **When:** {time_str}\n"
                f"⏱️ **Duration:** {appointment.service.duration_min} minutes\n\n"
                f"See you soon! 🎉"
            )
        elif reminder_type == '30m':
            message = (
                f"🚀 **Final Reminder**\n\n"
                f"Hi {client.name}! Your appointment is in 30 minutes.\n\n"
                f"📋 **Service:** {appointment.service.name}\n"
                f"📅 **When:** {time_str}\n\n"
                f"See you shortly! 😊"
            )
        else:
            logger.error(f"Unknown reminder type: {reminder_type}")
            return
        
        # Send reminder
        success = await send_whatsapp(client.phone, message)
        if success:
            logger.info(f"Sent {reminder_type} reminder for appointment {appointment_id}")
        else:
            logger.error(f"Failed to send {reminder_type} reminder for appointment {appointment_id}")
            
    except Exception as e:
        logger.error(f"Error sending reminder for appointment {appointment_id}: {e}")
    finally:
        db.close()


async def check_waitlist_opportunities(owner_id: int):
    """Check for waitlist opportunities and notify clients."""
    db = SessionLocal()
    try:
        from app.services.optimizer import OptimizationEngine
        
        optimizer = OptimizationEngine(db)
        
        # Get today's date
        owner = db.query(Owner).get(owner_id)
        if not owner:
            logger.error(f"Owner {owner_id} not found for waitlist check")
            return
        
        today = now_in_timezone(owner.timezone).date()
        
        # Check for opportunities
        result = await optimizer.check_waitlist_opportunities(owner_id, today)
        
        if result.get('success') and result.get('notifications_sent', 0) > 0:
            logger.info(f"Sent {result['notifications_sent']} waitlist notifications for owner {owner_id}")
        else:
            logger.info(f"No waitlist opportunities found for owner {owner_id}")
            
    except Exception as e:
        logger.error(f"Error checking waitlist opportunities for owner {owner_id}: {e}")
    finally:
        db.close()


async def send_daily_report(owner_id: int):
    """Send daily report to owner."""
    db = SessionLocal()
    try:
        owner = db.query(Owner).get(owner_id)
        if not owner:
            logger.error(f"Owner {owner_id} not found for daily report")
            return
        
        # Get yesterday's appointments
        yesterday = now_in_timezone(owner.timezone).date() - timedelta(days=1)
        start_of_day = to_utc(datetime.combine(yesterday, datetime.min.time()))
        end_of_day = to_utc(datetime.combine(yesterday, datetime.max.time()))
        
        appointments = db.query(Appointment).filter(
            Appointment.owner_id == owner_id,
            Appointment.start_dt >= start_of_day,
            Appointment.start_dt <= end_of_day
        ).all()
        
        # Calculate stats
        total_appointments = len(appointments)
        confirmed_appointments = len([apt for apt in appointments if apt.status == AppointmentStatus.CONFIRMED])
        cancelled_appointments = len([apt for apt in appointments if apt.status == AppointmentStatus.CANCELLED])
        total_revenue = sum(apt.service.price_cents for apt in appointments if apt.status == AppointmentStatus.CONFIRMED)
        
        # Get today's appointments
        today = now_in_timezone(owner.timezone).date()
        today_start = to_utc(datetime.combine(today, datetime.min.time()))
        today_end = to_utc(datetime.combine(today, datetime.max.time()))
        
        today_appointments = db.query(Appointment).filter(
            Appointment.owner_id == owner_id,
            Appointment.start_dt >= today_start,
            Appointment.start_dt <= today_end,
            Appointment.status == AppointmentStatus.CONFIRMED
        ).all()
        
        # Create report message
        message = (
            f"📊 **Daily Report - {yesterday.strftime('%A, %B %d, %Y')}**\n\n"
            f"📈 **Yesterday's Performance:**\n"
            f"• Total Appointments: {total_appointments}\n"
            f"• Confirmed: {confirmed_appointments}\n"
            f"• Cancelled: {cancelled_appointments}\n"
            f"• Revenue: ${total_revenue / 100:.0f}\n\n"
            f"📅 **Today's Schedule:**\n"
            f"• Appointments: {len(today_appointments)}\n"
        )
        
        if today_appointments:
            message += f"• First: {from_utc(today_appointments[0].start_dt, owner.timezone).strftime('%H:%M')}\n"
            message += f"• Last: {from_utc(today_appointments[-1].start_dt, owner.timezone).strftime('%H:%M')}\n"
        
        message += f"\n💡 **AI Suggestions:**\n"
        message += f"Check your dashboard for optimization recommendations!\n\n"
        message += f"🌐 **Dashboard:** http://localhost:8000/owner/dashboard"
        
        # Send report (assuming owner has a phone number for notifications)
        if hasattr(owner, 'phone') and owner.phone:
            success = await send_whatsapp(owner.phone, message)
            if success:
                logger.info(f"Sent daily report to owner {owner_id}")
            else:
                logger.error(f"Failed to send daily report to owner {owner_id}")
        else:
            logger.info(f"Owner {owner_id} has no phone number for daily report")
            
    except Exception as e:
        logger.error(f"Error sending daily report to owner {owner_id}: {e}")
    finally:
        db.close()


# Convenience functions for external use
def schedule_appointment_reminders(appointment_id: int):
    """Schedule reminders for an appointment."""
    manager = BackgroundJobManager()
    manager.schedule_appointment_reminders(appointment_id)


def schedule_waitlist_notifications(owner_id: int):
    """Schedule waitlist notifications for an owner."""
    manager = BackgroundJobManager()
    manager.schedule_waitlist_notifications(owner_id)


def schedule_daily_reports(owner_id: int):
    """Schedule daily reports for an owner."""
    manager = BackgroundJobManager()
    manager.schedule_daily_reports(owner_id)
