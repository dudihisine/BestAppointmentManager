"""
Optimization and gap-fill logic for appointment scheduling.
Handles waitlist management, gap filling, and proactive client outreach.
"""
import logging
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import (
    Owner, OwnerSetting, Service, Client, Appointment, Waitlist,
    AppointmentStatus, AuditActor
)
from app.services.scheduler import AppointmentScheduler, SlotFinder
from app.services.policies import PolicyEnforcer
from app.services.messaging import send_whatsapp
from app.utils.time import (
    now_in_timezone, format_datetime_for_user, is_within_quiet_hours,
    from_utc, to_utc, format_time_gap
)

logger = logging.getLogger(__name__)


class OptimizationEngine:
    """Handles appointment optimization and gap-fill logic."""
    
    def __init__(self, db: Session):
        self.db = db
        self.scheduler = AppointmentScheduler(db)
        self.slot_finder = SlotFinder(db)
        self.policy_enforcer = PolicyEnforcer(db)
    
    async def on_appointment_cancelled(self, appointment_id: int) -> Dict[str, Any]:
        """
        Handle appointment cancellation and trigger gap-fill process.
        
        Args:
            appointment_id: ID of cancelled appointment
            
        Returns:
            Dict with gap-fill results
        """
        appointment = self.db.query(Appointment).get(appointment_id)
        if not appointment:
            logger.error(f"Appointment {appointment_id} not found")
            return {"success": False, "error": "Appointment not found"}
        
        logger.info(f"Processing cancellation for appointment {appointment_id}")
        
        # Create gap-fill task
        gap_start = appointment.start_dt
        gap_end = appointment.end_dt
        owner = appointment.owner
        service = appointment.service
        
        # Log the cancellation
        await self._log_audit(
            owner.id, AuditActor.SYSTEM, "gap_fill_triggered",
            {"appointment_id": appointment_id, "gap_start": gap_start.isoformat(), "gap_end": gap_end.isoformat()}
        )
        
        # Start gap-fill process
        result = await self.fill_gap(owner.id, gap_start, gap_end, service.id)
        
        return {
            "success": True,
            "appointment_id": appointment_id,
            "gap_fill_result": result
        }
    
    async def fill_gap(self, owner_id: int, gap_start: datetime, gap_end: datetime, 
                      service_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Fill a gap in the schedule using waitlist and proactive outreach.
        
        Args:
            owner_id: Business owner ID
            gap_start: Gap start time (UTC)
            gap_end: Gap end time (UTC)
            service_id: Optional service ID to match
            
        Returns:
            Dict with fill results
        """
        owner = self.db.query(Owner).get(owner_id)
        if not owner:
            return {"success": False, "error": "Owner not found"}
        
        logger.info(f"Filling gap: {gap_start} - {gap_end} for owner {owner.name}")
        
        # Check if we're in quiet hours
        if is_within_quiet_hours(datetime.utcnow(), owner.quiet_hours_start, owner.quiet_hours_end, owner.timezone):
            logger.info("In quiet hours, scheduling gap-fill for later")
            return {"success": False, "reason": "quiet_hours", "scheduled_for_later": True}
        
        # Get owner settings for outreach limits
        settings = self.db.query(OwnerSetting).filter(OwnerSetting.owner_id == owner_id).first()
        max_outreach = settings.max_outreach_per_gap if settings else 5
        
        result = {
            "success": False,
            "waitlist_notifications": 0,
            "move_earlier_offers": 0,
            "appointments_filled": 0,
            "backfill_attempts": 0
        }
        
        # Step 1: Try to fill from waitlist
        waitlist_result = await self._fill_from_waitlist(owner, gap_start, gap_end, service_id, max_outreach)
        result.update(waitlist_result)
        
        # Step 2: If gap still exists, offer earlier moves to same-day clients
        if not result.get("filled_from_waitlist"):
            move_result = await self._offer_earlier_moves(owner, gap_start, gap_end, service_id, max_outreach)
            result.update(move_result)
        
        # Step 3: If someone moved earlier, try to backfill their old slot
        if result.get("move_accepted"):
            backfill_result = await self._backfill_moved_slot(owner, result.get("moved_from_time"), service_id)
            result.update(backfill_result)
        
        result["success"] = result["appointments_filled"] > 0
        
        # Log the gap-fill attempt
        await self._log_audit(
            owner_id, AuditActor.SYSTEM, "gap_fill_completed", result
        )
        
        return result
    
    async def _fill_from_waitlist(self, owner: Owner, gap_start: datetime, gap_end: datetime,
                                 service_id: Optional[int], max_outreach: int) -> Dict[str, Any]:
        """Fill gap from waitlist clients."""
        
        # Find matching waitlist entries
        query = self.db.query(Waitlist).filter(
            Waitlist.owner_id == owner.id,
            Waitlist.window_start_dt <= gap_start,
            Waitlist.window_end_dt >= gap_end
        )
        
        if service_id:
            query = query.filter(Waitlist.service_id == service_id)
        
        # Order by priority and creation time
        waitlist_entries = query.order_by(
            Waitlist.priority.desc(),
            Waitlist.created_at.asc()
        ).limit(max_outreach).all()
        
        notifications_sent = 0
        
        for entry in waitlist_entries:
            # Check if we haven't exceeded notification limits
            if entry.notify_count >= 3:  # Max 3 notifications per waitlist entry
                continue
            
            # Check cooldown period (don't notify same client within 2 hours)
            if entry.last_notified_at:
                time_since_last = datetime.utcnow() - entry.last_notified_at
                if time_since_last < timedelta(hours=2):
                    continue
            
            # Send notification
            success = await self._notify_waitlist_client(owner, entry, gap_start, gap_end)
            if success:
                notifications_sent += 1
                
                # Update notification tracking
                entry.notify_count += 1
                entry.last_notified_at = datetime.utcnow()
                self.db.commit()
        
        return {
            "waitlist_notifications": notifications_sent,
            "filled_from_waitlist": False  # Will be updated when client responds
        }
    
    async def _offer_earlier_moves(self, owner: Owner, gap_start: datetime, gap_end: datetime,
                                  service_id: Optional[int], max_outreach: int) -> Dict[str, Any]:
        """Offer earlier appointment times to same-day clients."""
        
        # Find same-day appointments that could move earlier
        gap_date = from_utc(gap_start, owner.timezone).date()
        day_start = to_utc(datetime.combine(gap_date, time.min), owner.timezone)
        day_end = to_utc(datetime.combine(gap_date, time.max), owner.timezone)
        
        # Find appointments later in the day that opted in to move earlier
        query = self.db.query(Appointment).join(Client).filter(
            Appointment.owner_id == owner.id,
            Appointment.start_dt > gap_end,  # Later than the gap
            Appointment.start_dt >= day_start,
            Appointment.start_dt <= day_end,
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
            Client.opt_in_move_earlier == True
        )
        
        if service_id:
            query = query.filter(Appointment.service_id == service_id)
        
        # Order by appointment time (earliest first)
        candidates = query.order_by(Appointment.start_dt).limit(max_outreach).all()
        
        offers_sent = 0
        
        for appointment in candidates:
            # Check if the gap can accommodate this appointment
            service = appointment.service
            if (gap_end - gap_start).total_seconds() / 60 >= service.duration_min:
                
                # Send move offer
                success = await self._offer_earlier_move(owner, appointment, gap_start)
                if success:
                    offers_sent += 1
        
        return {
            "move_earlier_offers": offers_sent,
            "move_accepted": False  # Will be updated when client responds
        }
    
    async def _backfill_moved_slot(self, owner: Owner, moved_from_time: datetime,
                                  service_id: Optional[int]) -> Dict[str, Any]:
        """Try to backfill a slot that was vacated by a move."""
        
        # This would typically trigger another gap-fill process
        # For now, we'll just log it and return
        logger.info(f"Backfill opportunity at {moved_from_time}")
        
        return {
            "backfill_attempts": 1,
            "backfill_success": False
        }
    
    async def _notify_waitlist_client(self, owner: Owner, waitlist_entry: Waitlist,
                                     gap_start: datetime, gap_end: datetime) -> bool:
        """Send notification to waitlist client about available slot."""
        
        try:
            client = waitlist_entry.client
            service = waitlist_entry.service
            
            # Format time in owner's timezone
            time_str = format_datetime_for_user(gap_start, owner.timezone)
            duration_str = f"{service.duration_min} minutes"
            price_str = f"${service.price_cents / 100:.0f}"
            
            message = (
                f"🎉 **Great news!** A slot just opened up!\n\n"
                f"📋 **Service:** {service.name}\n"
                f"📅 **Time:** {time_str}\n"
                f"⏱️ **Duration:** {duration_str}\n"
                f"💰 **Price:** {price_str}\n\n"
                f"👤 **Business:** {owner.name}\n\n"
                f"⚡ **Quick! This slot won't last long.**\n"
                f"Reply 'YES' to book it now, or 'NO' to pass.\n\n"
                f"⏰ You have 10 minutes to respond."
            )
            
            success = await send_whatsapp(client.phone, message)
            
            if success:
                logger.info(f"Waitlist notification sent to {client.name} ({client.phone})")
                
                # Store the offer in Redis for quick response handling
                # This would be implemented with session management
                
            return success
            
        except Exception as e:
            logger.error(f"Error sending waitlist notification: {e}")
            return False
    
    async def _offer_earlier_move(self, owner: Owner, appointment: Appointment,
                                 new_start_time: datetime) -> bool:
        """Offer earlier appointment time to client."""
        
        try:
            client = appointment.client
            service = appointment.service
            
            # Format times
            current_time = format_datetime_for_user(appointment.start_dt, owner.timezone)
            new_time = format_datetime_for_user(new_start_time, owner.timezone)
            
            message = (
                f"⏰ **Earlier appointment available!**\n\n"
                f"📋 **Service:** {service.name}\n"
                f"📅 **Current time:** {current_time}\n"
                f"🔄 **New time:** {new_time}\n\n"
                f"Would you like to move your appointment earlier?\n\n"
                f"Reply 'YES' to move earlier, or 'NO' to keep current time.\n\n"
                f"⏰ You have 10 minutes to respond."
            )
            
            success = await send_whatsapp(client.phone, message)
            
            if success:
                logger.info(f"Earlier move offer sent to {client.name} ({client.phone})")
                
                # Store the offer in Redis for quick response handling
                
            return success
            
        except Exception as e:
            logger.error(f"Error sending earlier move offer: {e}")
            return False
    
    async def handle_waitlist_response(self, client_phone: str, response: str,
                                      waitlist_entry_id: int, gap_start: datetime) -> Dict[str, Any]:
        """Handle client response to waitlist notification."""
        
        response = response.lower().strip()
        
        if response in ['yes', 'y', 'book', 'take it']:
            return await self._book_from_waitlist(client_phone, waitlist_entry_id, gap_start)
        elif response in ['no', 'n', 'pass', 'skip']:
            return await self._decline_waitlist_offer(waitlist_entry_id)
        else:
            return {"success": False, "error": "Invalid response"}
    
    async def handle_move_earlier_response(self, client_phone: str, response: str,
                                         appointment_id: int, new_start_time: datetime) -> Dict[str, Any]:
        """Handle client response to earlier move offer."""
        
        response = response.lower().strip()
        
        if response in ['yes', 'y', 'move', 'earlier']:
            return await self._accept_earlier_move(appointment_id, new_start_time)
        elif response in ['no', 'n', 'keep', 'stay']:
            return await self._decline_earlier_move(appointment_id)
        else:
            return {"success": False, "error": "Invalid response"}
    
    async def _book_from_waitlist(self, client_phone: str, waitlist_entry_id: int,
                                 gap_start: datetime) -> Dict[str, Any]:
        """Book appointment from waitlist."""
        
        try:
            waitlist_entry = self.db.query(Waitlist).get(waitlist_entry_id)
            if not waitlist_entry:
                return {"success": False, "error": "Waitlist entry not found"}
            
            # Book the appointment
            appointment = self.scheduler.book_appointment(
                waitlist_entry.owner,
                waitlist_entry.client,
                waitlist_entry.service,
                gap_start,
                notes="Booked from waitlist via gap-fill"
            )
            
            # Remove from waitlist
            self.db.delete(waitlist_entry)
            self.db.commit()
            
            # Send confirmation
            time_str = format_datetime_for_user(appointment.start_dt, waitlist_entry.owner.timezone)
            confirmation_message = (
                f"✅ **Appointment Confirmed!**\n\n"
                f"📋 **Service:** {appointment.service.name}\n"
                f"📅 **Time:** {time_str}\n"
                f"👤 **Business:** {appointment.owner.name}\n\n"
                f"🎉 You got the slot! See you soon."
            )
            
            await send_whatsapp(client_phone, confirmation_message)
            
            logger.info(f"Waitlist booking confirmed for {waitlist_entry.client.name}")
            
            return {
                "success": True,
                "appointment_id": appointment.id,
                "filled_from_waitlist": True
            }
            
        except Exception as e:
            logger.error(f"Error booking from waitlist: {e}")
            return {"success": False, "error": str(e)}
    
    async def _accept_earlier_move(self, appointment_id: int, new_start_time: datetime) -> Dict[str, Any]:
        """Accept earlier move offer."""
        
        try:
            appointment = self.db.query(Appointment).get(appointment_id)
            if not appointment:
                return {"success": False, "error": "Appointment not found"}
            
            old_start_time = appointment.start_dt
            
            # Reschedule the appointment
            updated_appointment = self.scheduler.reschedule_appointment(appointment, new_start_time)
            
            # Send confirmation
            new_time_str = format_datetime_for_user(updated_appointment.start_dt, appointment.owner.timezone)
            confirmation_message = (
                f"✅ **Appointment Moved!**\n\n"
                f"📋 **Service:** {appointment.service.name}\n"
                f"📅 **New Time:** {new_time_str}\n\n"
                f"🎉 Your appointment has been moved earlier. See you soon!"
            )
            
            await send_whatsapp(appointment.client.phone, confirmation_message)
            
            logger.info(f"Earlier move confirmed for {appointment.client.name}")
            
            return {
                "success": True,
                "appointment_id": appointment.id,
                "move_accepted": True,
                "moved_from_time": old_start_time
            }
            
        except Exception as e:
            logger.error(f"Error accepting earlier move: {e}")
            return {"success": False, "error": str(e)}
    
    async def _decline_waitlist_offer(self, waitlist_entry_id: int) -> Dict[str, Any]:
        """Handle declined waitlist offer."""
        
        waitlist_entry = self.db.query(Waitlist).get(waitlist_entry_id)
        if waitlist_entry:
            # Just log the decline, keep them on waitlist
            logger.info(f"Waitlist offer declined by {waitlist_entry.client.name}")
        
        return {"success": True, "declined": True}
    
    async def _decline_earlier_move(self, appointment_id: int) -> Dict[str, Any]:
        """Handle declined earlier move offer."""
        
        appointment = self.db.query(Appointment).get(appointment_id)
        if appointment:
            logger.info(f"Earlier move declined by {appointment.client.name}")
        
        return {"success": True, "declined": True}
    
    async def suggest_schedule_optimization(self, owner_id: int, target_date: date) -> Dict[str, Any]:
        """Suggest schedule optimizations for a given date."""
        
        owner = self.db.query(Owner).get(owner_id)
        if not owner:
            return {"success": False, "error": "Owner not found"}
        
        # Get day's appointments
        appointments = self.scheduler.get_daily_schedule(owner, target_date)
        suggestions = []
        
        # Always provide mode-specific suggestions
        current_mode = owner.default_intent.value
        
        if not appointments:
            # Provide suggestions for empty days based on mode
            if current_mode == "max_profit":
                suggestions.append({
                    "type": "mode_suggestion",
                    "suggestion": "💰 Max Profit Mode: Focus on booking high-revenue services like Deluxe Package ($75) and Haircut + Beard ($40)"
                })
                suggestions.append({
                    "type": "marketing_tip",
                    "suggestion": "📈 Consider promoting premium services to fill this open day and maximize revenue"
                })
            elif current_mode == "balanced":
                suggestions.append({
                    "type": "mode_suggestion", 
                    "suggestion": "⚖️ Balanced Mode: Mix different service types throughout the day for steady workflow"
                })
                suggestions.append({
                    "type": "scheduling_tip",
                    "suggestion": "📅 Space appointments evenly to maintain good work-life balance"
                })
            elif current_mode == "free_time":
                suggestions.append({
                    "type": "mode_suggestion",
                    "suggestion": "🌿 Free Time Mode: Keep this day light or use for personal time and business development"
                })
                suggestions.append({
                    "type": "wellness_tip", 
                    "suggestion": "💆 Consider blocking time for breaks or use for administrative tasks"
                })
        else:
            # Analyze existing schedule
            total_revenue = sum(apt.service.price_cents for apt in appointments)
            total_duration = sum(apt.service.duration_min + apt.service.buffer_min for apt in appointments)
            
            # Mode-specific analysis
            if current_mode == "max_profit":
                suggestions.extend(self._get_profit_mode_suggestions(appointments, total_revenue))
            elif current_mode == "balanced":
                suggestions.extend(self._get_balanced_mode_suggestions(appointments, total_duration))
            elif current_mode == "free_time":
                suggestions.extend(self._get_free_time_suggestions(appointments))
            
            # Analyze gaps for all modes
            suggestions.extend(self._analyze_gaps(appointments, owner))
        
        # Add general tips based on day of week
        day_of_week = target_date.weekday()  # 0 = Monday
        suggestions.extend(self._get_day_specific_tips(day_of_week, current_mode))
        
        return {
            "success": True,
            "suggestions": suggestions,
            "total_suggestions": len(suggestions),
            "mode": current_mode
        }
    
    def _get_profit_mode_suggestions(self, appointments, total_revenue):
        """Get suggestions for max profit mode."""
        suggestions = []
        
        # Revenue analysis
        if total_revenue < 15000:  # Less than $150
            suggestions.append({
                "type": "revenue_boost",
                "suggestion": f"💰 Current revenue: ${total_revenue/100:.0f}. Try promoting Deluxe Package ($75) to boost daily earnings"
            })
        
        # Service mix analysis
        service_counts = {}
        for apt in appointments:
            service_name = apt.service.name
            service_counts[service_name] = service_counts.get(service_name, 0) + 1
        
        # Check for low-value services
        low_value_services = [apt for apt in appointments if apt.service.price_cents < 2000]
        if low_value_services:
            suggestions.append({
                "type": "upsell_opportunity",
                "suggestion": f"🎯 {len(low_value_services)} low-value appointments. Consider upselling to premium services"
            })
        
        return suggestions
    
    def _get_balanced_mode_suggestions(self, appointments, total_duration):
        """Get suggestions for balanced mode."""
        suggestions = []
        
        # Check for clustering
        if len(appointments) > 3:
            # Check time distribution
            time_gaps = []
            for i in range(len(appointments) - 1):
                gap = (appointments[i+1].start_dt - appointments[i].end_dt).total_seconds() / 60
                time_gaps.append(gap)
            
            avg_gap = sum(time_gaps) / len(time_gaps) if time_gaps else 0
            
            if avg_gap < 15:
                suggestions.append({
                    "type": "spacing_tip",
                    "suggestion": "⚖️ Schedule is tightly packed. Consider adding buffer time between appointments for better balance"
                })
            elif avg_gap > 60:
                suggestions.append({
                    "type": "efficiency_tip", 
                    "suggestion": "📊 Large gaps between appointments. Consider filling with shorter services or admin time"
                })
        
        # Workload analysis
        if total_duration > 480:  # More than 8 hours
            suggestions.append({
                "type": "workload_warning",
                "suggestion": "⚠️ Heavy schedule (8+ hours). Ensure adequate breaks to maintain service quality"
            })
        
        return suggestions
    
    def _get_free_time_suggestions(self, appointments):
        """Get suggestions for free time mode."""
        suggestions = []
        
        if len(appointments) > 5:
            suggestions.append({
                "type": "overbooked_warning",
                "suggestion": "🌿 Schedule is quite full for Free Time mode. Consider moving some appointments to protect personal time"
            })
        
        # Check for back-to-back appointments
        back_to_back = 0
        for i in range(len(appointments) - 1):
            gap = (appointments[i+1].start_dt - appointments[i].end_dt).total_seconds() / 60
            if gap < 10:
                back_to_back += 1
        
        if back_to_back > 0:
            suggestions.append({
                "type": "break_reminder",
                "suggestion": f"💆 {back_to_back} back-to-back appointments. Add buffer time for better work-life balance"
            })
        
        return suggestions
    
    def _analyze_gaps(self, appointments, owner):
        """Analyze gaps between appointments."""
        suggestions = []
        
        for i in range(len(appointments) - 1):
            current_apt = appointments[i]
            next_apt = appointments[i + 1]
            gap_minutes = (next_apt.start_dt - current_apt.end_dt).total_seconds() / 60
            
            if gap_minutes > 45:
                # Format gap time using utility function
                gap_text = format_time_gap(gap_minutes)
                
                # Format the gap times in owner's timezone
                gap_start_local = from_utc(current_apt.end_dt, owner.timezone)
                gap_end_local = from_utc(next_apt.start_dt, owner.timezone)
                
                gap_start_time = gap_start_local.strftime("%H:%M")
                gap_end_time = gap_end_local.strftime("%H:%M")
                
                suggestions.append({
                    "type": "fill_gap",
                    "gap_minutes": int(gap_minutes),
                    "gap_formatted": gap_text,
                    "gap_start_time": gap_start_time,
                    "gap_end_time": gap_end_time,
                    "suggestion": f"📅 {gap_text} gap from {gap_start_time} to {gap_end_time} - perfect for Quick Trim (15min) or Hair Wash (10min)"
                })
        
        return suggestions
    
    def _get_day_specific_tips(self, day_of_week, mode):
        """Get tips based on day of week."""
        suggestions = []
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = day_names[day_of_week]
        
        if day_of_week == 0:  # Monday
            suggestions.append({
                "type": "weekly_tip",
                "suggestion": f"📅 {day_name}: Start the week strong! Consider booking premium services to set a positive tone"
            })
        elif day_of_week == 4:  # Friday
            suggestions.append({
                "type": "weekly_tip", 
                "suggestion": f"🎉 {day_name}: End the week well! Popular day for grooming before weekend events"
            })
        elif day_of_week in [5, 6]:  # Weekend
            if mode == "free_time":
                suggestions.append({
                    "type": "weekend_tip",
                    "suggestion": f"🌿 {day_name}: Perfect for personal time or light schedule in Free Time mode"
                })
            else:
                suggestions.append({
                    "type": "weekend_tip",
                    "suggestion": f"💼 {day_name}: Weekend bookings often command premium rates"
                })
        
        return suggestions
    
    async def check_waitlist_opportunities(self, owner_id: int, target_date: date) -> Dict[str, Any]:
        """Check for waitlist opportunities and notify clients."""
        
        owner = self.db.query(Owner).get(owner_id)
        if not owner:
            return {"success": False, "error": "Owner not found"}
        
        # Get waitlist entries for this date
        start_of_day = to_utc(datetime.combine(target_date, datetime.min.time()))
        end_of_day = to_utc(datetime.combine(target_date, datetime.max.time()))
        
        waitlist_entries = self.db.query(Waitlist).filter(
            Waitlist.owner_id == owner_id,
            Waitlist.window_start_dt >= start_of_day,
            Waitlist.window_start_dt <= end_of_day
        ).all()
        
        if not waitlist_entries:
            return {"success": True, "notifications_sent": 0, "message": "No waitlist entries for this date"}
        
        # Get available slots for today
        from app.services.scheduler import AppointmentScheduler
        scheduler = AppointmentScheduler(self.db)
        
        notifications_sent = 0
        
        for waitlist_entry in waitlist_entries:
            try:
                # Check if there are available slots for this service
                slot_suggestion = scheduler.suggest_slots_for_client(
                    owner, 
                    waitlist_entry.service, 
                    'today'
                )
                
                if slot_suggestion.slots:
                    # Send notification to client
                    client = waitlist_entry.client
                    service = waitlist_entry.service
                    
                    # Format available slots
                    slots_text = []
                    for i, slot in enumerate(slot_suggestion.slots[:3]):  # Show first 3 slots
                        slot_time = from_utc(slot.start_dt, owner.timezone)
                        slots_text.append(f"{i+1}. {slot_time.strftime('%H:%M')} - ${slot.price_cents / 100:.0f}")
                    
                    message = (
                        f"🎉 **Great News!**\n\n"
                        f"Hi {client.name}! A slot has opened up for your waitlisted service.\n\n"
                        f"📋 **Service:** {service.name}\n"
                        f"📅 **Available Times:**\n" + "\n".join(slots_text) + "\n\n"
                        f"⚡ **Quick Action:**\n"
                        f"Reply with the number of your preferred time to book immediately!\n\n"
                        f"⏰ **Limited Time:** This offer expires in 30 minutes."
                    )
                    
                    # Send notification
                    success = await send_whatsapp(client.phone, message)
                    if success:
                        notifications_sent += 1
                        logger.info(f"Sent waitlist notification to {client.phone} for {service.name}")
                    
            except Exception as e:
                logger.error(f"Error processing waitlist entry {waitlist_entry.id}: {e}")
        
        return {
            "success": True,
            "notifications_sent": notifications_sent,
            "waitlist_entries_checked": len(waitlist_entries)
        }

    async def _log_audit(self, owner_id: int, actor: AuditActor, action: str, data: Dict[str, Any]):
        """Log audit trail for optimization actions."""
        
        from app.models import AuditLog
        
        audit_log = AuditLog(
            owner_id=owner_id,
            actor=actor,
            action=action,
            after=data
        )
        
        self.db.add(audit_log)
        self.db.commit()


# Convenience functions for external use
async def handle_appointment_cancellation(db: Session, appointment_id: int) -> Dict[str, Any]:
    """Handle appointment cancellation and trigger optimization."""
    optimizer = OptimizationEngine(db)
    return await optimizer.on_appointment_cancelled(appointment_id)


async def fill_schedule_gap(db: Session, owner_id: int, gap_start: datetime, 
                           gap_end: datetime, service_id: Optional[int] = None) -> Dict[str, Any]:
    """Fill a gap in the schedule."""
    optimizer = OptimizationEngine(db)
    return await optimizer.fill_gap(owner_id, gap_start, gap_end, service_id)


async def get_optimization_suggestions(db: Session, owner_id: int, target_date: date) -> Dict[str, Any]:
    """Get optimization suggestions for a date."""
    optimizer = OptimizationEngine(db)
    return await optimizer.suggest_schedule_optimization(owner_id, target_date)
