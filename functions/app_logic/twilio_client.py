"""
Twilio Client for sending WhatsApp messages
"""
import os
import logging

logger = logging.getLogger(__name__)

# Lazy initialization - will be initialized on first use
_twilio_client = None
_initialized = False


def _get_twilio_client():
    """Lazy initialize Twilio client"""
    global _twilio_client, _initialized
    
    if _initialized:
        return _twilio_client
    
    _initialized = True
    
    try:
        from twilio.rest import Client
        
        # Get credentials from environment (Firebase config)
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        
        if account_sid and auth_token:
            _twilio_client = Client(account_sid, auth_token)
            logger.info("Twilio client initialized successfully")
        else:
            logger.warning("Twilio credentials not found in environment")
            
    except Exception as e:
        logger.error(f"Error initializing Twilio: {str(e)}")
    
    return _twilio_client


def send_whatsapp_message(to: str, message: str) -> bool:
    """
    Send a WhatsApp message using Twilio
    
    Args:
        to: Phone number (e.g., +1234567890)
        message: Message text
    
    Returns:
        bool: True if sent successfully
    """
    try:
        client = _get_twilio_client()
        
        if not client:
            logger.warning(f"Twilio not configured. Would send to {to}: {message}")
            return False
        
        whatsapp_from = os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
        
        # Ensure phone number has whatsapp: prefix
        if not to.startswith('whatsapp:'):
            to = f'whatsapp:{to}'
        
        # Send message
        message_obj = client.messages.create(
            from_=whatsapp_from,
            body=message,
            to=to
        )
        
        logger.info(f"WhatsApp message sent to {to}, SID: {message_obj.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to}: {str(e)}")
        return False
