"""
WhatsApp messaging service using Twilio API.
"""
import logging
from typing import Optional, List, Dict, Any
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MessagingError(Exception):
    """Custom exception for messaging errors."""
    pass


async def send_whatsapp(
    to: str, 
    text: str, 
    buttons: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """
    Send WhatsApp message using Twilio API.
    
    Args:
        to: Recipient phone number (e.g., "whatsapp:+1234567890")
        text: Message text content
        buttons: Optional list of button objects (for future use)
        
    Returns:
        bool: True if message sent successfully, False otherwise
        
    Raises:
        MessagingError: If Twilio credentials are missing or API call fails
    """
    # Check if test mode is enabled and capture message
    try:
        from app.services.test_messaging import is_test_mode_enabled, capture_message
        if is_test_mode_enabled():
            capture_message(to, text)
            logger.info(f"📱 CAPTURED WhatsApp to {to}: {text}")
            return True
    except ImportError:
        pass  # Test messaging not available
    
    # For testing: just log the message instead of sending via Twilio
    if not settings.twilio_account_sid or settings.twilio_account_sid.startswith("ACxxxxxxx"):
        logger.info(f"📱 WOULD SEND WhatsApp to {to}:")
        logger.info(f"📝 MESSAGE: {text}")
        if buttons:
            logger.info(f"🔘 BUTTONS: {buttons}")
        return True
    
    # Real Twilio sending (when credentials are configured)
    if not settings.twilio_auth_token:
        raise MessagingError("Twilio credentials not configured")
    
    # Ensure 'to' number has whatsapp: prefix
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    
    # Twilio Messages API endpoint
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    
    # Prepare message data
    data = {
        "From": settings.twilio_whatsapp_from,
        "To": to,
        "Body": text
    }
    
    # Add buttons if provided (for future enhancement)
    if buttons:
        # Note: Twilio WhatsApp buttons require specific formatting
        # This is a placeholder for future implementation
        logger.info(f"Buttons provided but not yet implemented: {buttons}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data=data,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0
            )
            
            if response.status_code == 201:
                result = response.json()
                message_sid = result.get("sid")
                logger.info(f"WhatsApp message sent successfully to {to}, SID: {message_sid}")
                return True
            else:
                logger.error(f"Failed to send WhatsApp message. Status: {response.status_code}, Response: {response.text}")
                return False
                
    except httpx.TimeoutException:
        logger.error(f"Timeout sending WhatsApp message to {to}")
        return False
    except httpx.RequestError as e:
        logger.error(f"Request error sending WhatsApp message to {to}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending WhatsApp message to {to}: {e}")
        return False


async def send_whatsapp_with_quick_replies(
    to: str,
    text: str,
    options: List[str]
) -> bool:
    """
    Send WhatsApp message with numbered quick reply options.
    
    Args:
        to: Recipient phone number
        text: Main message text
        options: List of option strings
        
    Returns:
        bool: True if sent successfully
    """
    # Format options as numbered list
    options_text = "\n".join([f"{i+1}. {option}" for i, option in enumerate(options)])
    full_text = f"{text}\n\n{options_text}\n\nReply with the number of your choice."
    
    return await send_whatsapp(to, full_text)


def format_phone_number(phone: str) -> str:
    """
    Format phone number for WhatsApp (ensure whatsapp: prefix).
    
    Args:
        phone: Phone number in various formats
        
    Returns:
        str: Formatted WhatsApp phone number
    """
    # Remove any existing whatsapp: prefix
    if phone.startswith("whatsapp:"):
        phone = phone[9:]
    
    # Ensure + prefix for international format
    if not phone.startswith("+"):
        phone = f"+{phone}"
    
    return f"whatsapp:{phone}"


def extract_phone_number(whatsapp_number: str) -> str:
    """
    Extract plain phone number from WhatsApp format.
    
    Args:
        whatsapp_number: Number in format "whatsapp:+1234567890" or "whatsapp:1234567890"
        
    Returns:
        str: Plain phone number "+1234567890" (always with + prefix)
    """
    if whatsapp_number.startswith("whatsapp:"):
        phone = whatsapp_number[9:]
    else:
        phone = whatsapp_number
    
    # Ensure + prefix for international format
    if not phone.startswith("+"):
        phone = f"+{phone}"
    
    return phone
