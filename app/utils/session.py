"""
Redis-based session state management for WhatsApp conversations.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass, asdict

from app.db import get_redis
from app.utils.time import now_in_timezone

logger = logging.getLogger(__name__)

# Session expiry times
DEFAULT_SESSION_EXPIRY = 3600  # 1 hour
BOOKING_SESSION_EXPIRY = 1800  # 30 minutes
SETUP_SESSION_EXPIRY = 7200   # 2 hours


@dataclass
class SessionState:
    """User session state."""
    phone: str
    state_type: str  # "owner_setup", "client_booking", "client_reschedule", etc.
    step: str        # Current step in the flow
    data: Dict[str, Any]  # Collected data
    created_at: datetime
    expires_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'phone': self.phone,
            'state_type': self.state_type,
            'step': self.step,
            'data': self.data,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        """Create from dictionary."""
        return cls(
            phone=data['phone'],
            state_type=data['state_type'],
            step=data['step'],
            data=data['data'],
            created_at=datetime.fromisoformat(data['created_at']),
            expires_at=datetime.fromisoformat(data['expires_at'])
        )


class SessionManager:
    """Manages user session state in Redis."""
    
    def __init__(self):
        self.redis = get_redis()
        self.key_prefix = "whatsapp_session:"
    
    def _get_key(self, phone: str) -> str:
        """Get Redis key for phone number."""
        # Clean phone number (remove whatsapp: prefix if present)
        clean_phone = phone.replace("whatsapp:", "")
        return f"{self.key_prefix}{clean_phone}"
    
    def get_session(self, phone: str) -> Optional[SessionState]:
        """
        Get session state for phone number.
        
        Args:
            phone: Phone number (with or without whatsapp: prefix)
            
        Returns:
            SessionState or None if not found/expired
        """
        try:
            key = self._get_key(phone)
            data = self.redis.get(key)
            
            if not data:
                return None
            
            session_data = json.loads(data)
            session = SessionState.from_dict(session_data)
            
            # Check if expired
            if datetime.now() > session.expires_at:
                self.clear_session(phone)
                return None
            
            return session
            
        except Exception as e:
            logger.error(f"Error getting session for {phone}: {e}")
            return None
    
    def set_session(
        self, 
        phone: str, 
        state_type: str, 
        step: str = "start",
        data: Optional[Dict[str, Any]] = None,
        expiry_seconds: Optional[int] = None
    ) -> SessionState:
        """
        Set session state for phone number.
        
        Args:
            phone: Phone number
            state_type: Type of conversation flow
            step: Current step in the flow
            data: Session data
            expiry_seconds: Custom expiry time
            
        Returns:
            SessionState: Created session
        """
        try:
            if data is None:
                data = {}
            
            if expiry_seconds is None:
                expiry_seconds = self._get_default_expiry(state_type)
            
            now = datetime.now()
            session = SessionState(
                phone=phone,
                state_type=state_type,
                step=step,
                data=data,
                created_at=now,
                expires_at=now + timedelta(seconds=expiry_seconds)
            )
            
            key = self._get_key(phone)
            self.redis.setex(
                key, 
                expiry_seconds, 
                json.dumps(session.to_dict(), default=str)
            )
            
            logger.info(f"Set session for {phone}: {state_type}/{step}")
            return session
            
        except Exception as e:
            logger.error(f"Error setting session for {phone}: {e}")
            raise
    
    def update_session(
        self, 
        phone: str, 
        step: Optional[str] = None,
        data_update: Optional[Dict[str, Any]] = None,
        extend_expiry: bool = True
    ) -> Optional[SessionState]:
        """
        Update existing session.
        
        Args:
            phone: Phone number
            step: New step (if changing)
            data_update: Data to merge into session
            extend_expiry: Whether to extend expiry time
            
        Returns:
            Updated SessionState or None if session doesn't exist
        """
        try:
            session = self.get_session(phone)
            if not session:
                return None
            
            # Update step if provided
            if step is not None:
                session.step = step
            
            # Merge data updates
            if data_update:
                session.data.update(data_update)
            
            # Extend expiry if requested
            if extend_expiry:
                expiry_seconds = self._get_default_expiry(session.state_type)
                session.expires_at = datetime.now() + timedelta(seconds=expiry_seconds)
            
            # Save updated session
            key = self._get_key(phone)
            ttl = int((session.expires_at - datetime.now()).total_seconds())
            if ttl > 0:
                self.redis.setex(
                    key, 
                    ttl, 
                    json.dumps(session.to_dict(), default=str)
                )
                logger.info(f"Updated session for {phone}: {session.step}")
                return session
            else:
                # Session expired, clear it
                self.clear_session(phone)
                return None
                
        except Exception as e:
            logger.error(f"Error updating session for {phone}: {e}")
            return None
    
    def clear_session(self, phone: str) -> bool:
        """
        Clear session for phone number.
        
        Args:
            phone: Phone number
            
        Returns:
            bool: True if session was cleared
        """
        try:
            key = self._get_key(phone)
            result = self.redis.delete(key)
            logger.info(f"Cleared session for {phone}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error clearing session for {phone}: {e}")
            return False
    
    def _get_default_expiry(self, state_type: str) -> int:
        """Get default expiry time for state type."""
        expiry_map = {
            'owner_setup': SETUP_SESSION_EXPIRY,
            'client_booking': BOOKING_SESSION_EXPIRY,
            'client_reschedule': BOOKING_SESSION_EXPIRY,
            'client_cancel': BOOKING_SESSION_EXPIRY,
            'client_waitlist': BOOKING_SESSION_EXPIRY,
        }
        return expiry_map.get(state_type, DEFAULT_SESSION_EXPIRY)
    
    def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        try:
            pattern = f"{self.key_prefix}*"
            keys = self.redis.keys(pattern)
            return len(keys)
        except Exception as e:
            logger.error(f"Error getting active sessions count: {e}")
            return 0


# Global session manager instance
session_manager = SessionManager()


# Convenience functions
def get_session(phone: str) -> Optional[SessionState]:
    """Get session for phone number."""
    return session_manager.get_session(phone)


def set_session(
    phone: str, 
    state_type: str, 
    step: str = "start",
    data: Optional[Dict[str, Any]] = None
) -> SessionState:
    """Set session for phone number."""
    return session_manager.set_session(phone, state_type, step, data)


def update_session(
    phone: str, 
    step: Optional[str] = None,
    data_update: Optional[Dict[str, Any]] = None
) -> Optional[SessionState]:
    """Update session for phone number."""
    return session_manager.update_session(phone, step, data_update)


def clear_session(phone: str) -> bool:
    """Clear session for phone number."""
    return session_manager.clear_session(phone)


def is_in_conversation(phone: str) -> bool:
    """Check if user is in an active conversation."""
    return get_session(phone) is not None
