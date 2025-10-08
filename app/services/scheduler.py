"""
Core scheduling engine for appointment booking.
Handles slot finding, booking, rescheduling with optimization modes.
"""
import logging
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import (
    Owner, Service, Client, Appointment, Availability, Block,
    AppointmentStatus, IntentMode
)
from app.schemas import TimeSlot, SlotSuggestion
from app.services.policies import PolicyEnforcer, PolicyViolation
from app.utils.time import (
    now_in_timezone, to_utc, from_utc, get_time_slots_for_day,
    format_datetime_for_user
)

logger = logging.getLogger(__name__)


class SchedulingError(Exception):
    """Exception raised when scheduling operations fail."""
    pass


class SlotFinder:
    """Finds available appointment slots based on owner availability and constraints."""
    
    def __init__(self, db: Session):
        self.db = db
        self.policy_enforcer = PolicyEnforcer(db)
    
    def find_available_slots(self, owner: Owner, service: Service, 
                           start_date: date, end_date: date,
                           max_slots: int = 10) -> List[TimeSlot]:
        """
        Find available appointment slots for a service within a date range.
        
        Args:
            owner: Business owner
            service: Service to book
            start_date: Start of search range
            end_date: End of search range
            max_slots: Maximum number of slots to return
            
        Returns:
            List[TimeSlot]: Available time slots
        """
        available_slots = []
        current_date = start_date
        
        while current_date <= end_date and len(available_slots) < max_slots:
            daily_slots = self._find_daily_slots(owner, service, current_date)
            available_slots.extend(daily_slots)
            
            # Stop if we have enough slots
            if len(available_slots) >= max_slots:
                available_slots = available_slots[:max_slots]
                break
                
            current_date += timedelta(days=1)
        
        # Apply optimization based on owner's intent
        optimized_slots = self._optimize_slots(owner, available_slots, max_slots)
        
        logger.info(f"Found {len(optimized_slots)} available slots for {service.name}")
        return optimized_slots
    
    def _find_daily_slots(self, owner: Owner, service: Service, target_date: date) -> List[TimeSlot]:
        """Find available slots for a specific date."""
        weekday = target_date.weekday()
        
        # Get availability for this weekday
        availability = self.db.query(Availability).filter(
            Availability.owner_id == owner.id,
            Availability.weekday == weekday,
            Availability.active == True
        ).first()
        
        if not availability:
            return []
        
        # Generate potential time slots for the day
        potential_slots = get_time_slots_for_day(
            availability.start_time,
            availability.end_time,
            service.duration_min,
            service.buffer_min
        )
        
        available_slots = []
        
        for slot_start_time, slot_end_time in potential_slots:
            # Convert to datetime in owner's timezone, then to UTC
            slot_start_local = datetime.combine(target_date, slot_start_time)
            slot_start_utc = to_utc(slot_start_local, owner.timezone)
            slot_end_utc = slot_start_utc + timedelta(minutes=service.duration_min)
            
            try:
                # Check if this slot is available
                self.policy_enforcer.validate_appointment_request(
                    owner, slot_start_utc, service.duration_min, service.buffer_min
                )
                
                # Create time slot
                time_slot = TimeSlot(
                    start_dt=slot_start_utc,
                    end_dt=slot_end_utc,
                    service_id=service.id,
                    price_cents=service.price_cents
                )
                available_slots.append(time_slot)
                
            except PolicyViolation:
                # Slot not available, skip it
                continue
        
        return available_slots
    
    def _optimize_slots(self, owner: Owner, slots: List[TimeSlot], max_slots: int) -> List[TimeSlot]:
        """
        Optimize slot selection based on owner's intent mode.
        
        Args:
            owner: Business owner
            slots: Available slots
            max_slots: Maximum slots to return
            
        Returns:
            List[TimeSlot]: Optimized slot selection
        """
        if not slots:
            return []
        
        if owner.default_intent == IntentMode.PROFIT:
            return self._optimize_for_profit(slots, max_slots)
        elif owner.default_intent == IntentMode.BALANCED:
            return self._optimize_for_balance(slots, max_slots)
        elif owner.default_intent == IntentMode.FREE_TIME:
            return self._optimize_for_free_time(owner, slots, max_slots)
        else:
            # Default to balanced
            return self._optimize_for_balance(slots, max_slots)
    
    def _optimize_for_profit(self, slots: List[TimeSlot], max_slots: int) -> List[TimeSlot]:
        """
        Optimize for maximum profit: prioritize high-revenue density and tight packing.
        """
        # Calculate revenue density and sort
        def get_revenue_density(slot):
            service = self.db.query(Service).get(slot.service_id)
            total_time = service.duration_min + service.buffer_min
            return service.price_cents / max(total_time, 1)
        
        # Sort by revenue density (highest first), then by earliest time
        sorted_slots = sorted(slots, key=lambda s: (-get_revenue_density(s), s.start_dt))
        
        # Select tightly packed slots (prefer consecutive or close times)
        selected_slots = []
        for slot in sorted_slots:
            if len(selected_slots) >= max_slots:
                break
            
            # For profit mode, prefer slots that pack tightly together
            if not selected_slots or self._slots_are_close(selected_slots[-1], slot):
                selected_slots.append(slot)
        
        return selected_slots[:max_slots]
    
    def _optimize_for_balance(self, slots: List[TimeSlot], max_slots: int) -> List[TimeSlot]:
        """
        Optimize for balanced schedule: even spacing with micro-breaks.
        """
        if len(slots) <= max_slots:
            return sorted(slots, key=lambda s: s.start_dt)
        
        # Select evenly distributed slots across the available time range
        sorted_slots = sorted(slots, key=lambda s: s.start_dt)
        
        if max_slots == 1:
            return [sorted_slots[0]]
        
        # Calculate step size for even distribution
        step = len(sorted_slots) // max_slots
        selected_slots = []
        
        for i in range(0, len(sorted_slots), max(step, 1)):
            if len(selected_slots) >= max_slots:
                break
            selected_slots.append(sorted_slots[i])
        
        return selected_slots[:max_slots]
    
    def _optimize_for_free_time(self, owner: Owner, slots: List[TimeSlot], max_slots: int) -> List[TimeSlot]:
        """
        Optimize for free time: respect blocks and minimize fragmentation.
        """
        # Group slots by day to minimize fragmentation
        slots_by_day = {}
        for slot in slots:
            slot_date = from_utc(slot.start_dt, owner.timezone).date()
            if slot_date not in slots_by_day:
                slots_by_day[slot_date] = []
            slots_by_day[slot_date].append(slot)
        
        # Prefer days with more available slots (less fragmentation)
        day_scores = []
        for day, day_slots in slots_by_day.items():
            # Score based on number of slots and how tightly they're packed
            score = len(day_slots)
            if len(day_slots) > 1:
                # Bonus for tightly packed slots
                time_span = (day_slots[-1].start_dt - day_slots[0].start_dt).total_seconds() / 3600
                if time_span < 4:  # Within 4 hours
                    score += 2
            day_scores.append((score, day, day_slots))
        
        # Sort by score (highest first)
        day_scores.sort(key=lambda x: -x[0])
        
        # Select slots from best days first
        selected_slots = []
        for _, _, day_slots in day_scores:
            if len(selected_slots) >= max_slots:
                break
            
            # Sort day slots by time
            day_slots.sort(key=lambda s: s.start_dt)
            
            # Add slots from this day
            remaining_slots = max_slots - len(selected_slots)
            selected_slots.extend(day_slots[:remaining_slots])
        
        return sorted(selected_slots, key=lambda s: s.start_dt)[:max_slots]
    
    def _slots_are_close(self, slot1: TimeSlot, slot2: TimeSlot, max_gap_hours: float = 2.0) -> bool:
        """Check if two slots are close in time (for tight packing)."""
        time_diff = abs((slot2.start_dt - slot1.start_dt).total_seconds() / 3600)
        return time_diff <= max_gap_hours


class AppointmentScheduler:
    """Handles appointment booking, rescheduling, and cancellation."""
    
    def __init__(self, db: Session):
        self.db = db
        self.slot_finder = SlotFinder(db)
        self.policy_enforcer = PolicyEnforcer(db)
    
    def suggest_slots_for_client(self, owner: Owner, service: Service,
                               preference: str = "this_week", max_slots: int = 3) -> SlotSuggestion:
        """
        Suggest appointment slots based on client preference.
        
        Args:
            owner: Business owner
            service: Requested service
            preference: Client preference ("today", "tomorrow", "this_week", "next_week")
            max_slots: Maximum slots to suggest
            
        Returns:
            SlotSuggestion: Suggested slots with message
        """
        # Determine date range based on preference
        today = date.today()
        
        if preference.lower() in ["today"]:
            start_date = today
            end_date = today
        elif preference.lower() in ["tomorrow"]:
            start_date = today + timedelta(days=1)
            end_date = start_date
        elif preference.lower() in ["this week", "this_week"]:
            start_date = today
            end_date = today + timedelta(days=7)
        elif preference.lower() in ["next week", "next_week"]:
            start_date = today + timedelta(days=7)
            end_date = start_date + timedelta(days=7)
        else:
            # Default to this week
            start_date = today
            end_date = today + timedelta(days=7)
        
        # Find available slots
        slots = self.slot_finder.find_available_slots(
            owner, service, start_date, end_date, max_slots
        )
        
        # Generate message
        if not slots:
            message = f"Sorry, no available slots found for {preference}. Would you like to:\n1. Try a different time period\n2. Join the waitlist"
        else:
            slot_descriptions = []
            for i, slot in enumerate(slots, 1):
                time_str = format_datetime_for_user(slot.start_dt, owner.timezone)
                price_str = f"${slot.price_cents / 100:.0f}"
                slot_descriptions.append(f"{i}. {time_str} - {price_str}")
            
            message = f"📅 **Available slots for {service.name}:**\n\n" + "\n".join(slot_descriptions)
            message += f"\n\nReply with the number of your preferred time."
        
        return SlotSuggestion(slots=slots, message=message)
    
    def book_appointment(self, owner: Owner, client: Client, service: Service,
                        start_dt: datetime, notes: Optional[str] = None) -> Appointment:
        """
        Book an appointment with full validation and conflict checking.
        
        Args:
            owner: Business owner
            client: Client booking the appointment
            service: Service being booked
            start_dt: Appointment start time (UTC)
            notes: Optional appointment notes
            
        Returns:
            Appointment: Created appointment
            
        Raises:
            SchedulingError: If booking fails
        """
        try:
            # Validate appointment request
            self.policy_enforcer.validate_appointment_request(
                owner, start_dt, service.duration_min, service.buffer_min
            )
            
            # Calculate end time
            end_dt = start_dt + timedelta(minutes=service.duration_min)
            
            # Create appointment
            appointment = Appointment(
                owner_id=owner.id,
                client_id=client.id,
                service_id=service.id,
                start_dt=start_dt,
                end_dt=end_dt,
                status=AppointmentStatus.PENDING,
                channel="whatsapp",
                notes=notes
            )
            
            self.db.add(appointment)
            self.db.flush()  # Get the ID
            
            # Final conflict check with SELECT FOR UPDATE
            conflicts = self.db.query(Appointment).filter(
                Appointment.owner_id == owner.id,
                Appointment.id != appointment.id,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                Appointment.start_dt < end_dt + timedelta(minutes=service.buffer_min),
                Appointment.end_dt > start_dt - timedelta(minutes=service.buffer_min)
            ).with_for_update().all()
            
            if conflicts:
                raise SchedulingError("Appointment slot was taken by another booking")
            
            # Commit the changes
            self.db.commit()
            
            # Schedule reminder jobs
            try:
                from app.services.background_jobs import schedule_appointment_reminders
                schedule_appointment_reminders(appointment.id)
                logger.info(f"Scheduled reminder jobs for appointment {appointment.id}")
            except Exception as e:
                logger.error(f"Failed to schedule reminders for appointment {appointment.id}: {e}")
            
            logger.info(f"Booked appointment {appointment.id} for {client.name} at {start_dt}")
            return appointment
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to book appointment: {e}")
            raise SchedulingError(f"Failed to book appointment: {str(e)}")
    
    def reschedule_appointment(self, appointment: Appointment, new_start_dt: datetime) -> Appointment:
        """
        Reschedule an existing appointment.
        
        Args:
            appointment: Existing appointment
            new_start_dt: New start time (UTC)
            
        Returns:
            Appointment: Updated appointment
            
        Raises:
            SchedulingError: If rescheduling fails
        """
        try:
            # Get related objects
            owner = appointment.owner
            service = appointment.service
            
            # Validate new time (excluding current appointment from conflict check)
            self.policy_enforcer.validate_appointment_request(
                owner, new_start_dt, service.duration_min, service.buffer_min,
                exclude_appointment_id=appointment.id
            )
            
            # Update appointment
            old_start = appointment.start_dt
            appointment.start_dt = new_start_dt
            appointment.end_dt = new_start_dt + timedelta(minutes=service.duration_min)
            
            # Final conflict check
            conflicts = self.db.query(Appointment).filter(
                Appointment.owner_id == owner.id,
                Appointment.id != appointment.id,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                Appointment.start_dt < appointment.end_dt + timedelta(minutes=service.buffer_min),
                Appointment.end_dt > appointment.start_dt - timedelta(minutes=service.buffer_min)
            ).with_for_update().all()
            
            if conflicts:
                raise SchedulingError("New appointment slot conflicts with existing booking")
            
            self.db.commit()
            
            logger.info(f"Rescheduled appointment {appointment.id} from {old_start} to {new_start_dt}")
            return appointment
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to reschedule appointment: {e}")
            raise SchedulingError(f"Failed to reschedule appointment: {str(e)}")
    
    def cancel_appointment(self, appointment: Appointment, reason: str = "Client cancellation") -> bool:
        """
        Cancel an appointment.
        
        Args:
            appointment: Appointment to cancel
            reason: Cancellation reason
            
        Returns:
            bool: True if cancelled successfully
            
        Raises:
            SchedulingError: If cancellation fails
        """
        try:
            # Check cancellation policy
            owner = appointment.owner
            self.policy_enforcer.check_cancel_window(owner, appointment)
            
            # Store appointment info for gap-fill before cancelling
            appointment_id = appointment.id
            
            # Update appointment status
            appointment.status = AppointmentStatus.CANCELLED
            appointment.notes = f"{appointment.notes or ''}\nCancelled: {reason}".strip()
            
            self.db.commit()
            
            logger.info(f"Cancelled appointment {appointment_id}: {reason}")
            
            # Trigger gap-fill optimization (async, don't wait for result)
            try:
                import asyncio
                from app.services.optimizer import handle_appointment_cancellation
                
                # Create a task to handle gap-fill without blocking
                asyncio.create_task(handle_appointment_cancellation(self.db, appointment_id))
                logger.info(f"Gap-fill process initiated for cancelled appointment {appointment_id}")
                
            except Exception as gap_fill_error:
                # Don't fail the cancellation if gap-fill fails
                logger.error(f"Gap-fill process failed: {gap_fill_error}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to cancel appointment: {e}")
            raise SchedulingError(f"Failed to cancel appointment: {str(e)}")
    
    def get_daily_schedule(self, owner: Owner, target_date: date) -> List[Appointment]:
        """
        Get owner's schedule for a specific date.
        
        Args:
            owner: Business owner
            target_date: Date to get schedule for
            
        Returns:
            List[Appointment]: Appointments for the day
        """
        # Convert date to UTC range
        start_local = datetime.combine(target_date, time.min)
        end_local = datetime.combine(target_date, time.max)
        start_utc = to_utc(start_local, owner.timezone)
        end_utc = to_utc(end_local, owner.timezone)
        
        appointments = self.db.query(Appointment).filter(
            Appointment.owner_id == owner.id,
            Appointment.start_dt >= start_utc,
            Appointment.start_dt <= end_utc,
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
        ).order_by(Appointment.start_dt).all()
        
        return appointments


# Convenience functions
def find_available_slots(db: Session, owner: Owner, service: Service,
                        start_date: date, end_date: date, max_slots: int = 10) -> List[TimeSlot]:
    """Find available appointment slots."""
    finder = SlotFinder(db)
    return finder.find_available_slots(owner, service, start_date, end_date, max_slots)


def suggest_slots(db: Session, owner: Owner, service: Service,
                 preference: str = "this_week") -> SlotSuggestion:
    """Suggest appointment slots for client."""
    scheduler = AppointmentScheduler(db)
    return scheduler.suggest_slots_for_client(owner, service, preference)


def book_appointment(db: Session, owner: Owner, client: Client, service: Service,
                    start_dt: datetime, notes: Optional[str] = None) -> Appointment:
    """Book an appointment."""
    scheduler = AppointmentScheduler(db)
    return scheduler.book_appointment(owner, client, service, start_dt, notes)
