"""
Main WhatsApp webhook router that dispatches messages to owner/client flows.
"""
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Owner
from app.services.messaging import extract_phone_number
from app.utils.session import get_session, clear_session
from app.routes.owner import handle_owner_message
from app.routes.client import handle_client_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Main WhatsApp webhook endpoint.
    Routes messages to appropriate handlers based on sender.
    """
    try:
        # Parse Twilio webhook data
        form_data = await request.form()
        
        from_number = form_data.get("From", "")  # e.g., "whatsapp:+1234567890"
        wa_id = form_data.get("WaId", "")
        body = form_data.get("Body", "").strip()
        message_sid = form_data.get("MessageSid", "")
        
        if not from_number or not body:
            logger.warning(f"Invalid webhook data: From={from_number}, Body={body}")
            return PlainTextResponse("", status_code=200)
        
        # Extract clean phone number
        phone = extract_phone_number(from_number)
        
        logger.info(f"WhatsApp message from {phone}: {body}")
        
        # Check if sender is a registered owner
        owner = db.query(Owner).filter(Owner.phone == phone).first()
        
        if owner:
            # Route to owner flow
            logger.info(f"Routing to owner flow for {owner.name} ({phone})")
            await handle_owner_message(
                phone=phone,
                message=body,
                owner=owner,
                db=db
            )
        else:
            # Route to client flow
            logger.info(f"Routing to client flow for {phone}")
            await handle_client_message(
                phone=phone,
                message=body,
                db=db
            )
        
        # Twilio expects empty 200 response
        return PlainTextResponse("", status_code=200)
        
    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}", exc_info=True)
        
        # Try to send error message to user if we have their phone
        try:
            if 'phone' in locals():
                from app.services.messaging import send_whatsapp
                await send_whatsapp(
                    from_number,
                    "Sorry, I encountered an error processing your message. Please try again in a few minutes."
                )
        except:
            pass  # Don't fail if we can't send error message
        
        # Always return 200 to Twilio to avoid retries
        return PlainTextResponse("", status_code=200)


@router.post("/whatsapp/status")
async def whatsapp_status_webhook(request: Request):
    """
    Handle WhatsApp message status updates from Twilio.
    """
    try:
        form_data = await request.form()
        
        message_sid = form_data.get("MessageSid", "")
        message_status = form_data.get("MessageStatus", "")
        to = form_data.get("To", "")
        
        logger.info(f"WhatsApp status update: {message_sid} -> {message_status} (to: {to})")
        
        # TODO: Store delivery status in database if needed for analytics
        
        return PlainTextResponse("", status_code=200)
        
    except Exception as e:
        logger.error(f"Error processing WhatsApp status webhook: {e}")
        return PlainTextResponse("", status_code=200)


# Utility functions for common webhook operations
def parse_webhook_data(form_data) -> dict:
    """Parse Twilio webhook form data into structured dict."""
    return {
        'from': form_data.get("From", ""),
        'wa_id': form_data.get("WaId", ""),
        'body': form_data.get("Body", "").strip(),
        'message_sid': form_data.get("MessageSid", ""),
        'to': form_data.get("To", ""),
        'account_sid': form_data.get("AccountSid", ""),
        'num_media': int(form_data.get("NumMedia", "0")),
    }


def is_command(message: str) -> bool:
    """Check if message is a command (starts with keyword)."""
    commands = [
        'setup', 'help', 'book', 'reschedule', 'cancel', 'waitlist',
        'summary', 'intent', 'block', 'service', 'reminders', 'settings'
    ]
    first_word = message.lower().split()[0] if message else ""
    return first_word in commands


def extract_command_and_args(message: str) -> tuple[str, str]:
    """
    Extract command and arguments from message.
    
    Returns:
        tuple: (command, arguments)
    """
    parts = message.strip().split(None, 1)
    command = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    return command, args
