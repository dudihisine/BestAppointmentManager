"""
Appointment Scheduler
Handles finding available slots and booking logic
"""
from datetime import datetime, timedelta, time
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class AppointmentScheduler:
    """Appointment scheduling engine"""
    
    def __init__(self, db):
        self.db = db
    
    def find_available_slots(self, owner: Dict[str, Any], service: Dict[str, Any], preference: str) -> List[Dict[str, Any]]:
        """Find available appointment slots"""
        try:
            # Get date range based on preference
            today = datetime.utcnow().date()
            
            if preference == 'today':
                search_dates = [today]
            elif preference == 'tomorrow':
                search_dates = [today + timedelta(days=1)]
            elif preference == 'this_week':
                search_dates = [today + timedelta(days=i) for i in range(7)]
            elif preference == 'next_week':
                search_dates = [today + timedelta(days=i) for i in range(7, 14)]
            else:
                search_dates = [today + timedelta(days=i) for i in range(7)]
            
            all_slots = []
            
            for date in search_dates:
                slots = self._find_slots_for_date(owner, service, date)
                all_slots.extend(slots)
                
                if len(all_slots) >= 5:  # Return first 5 slots
                    break
            
            return all_slots[:5]
            
        except Exception as e:
            logger.error(f"Error finding slots: {str(e)}", exc_info=True)
            return []
    
    def _find_slots_for_date(self, owner: Dict[str, Any], service: Dict[str, Any], date: datetime.date) -> List[Dict[str, Any]]:
        """Find available slots for a specific date"""
        try:
            # Get business hours
            settings = self.db.get_settings(owner['id'])
            
            if not settings:
                # Default hours
                start_time = time(9, 0)
                end_time = time(18, 0)
            else:
                start_time = datetime.strptime(settings.get('business_hours_start', '09:00'), '%H:%M').time()
                end_time = datetime.strptime(settings.get('business_hours_end', '18:00'), '%H:%M').time()
            
            # Get existing appointments for this date
            appointments = self.db.get_owner_appointments(owner['id'], date)
            
            # Generate time slots
            slots = []
            current_time = datetime.combine(date, start_time)
            end_datetime = datetime.combine(date, end_time)
            
            slot_duration = timedelta(minutes=service['duration_min'])
            buffer_duration = timedelta(minutes=service.get('buffer_min', 0))
            
            while current_time + slot_duration <= end_datetime:
                slot_end = current_time + slot_duration
                
                # Check if slot conflicts with existing appointments
                is_available = True
                for apt in appointments:
                    apt_start = apt['start_dt']
                    apt_end = apt['end_dt']
                    
                    # Check for overlap
                    if current_time < apt_end and slot_end > apt_start:
                        is_available = False
                        break
                
                if is_available:
                    slots.append({
                        'start_dt': current_time,
                        'end_dt': slot_end,
                        'service_id': service['id'],
                        'price_cents': service['price_cents']
                    })
                
                # Move to next slot (with buffer)
                current_time = slot_end + buffer_duration
            
            return slots
            
        except Exception as e:
            logger.error(f"Error finding slots for date: {str(e)}", exc_info=True)
            return []
