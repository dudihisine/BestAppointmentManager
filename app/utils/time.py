"""
Time and timezone utilities for appointment scheduling.
"""
import re
from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple, List
import pytz
from zoneinfo import ZoneInfo

from app.config import get_settings

settings = get_settings()


def get_owner_timezone(timezone_str: str = None) -> ZoneInfo:
    """
    Get timezone object for owner.
    
    Args:
        timezone_str: Timezone string (e.g., "Asia/Jerusalem")
        
    Returns:
        ZoneInfo: Timezone object
    """
    tz_str = timezone_str or settings.timezone_default
    return ZoneInfo(tz_str)


def now_in_timezone(timezone_str: str = None) -> datetime:
    """
    Get current datetime in owner's timezone.
    
    Args:
        timezone_str: Timezone string
        
    Returns:
        datetime: Current time in specified timezone
    """
    tz = get_owner_timezone(timezone_str)
    return datetime.now(tz)


def to_utc(dt: datetime, timezone_str: str = None) -> datetime:
    """
    Convert datetime to UTC.
    
    Args:
        dt: Datetime object (naive or timezone-aware)
        timezone_str: Source timezone if dt is naive
        
    Returns:
        datetime: UTC datetime
    """
    if dt.tzinfo is None:
        # Naive datetime - assume it's in owner's timezone
        tz = get_owner_timezone(timezone_str)
        dt = dt.replace(tzinfo=tz)
    
    return dt.astimezone(ZoneInfo("UTC"))


def from_utc(dt: datetime, timezone_str: str = None) -> datetime:
    """
    Convert UTC datetime to owner's timezone.
    
    Args:
        dt: UTC datetime
        timezone_str: Target timezone
        
    Returns:
        datetime: Datetime in owner's timezone
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    
    tz = get_owner_timezone(timezone_str)
    return dt.astimezone(tz)


def parse_human_time(text: str, reference_date: date = None) -> Optional[datetime]:
    """
    Parse human-readable time expressions.
    
    Args:
        text: Human time expression (e.g., "today 2pm", "tomorrow 14:30", "monday 9am")
        reference_date: Reference date for relative expressions
        
    Returns:
        datetime: Parsed datetime or None if invalid
    """
    if reference_date is None:
        reference_date = date.today()
    
    text = text.lower().strip()
    
    # Time patterns
    time_patterns = [
        (r'(\d{1,2}):(\d{2})', lambda h, m: time(int(h), int(m))),
        (r'(\d{1,2})pm', lambda h: time(int(h) + 12 if int(h) != 12 else 12, 0)),
        (r'(\d{1,2})am', lambda h: time(int(h) if int(h) != 12 else 0, 0)),
        (r'(\d{1,2})', lambda h: time(int(h), 0) if int(h) <= 23 else None),
    ]
    
    # Date patterns
    date_patterns = [
        ('today', reference_date),
        ('tomorrow', reference_date + timedelta(days=1)),
        ('monday', get_next_weekday(reference_date, 0)),
        ('tuesday', get_next_weekday(reference_date, 1)),
        ('wednesday', get_next_weekday(reference_date, 2)),
        ('thursday', get_next_weekday(reference_date, 3)),
        ('friday', get_next_weekday(reference_date, 4)),
        ('saturday', get_next_weekday(reference_date, 5)),
        ('sunday', get_next_weekday(reference_date, 6)),
    ]
    
    # Find date
    target_date = reference_date
    for pattern, result_date in date_patterns:
        if pattern in text:
            target_date = result_date
            text = text.replace(pattern, '').strip()
            break
    
    # Find time
    target_time = None
    for pattern, parser in time_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                if len(match.groups()) == 2:
                    target_time = parser(match.group(1), match.group(2))
                else:
                    target_time = parser(match.group(1))
                if target_time:
                    break
            except (ValueError, TypeError):
                continue
    
    if target_time is None:
        return None
    
    return datetime.combine(target_date, target_time)


def get_next_weekday(reference_date: date, weekday: int) -> date:
    """
    Get next occurrence of a weekday.
    
    Args:
        reference_date: Starting date
        weekday: Target weekday (0=Monday, 6=Sunday)
        
    Returns:
        date: Next occurrence of the weekday
    """
    days_ahead = weekday - reference_date.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return reference_date + timedelta(days_ahead)


def format_datetime_for_user(dt: datetime, timezone_str: str = None, include_date: bool = True) -> str:
    """
    Format datetime for user display.
    
    Args:
        dt: Datetime to format
        timezone_str: User's timezone
        include_date: Whether to include date
        
    Returns:
        str: Formatted datetime string
    """
    local_dt = from_utc(dt, timezone_str)
    
    if include_date:
        if local_dt.date() == date.today():
            return f"Today at {local_dt.strftime('%H:%M')}"
        elif local_dt.date() == date.today() + timedelta(days=1):
            return f"Tomorrow at {local_dt.strftime('%H:%M')}"
        else:
            return local_dt.strftime('%A, %B %d at %H:%M')
    else:
        return local_dt.strftime('%H:%M')


def get_time_slots_for_day(
    start_time: time, 
    end_time: time, 
    duration_minutes: int, 
    buffer_minutes: int = 0
) -> List[Tuple[time, time]]:
    """
    Generate available time slots for a day.
    
    Args:
        start_time: Day start time
        end_time: Day end time
        duration_minutes: Appointment duration
        buffer_minutes: Buffer time between appointments
        
    Returns:
        List[Tuple[time, time]]: List of (start, end) time tuples
    """
    slots = []
    current = datetime.combine(date.today(), start_time)
    end_dt = datetime.combine(date.today(), end_time)
    
    slot_duration = timedelta(minutes=duration_minutes)
    buffer_duration = timedelta(minutes=buffer_minutes)
    
    while current + slot_duration <= end_dt:
        slot_start = current.time()
        slot_end = (current + slot_duration).time()
        slots.append((slot_start, slot_end))
        current += slot_duration + buffer_duration
    
    return slots


def is_within_quiet_hours(
    check_time: datetime, 
    quiet_start: Optional[time], 
    quiet_end: Optional[time],
    timezone_str: str = None
) -> bool:
    """
    Check if a datetime is within quiet hours.
    
    Args:
        check_time: Time to check
        quiet_start: Quiet hours start time
        quiet_end: Quiet hours end time
        timezone_str: Timezone for conversion
        
    Returns:
        bool: True if within quiet hours
    """
    if not quiet_start or not quiet_end:
        return False
    
    local_time = from_utc(check_time, timezone_str).time()
    
    if quiet_start <= quiet_end:
        # Same day quiet hours (e.g., 22:00 - 08:00 next day)
        return quiet_start <= local_time <= quiet_end
    else:
        # Overnight quiet hours (e.g., 22:00 - 08:00)
        return local_time >= quiet_start or local_time <= quiet_end


def add_business_days(start_date: date, days: int) -> date:
    """
    Add business days to a date (skip weekends).
    
    Args:
        start_date: Starting date
        days: Number of business days to add
        
    Returns:
        date: Resulting date
    """
    current = start_date
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday = 0, Friday = 4
            days -= 1
    return current


def get_duration_string(minutes: int) -> str:
    """
    Convert minutes to human-readable duration.
    
    Args:
        minutes: Duration in minutes
        
    Returns:
        str: Human-readable duration (e.g., "1h 30m", "45m")
    """
    if minutes < 60:
        return f"{minutes}m"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h {remaining_minutes}m"


def format_time_gap(minutes: float) -> str:
    """
    Format a time gap in minutes to a user-friendly string.
    
    Args:
        minutes: Gap duration in minutes (can be float)
        
    Returns:
        str: User-friendly time gap (e.g., "3h 20m", "45m", "2h")
    """
    total_minutes = int(minutes)
    
    if total_minutes < 60:
        return f"{total_minutes}m"
    
    hours = total_minutes // 60
    remaining_minutes = total_minutes % 60
    
    if remaining_minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h {remaining_minutes}m"
