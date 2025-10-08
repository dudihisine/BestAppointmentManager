"""
Business policy enforcement for appointment scheduling.
Handles lead time, cancel window, quiet hours, and other business rules.
"""
import logging
from datetime import datetime, timedelta, time
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session

from app.models import Owner, OwnerSetting, Appointment, AppointmentStatus
from app.utils.time import now_in_timezone, is_within_quiet_hours, to_utc, from_utc

logger = logging.getLogger(__name__)


class PolicyViolation(Exception):
    """Exception raised when a business policy is violated."""
    pass


class PolicyEnforcer:
    """Enforces business policies for appointment scheduling."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_lead_time(self, owner: Owner, requested_start: datetime) -> bool:
        """
        Check if requested appointment time meets lead time requirements.
        
        Args:
            owner: Business owner
            requested_start: Requested appointment start time (UTC)
            
        Returns:
            bool: True if lead time is satisfied
            
        Raises:
            PolicyViolation: If lead time requirement is not met
        """
        settings = self.db.query(OwnerSetting).filter(
            OwnerSetting.owner_id == owner.id
        ).first()
        
        if not settings:
            # No settings configured, allow booking
            return True
        
        # Convert to owner's timezone for comparison
        now_local = now_in_timezone(owner.timezone)
        requested_local = from_utc(requested_start, owner.timezone)
        
        # Calculate time difference in minutes
        time_diff = (requested_local - now_local).total_seconds() / 60
        
        if time_diff < settings.lead_time_min:
            raise PolicyViolation(
                f"Appointment must be booked at least {settings.lead_time_min} minutes in advance. "
                f"Requested time is only {int(time_diff)} minutes away."
            )
        
        logger.info(f"Lead time check passed: {int(time_diff)} minutes >= {settings.lead_time_min} minutes")
        return True
    
    def check_cancel_window(self, owner: Owner, appointment: Appointment) -> bool:
        """
        Check if appointment can be cancelled within the cancel window.
        
        Args:
            owner: Business owner
            appointment: Appointment to cancel
            
        Returns:
            bool: True if cancellation is allowed
            
        Raises:
            PolicyViolation: If cancellation is outside allowed window
        """
        settings = self.db.query(OwnerSetting).filter(
            OwnerSetting.owner_id == owner.id
        ).first()
        
        if not settings:
            # No settings configured, allow cancellation
            return True
        
        # Convert to owner's timezone for comparison
        now_local = now_in_timezone(owner.timezone)
        appointment_local = from_utc(appointment.start_dt, owner.timezone)
        
        # Calculate time until appointment in hours
        time_until = (appointment_local - now_local).total_seconds() / 3600
        
        if time_until < settings.cancel_window_hr:
            raise PolicyViolation(
                f"Appointment can only be cancelled at least {settings.cancel_window_hr} hours in advance. "
                f"Appointment is in {time_until:.1f} hours."
            )
        
        logger.info(f"Cancel window check passed: {time_until:.1f} hours >= {settings.cancel_window_hr} hours")
        return True
    
    def check_quiet_hours(self, owner: Owner, notification_time: datetime) -> bool:
        """
        Check if notification can be sent during quiet hours.
        
        Args:
            owner: Business owner
            notification_time: When notification would be sent (UTC)
            
        Returns:
            bool: True if notification is allowed
            
        Raises:
            PolicyViolation: If notification is during quiet hours
        """
        if not owner.quiet_hours_start or not owner.quiet_hours_end:
            # No quiet hours configured
            return True
        
        if is_within_quiet_hours(
            notification_time,
            owner.quiet_hours_start,
            owner.quiet_hours_end,
            owner.timezone
        ):
            raise PolicyViolation(
                f"Cannot send notifications during quiet hours "
                f"({owner.quiet_hours_start.strftime('%H:%M')} - {owner.quiet_hours_end.strftime('%H:%M')})"
            )
        
        return True
    
    def check_business_hours(self, owner: Owner, requested_start: datetime, duration_minutes: int) -> bool:
        """
        Check if appointment falls within business hours.
        
        Args:
            owner: Business owner
            requested_start: Requested start time (UTC)
            duration_minutes: Appointment duration
            
        Returns:
            bool: True if within business hours
            
        Raises:
            PolicyViolation: If appointment is outside business hours
        """
        from app.models import Availability
        
        # Convert to owner's timezone
        start_local = from_utc(requested_start, owner.timezone)
        end_local = start_local + timedelta(minutes=duration_minutes)
        
        # Get weekday (0=Monday, 6=Sunday)
        weekday = start_local.weekday()
        
        # Check if owner has availability for this weekday
        availability = self.db.query(Availability).filter(
            Availability.owner_id == owner.id,
            Availability.weekday == weekday,
            Availability.active == True
        ).first()
        
        if not availability:
            raise PolicyViolation(
                f"No availability configured for {start_local.strftime('%A')}"
            )
        
        # Check if appointment fits within available hours
        start_time = start_local.time()
        end_time = end_local.time()
        
        if start_time < availability.start_time:
            raise PolicyViolation(
                f"Appointment starts at {start_time.strftime('%H:%M')} but business opens at {availability.start_time.strftime('%H:%M')}"
            )
        
        if end_time > availability.end_time:
            raise PolicyViolation(
                f"Appointment ends at {end_time.strftime('%H:%M')} but business closes at {availability.end_time.strftime('%H:%M')}"
            )
        
        logger.info(f"Business hours check passed: {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} within {availability.start_time.strftime('%H:%M')}-{availability.end_time.strftime('%H:%M')}")
        return True
    
    def check_appointment_conflicts(self, owner: Owner, requested_start: datetime, 
                                  duration_minutes: int, buffer_minutes: int = 0,
                                  exclude_appointment_id: Optional[int] = None) -> bool:
        """
        Check for appointment conflicts including buffer time.
        
        Args:
            owner: Business owner
            requested_start: Requested start time (UTC)
            duration_minutes: Appointment duration
            buffer_minutes: Buffer time before/after appointment
            exclude_appointment_id: Appointment ID to exclude from conflict check (for rescheduling)
            
        Returns:
            bool: True if no conflicts
            
        Raises:
            PolicyViolation: If there are conflicts
        """
        # Calculate appointment window including buffers
        buffer_delta = timedelta(minutes=buffer_minutes)
        window_start = requested_start - buffer_delta
        window_end = requested_start + timedelta(minutes=duration_minutes) + buffer_delta
        
        # Query for conflicting appointments
        query = self.db.query(Appointment).filter(
            Appointment.owner_id == owner.id,
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
            # Check for overlap: appointment starts before our window ends AND ends after our window starts
            Appointment.start_dt < window_end,
            Appointment.end_dt > window_start
        )
        
        if exclude_appointment_id:
            query = query.filter(Appointment.id != exclude_appointment_id)
        
        conflicts = query.all()
        
        if conflicts:
            conflict_times = []
            for conflict in conflicts:
                start_local = from_utc(conflict.start_dt, owner.timezone)
                end_local = from_utc(conflict.end_dt, owner.timezone)
                conflict_times.append(f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}")
            
            raise PolicyViolation(
                f"Time slot conflicts with existing appointments: {', '.join(conflict_times)}"
            )
        
        logger.info(f"No conflicts found for {requested_start} + {duration_minutes}min + {buffer_minutes}min buffer")
        return True
    
    def check_blocked_time(self, owner: Owner, requested_start: datetime, duration_minutes: int) -> bool:
        """
        Check if appointment conflicts with blocked time.
        
        Args:
            owner: Business owner
            requested_start: Requested start time (UTC)
            duration_minutes: Appointment duration
            
        Returns:
            bool: True if no blocked time conflicts
            
        Raises:
            PolicyViolation: If appointment conflicts with blocked time
        """
        from app.models import Block
        
        # Convert to owner's timezone to get the date
        start_local = from_utc(requested_start, owner.timezone)
        end_local = start_local + timedelta(minutes=duration_minutes)
        appointment_date = start_local.date()
        
        # Query for blocks on the same date
        blocks = self.db.query(Block).filter(
            Block.owner_id == owner.id,
            Block.date == appointment_date
        ).all()
        
        for block in blocks:
            # Check if appointment overlaps with block
            block_start = datetime.combine(appointment_date, block.start_time)
            block_end = datetime.combine(appointment_date, block.end_time)
            
            # Check for overlap
            if (start_local < block_end and end_local > block_start):
                raise PolicyViolation(
                    f"Time slot conflicts with blocked time: {block.start_time.strftime('%H:%M')}-{block.end_time.strftime('%H:%M')} "
                    f"({block.reason or 'No reason specified'})"
                )
        
        logger.info(f"No blocked time conflicts for {start_local.strftime('%Y-%m-%d %H:%M')}")
        return True
    
    def validate_appointment_request(self, owner: Owner, requested_start: datetime,
                                   duration_minutes: int, buffer_minutes: int = 0,
                                   exclude_appointment_id: Optional[int] = None) -> bool:
        """
        Comprehensive validation of appointment request against all policies.
        
        Args:
            owner: Business owner
            requested_start: Requested start time (UTC)
            duration_minutes: Appointment duration
            buffer_minutes: Buffer time
            exclude_appointment_id: Appointment to exclude from conflict check
            
        Returns:
            bool: True if all policies are satisfied
            
        Raises:
            PolicyViolation: If any policy is violated
        """
        try:
            # Check all policies
            self.check_lead_time(owner, requested_start)
            self.check_business_hours(owner, requested_start, duration_minutes)
            self.check_blocked_time(owner, requested_start, duration_minutes)
            self.check_appointment_conflicts(
                owner, requested_start, duration_minutes, buffer_minutes, exclude_appointment_id
            )
            
            logger.info(f"All policy checks passed for appointment at {requested_start}")
            return True
            
        except PolicyViolation as e:
            logger.warning(f"Policy violation: {e}")
            raise
    
    def get_max_outreach_per_gap(self, owner: Owner) -> int:
        """Get maximum number of outreach messages per gap."""
        settings = self.db.query(OwnerSetting).filter(
            OwnerSetting.owner_id == owner.id
        ).first()
        
        return settings.max_outreach_per_gap if settings else 5
    
    def get_reminder_hours(self, owner: Owner) -> List[int]:
        """Get reminder hours configuration."""
        settings = self.db.query(OwnerSetting).filter(
            OwnerSetting.owner_id == owner.id
        ).first()
        
        return settings.reminder_hours if settings else [24, 2]


def check_policies(db: Session, owner: Owner, requested_start: datetime,
                  duration_minutes: int, buffer_minutes: int = 0,
                  exclude_appointment_id: Optional[int] = None) -> bool:
    """
    Convenience function to check all policies for an appointment request.
    
    Args:
        db: Database session
        owner: Business owner
        requested_start: Requested start time (UTC)
        duration_minutes: Appointment duration
        buffer_minutes: Buffer time
        exclude_appointment_id: Appointment to exclude from conflict check
        
    Returns:
        bool: True if all policies are satisfied
        
    Raises:
        PolicyViolation: If any policy is violated
    """
    enforcer = PolicyEnforcer(db)
    return enforcer.validate_appointment_request(
        owner, requested_start, duration_minutes, buffer_minutes, exclude_appointment_id
    )
