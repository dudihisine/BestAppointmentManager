"""
Waitlist management system for appointment scheduling.
Handles waitlist signup, priority management, and notifications.
"""
import logging
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import Owner, Service, Client, Waitlist, Appointment, AppointmentStatus
from app.services.messaging import send_whatsapp
from app.utils.time import (
    format_datetime_for_user, parse_human_time, 
    now_in_timezone, from_utc, to_utc
)

logger = logging.getLogger(__name__)


class WaitlistManager:
    """Manages waitlist operations and client notifications."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def add_to_waitlist(self, owner: Owner, client: Client, service: Service,
                       window_start: datetime, window_end: datetime,
                       priority: int = 0) -> Waitlist:
        """
        Add client to waitlist for a service.
        
        Args:
            owner: Business owner
            client: Client to add
            service: Requested service
            window_start: Earliest acceptable time (UTC)
            window_end: Latest acceptable time (UTC)
            priority: Priority level (higher = more priority)
            
        Returns:
            Waitlist: Created waitlist entry
        """
        # Check if client is already on waitlist for this service
        existing = self.db.query(Waitlist).filter(
            Waitlist.owner_id == owner.id,
            Waitlist.client_id == client.id,
            Waitlist.service_id == service.id,
            Waitlist.window_end_dt >= datetime.utcnow()  # Active waitlist entries
        ).first()
        
        if existing:
            # Update existing entry with new window
            existing.window_start_dt = window_start
            existing.window_end_dt = window_end
            existing.priority = max(existing.priority, priority)
            self.db.commit()
            
            logger.info(f"Updated waitlist entry for {client.name} - {service.name}")
            return existing
        
        # Create new waitlist entry
        waitlist_entry = Waitlist(
            owner_id=owner.id,
            client_id=client.id,
            service_id=service.id,
            window_start_dt=window_start,
            window_end_dt=window_end,
            priority=priority,
            notify_count=0
        )
        
        self.db.add(waitlist_entry)
        self.db.commit()
        
        logger.info(f"Added {client.name} to waitlist for {service.name}")
        return waitlist_entry
    
    def remove_from_waitlist(self, waitlist_id: int) -> bool:
        """Remove client from waitlist."""
        
        waitlist_entry = self.db.query(Waitlist).get(waitlist_id)
        if not waitlist_entry:
            return False
        
        client_name = waitlist_entry.client.name
        service_name = waitlist_entry.service.name
        
        self.db.delete(waitlist_entry)
        self.db.commit()
        
        logger.info(f"Removed {client_name} from waitlist for {service_name}")
        return True
    
    def get_client_waitlist_entries(self, client_phone: str, owner_id: Optional[int] = None) -> List[Waitlist]:
        """Get all active waitlist entries for a client."""
        
        query = self.db.query(Waitlist).join(Client).filter(
            Client.phone == client_phone,
            Waitlist.window_end_dt >= datetime.utcnow()
        )
        
        if owner_id:
            query = query.filter(Waitlist.owner_id == owner_id)
        
        return query.order_by(Waitlist.created_at.desc()).all()
    
    def get_waitlist_for_service(self, owner_id: int, service_id: int,
                                window_start: Optional[datetime] = None,
                                window_end: Optional[datetime] = None) -> List[Waitlist]:
        """Get waitlist entries for a specific service and time window."""
        
        query = self.db.query(Waitlist).filter(
            Waitlist.owner_id == owner_id,
            Waitlist.service_id == service_id,
            Waitlist.window_end_dt >= datetime.utcnow()
        )
        
        if window_start:
            query = query.filter(Waitlist.window_start_dt <= window_start)
        
        if window_end:
            query = query.filter(Waitlist.window_end_dt >= window_end)
        
        return query.order_by(
            Waitlist.priority.desc(),
            Waitlist.created_at.asc()
        ).all()
    
    async def process_waitlist_signup(self, client_phone: str, owner_id: int,
                                     service_id: int, preference: str) -> Dict[str, Any]:
        """
        Process waitlist signup from client message.
        
        Args:
            client_phone: Client's phone number
            owner_id: Business owner ID
            service_id: Requested service ID
            preference: Time preference (e.g., "today", "tomorrow", "this week")
            
        Returns:
            Dict with signup result
        """
        try:
            # Get entities
            owner = self.db.query(Owner).get(owner_id)
            service = self.db.query(Service).get(service_id)
            
            if not owner or not service:
                return {"success": False, "error": "Owner or service not found"}
            
            # Get or create client
            client = self.db.query(Client).filter(
                Client.owner_id == owner_id,
                Client.phone == client_phone
            ).first()
            
            if not client:
                # Create new client
                client = Client(
                    owner_id=owner_id,
                    phone=client_phone,
                    name="Waitlist Client",  # Will be updated when they provide name
                    opt_in_move_earlier=True  # Default to opt-in for waitlist clients
                )
                self.db.add(client)
                self.db.flush()
            
            # Parse time preference into window
            window_start, window_end = self._parse_waitlist_window(preference, owner.timezone)
            
            # Add to waitlist
            waitlist_entry = self.add_to_waitlist(
                owner, client, service, window_start, window_end, priority=0
            )
            
            # Send confirmation message
            await self._send_waitlist_confirmation(client_phone, owner, service, window_start, window_end)
            
            return {
                "success": True,
                "waitlist_id": waitlist_entry.id,
                "message": "Added to waitlist successfully"
            }
            
        except Exception as e:
            logger.error(f"Error processing waitlist signup: {e}")
            return {"success": False, "error": str(e)}
    
    def _parse_waitlist_window(self, preference: str, timezone_str: str) -> Tuple[datetime, datetime]:
        """Parse client preference into time window."""
        
        now_local = now_in_timezone(timezone_str)
        today = now_local.date()
        
        if preference.lower() in ["today"]:
            # Rest of today
            window_start = datetime.utcnow()
            window_end = to_utc(datetime.combine(today, time(23, 59)), timezone_str)
            
        elif preference.lower() in ["tomorrow"]:
            # All of tomorrow
            tomorrow = today + timedelta(days=1)
            window_start = to_utc(datetime.combine(tomorrow, time(0, 0)), timezone_str)
            window_end = to_utc(datetime.combine(tomorrow, time(23, 59)), timezone_str)
            
        elif preference.lower() in ["this week", "this_week"]:
            # Rest of this week
            window_start = datetime.utcnow()
            days_until_sunday = 6 - today.weekday()  # Monday = 0, Sunday = 6
            week_end = today + timedelta(days=days_until_sunday)
            window_end = to_utc(datetime.combine(week_end, time(23, 59)), timezone_str)
            
        elif preference.lower() in ["next week", "next_week"]:
            # All of next week
            days_until_next_monday = 7 - today.weekday()
            next_monday = today + timedelta(days=days_until_next_monday)
            next_sunday = next_monday + timedelta(days=6)
            window_start = to_utc(datetime.combine(next_monday, time(0, 0)), timezone_str)
            window_end = to_utc(datetime.combine(next_sunday, time(23, 59)), timezone_str)
            
        else:
            # Default to next 7 days
            window_start = datetime.utcnow()
            window_end = window_start + timedelta(days=7)
        
        return window_start, window_end
    
    async def _send_waitlist_confirmation(self, client_phone: str, owner: Owner,
                                         service: Service, window_start: datetime,
                                         window_end: datetime):
        """Send waitlist confirmation message."""
        
        start_str = format_datetime_for_user(window_start, owner.timezone)
        end_str = format_datetime_for_user(window_end, owner.timezone)
        
        message = (
            f"📋 **Added to Waitlist**\n\n"
            f"📋 **Service:** {service.name}\n"
            f"⏱️ **Duration:** {service.duration_min} minutes\n"
            f"💰 **Price:** ${service.price_cents / 100:.0f}\n"
            f"📅 **Window:** {start_str} - {end_str}\n\n"
            f"👤 **Business:** {owner.name}\n\n"
            f"🔔 **We'll notify you immediately when a slot opens up!**\n\n"
            f"💡 **Tips:**\n"
            f"• Keep your phone handy for quick notifications\n"
            f"• You'll have 10 minutes to respond when we find a slot\n"
            f"• Send 'waitlist' to view your current waitlist entries\n"
            f"• Send 'remove waitlist' to remove yourself from all waitlists"
        )
        
        await send_whatsapp(client_phone, message)
    
    async def show_client_waitlist(self, client_phone: str, owner_id: Optional[int] = None) -> str:
        """Generate waitlist status message for client."""
        
        entries = self.get_client_waitlist_entries(client_phone, owner_id)
        
        if not entries:
            return (
                "📋 **Your Waitlist**\n\n"
                "You're not currently on any waitlists.\n\n"
                "💡 When booking is full, we'll offer to add you to the waitlist for automatic notifications when slots open up!"
            )
        
        message_parts = ["📋 **Your Waitlist**\n"]
        
        for i, entry in enumerate(entries, 1):
            service = entry.service
            owner = entry.owner
            
            start_str = format_datetime_for_user(entry.window_start_dt, owner.timezone)
            end_str = format_datetime_for_user(entry.window_end_dt, owner.timezone)
            
            message_parts.append(
                f"{i}. **{service.name}** at {owner.name}\n"
                f"   📅 Window: {start_str} - {end_str}\n"
                f"   💰 ${service.price_cents / 100:.0f} • {service.duration_min}min\n"
                f"   🔔 Notifications: {entry.notify_count}\n"
            )
        
        message_parts.extend([
            f"\n💡 **Tips:**",
            f"• We'll notify you when slots open up",
            f"• Reply quickly to secure your spot",
            f"• Send 'remove waitlist' to remove all entries"
        ])
        
        return "\n".join(message_parts)
    
    async def remove_client_from_all_waitlists(self, client_phone: str, owner_id: Optional[int] = None) -> Dict[str, Any]:
        """Remove client from all waitlists."""
        
        entries = self.get_client_waitlist_entries(client_phone, owner_id)
        
        if not entries:
            return {
                "success": True,
                "removed_count": 0,
                "message": "You weren't on any waitlists."
            }
        
        removed_count = 0
        for entry in entries:
            if self.remove_from_waitlist(entry.id):
                removed_count += 1
        
        message = (
            f"✅ **Removed from Waitlist**\n\n"
            f"You've been removed from {removed_count} waitlist{'s' if removed_count != 1 else ''}.\n\n"
            f"💡 You can always join the waitlist again when booking is full!"
        )
        
        return {
            "success": True,
            "removed_count": removed_count,
            "message": message
        }
    
    def get_waitlist_stats(self, owner_id: int) -> Dict[str, Any]:
        """Get waitlist statistics for owner."""
        
        # Total active waitlist entries
        total_entries = self.db.query(func.count(Waitlist.id)).filter(
            Waitlist.owner_id == owner_id,
            Waitlist.window_end_dt >= datetime.utcnow()
        ).scalar()
        
        # Entries by service
        service_stats = self.db.query(
            Service.name,
            func.count(Waitlist.id).label('count')
        ).join(Waitlist).filter(
            Waitlist.owner_id == owner_id,
            Waitlist.window_end_dt >= datetime.utcnow()
        ).group_by(Service.id, Service.name).all()
        
        # High priority entries
        high_priority = self.db.query(func.count(Waitlist.id)).filter(
            Waitlist.owner_id == owner_id,
            Waitlist.priority > 0,
            Waitlist.window_end_dt >= datetime.utcnow()
        ).scalar()
        
        return {
            "total_entries": total_entries,
            "high_priority": high_priority,
            "by_service": [{"service": name, "count": count} for name, count in service_stats]
        }


# Convenience functions
def add_client_to_waitlist(db: Session, owner_id: int, client_phone: str,
                          service_id: int, window_start: datetime, window_end: datetime) -> Optional[Waitlist]:
    """Add client to waitlist."""
    manager = WaitlistManager(db)
    
    owner = db.query(Owner).get(owner_id)
    service = db.query(Service).get(service_id)
    
    if not owner or not service:
        return None
    
    # Get or create client
    client = db.query(Client).filter(
        Client.owner_id == owner_id,
        Client.phone == client_phone
    ).first()
    
    if not client:
        client = Client(
            owner_id=owner_id,
            phone=client_phone,
            name="Waitlist Client"
        )
        db.add(client)
        db.flush()
    
    return manager.add_to_waitlist(owner, client, service, window_start, window_end)


async def process_waitlist_command(db: Session, client_phone: str, command: str, owner_id: int) -> str:
    """Process waitlist-related commands."""
    manager = WaitlistManager(db)
    
    command = command.lower().strip()
    
    if command in ["waitlist", "my waitlist", "show waitlist"]:
        return await manager.show_client_waitlist(client_phone, owner_id)
    
    elif command in ["remove waitlist", "leave waitlist", "cancel waitlist"]:
        result = await manager.remove_client_from_all_waitlists(client_phone, owner_id)
        return result["message"]
    
    else:
        return (
            "❓ **Waitlist Commands:**\n\n"
            "• `waitlist` - Show your current waitlist entries\n"
            "• `remove waitlist` - Remove yourself from all waitlists\n\n"
            "💡 You'll be automatically added to waitlists when booking is full!"
        )
