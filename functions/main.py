"""
Firebase Cloud Function for WhatsApp Appointment Manager
This is the main entry point for all WhatsApp messages via Twilio webhook
"""
from firebase_functions import https_fn, options
from firebase_admin import initialize_app
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin
initialize_app()

# Import our application logic
from app_logic.whatsapp_handler import handle_whatsapp_message
from app_logic.firestore_db import FirestoreDB

# Set global options
options.set_global_options(max_instances=10)

# Lazy initialize DB
_db = None

def get_db():
    """Lazy initialize Firestore DB"""
    global _db
    if _db is None:
        _db = FirestoreDB()
    return _db


@https_fn.on_request()
def whatsapp_webhook(req: https_fn.Request) -> https_fn.Response:
    """
    Twilio WhatsApp Webhook Endpoint
    
    This function receives POST requests from Twilio when a WhatsApp message is received.
    URL will be: https://YOUR_REGION-YOUR_PROJECT.cloudfunctions.net/whatsapp_webhook
    
    Expected Twilio POST parameters:
    - From: whatsapp:+1234567890
    - To: whatsapp:+14155238886
    - Body: Message text
    - MessageSid: Unique message ID
    """
    try:
        # Log incoming request
        logger.info(f"Received webhook request: {req.method}")
        
        # Handle CORS for testing
        if req.method == 'OPTIONS':
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '3600'
            }
            return https_fn.Response('', status=204, headers=headers)
        
        # Only accept POST requests
        if req.method != 'POST':
            return https_fn.Response('Method not allowed', status=405)
        
        # Get form data from Twilio
        form_data = req.form
        
        # Extract WhatsApp message details
        from_number = form_data.get('From', '')  # e.g., whatsapp:+1234567890
        to_number = form_data.get('To', '')
        message_body = form_data.get('Body', '')
        message_sid = form_data.get('MessageSid', '')
        
        # Clean phone number (remove whatsapp: prefix)
        phone = from_number.replace('whatsapp:', '').strip()
        
        logger.info(f"WhatsApp message from {phone}: {message_body}")
        
        # Validate required fields
        if not phone or not message_body:
            logger.error("Missing required fields in webhook request")
            return https_fn.Response('Bad request', status=400)
        
        # Process the message
        response_message = handle_whatsapp_message(phone, message_body, get_db())
        
        # Return TwiML response
        twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_message}</Message>
</Response>"""
        
        logger.info(f"Sending response to {phone}: {response_message[:50]}...")
        
        # Return proper TwiML response with headers
        headers = {
            'Content-Type': 'text/xml',
            'Access-Control-Allow-Origin': '*'
        }
        
        return https_fn.Response(twiml_response, status=200, headers=headers)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        
        # Return error TwiML
        error_twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>Sorry, I encountered an error. Please try again.</Message>
</Response>"""
        
        return https_fn.Response(error_twiml, status=200, headers={'Content-Type': 'text/xml'})


@https_fn.on_request()
def health_check(req: https_fn.Request) -> https_fn.Response:
    """Health check endpoint"""
    return https_fn.Response('OK - WhatsApp Appointment Manager is running!', status=200)


@https_fn.on_request()
def send_reminders(req: https_fn.Request) -> https_fn.Response:
    """
    Cloud Scheduler endpoint for sending appointment reminders
    Configure Cloud Scheduler to call this every hour
    """
    try:
        logger.info("Running scheduled reminders...")
        
        from app_logic.reminders import send_due_reminders
        
        results = send_due_reminders(get_db())
        
        logger.info(f"Reminders sent: {results}")
        
        return https_fn.Response(f"Reminders sent: {results}", status=200)
        
    except Exception as e:
        logger.error(f"Error sending reminders: {str(e)}", exc_info=True)
        return https_fn.Response(f"Error: {str(e)}", status=500)


@https_fn.on_request()
def check_waitlist(req: https_fn.Request) -> https_fn.Response:
    """
    Cloud Scheduler endpoint for checking waitlist opportunities
    Configure Cloud Scheduler to call this every 30 minutes
    """
    try:
        logger.info("Checking waitlist opportunities...")
        
        from app_logic.waitlist import check_waitlist_opportunities
        
        results = check_waitlist_opportunities(get_db())
        
        logger.info(f"Waitlist notifications sent: {results}")
        
        return https_fn.Response(f"Waitlist checked: {results}", status=200)
        
    except Exception as e:
        logger.error(f"Error checking waitlist: {str(e)}", exc_info=True)
        return https_fn.Response(f"Error: {str(e)}", status=500)


@https_fn.on_request()
def daily_report(req: https_fn.Request) -> https_fn.Response:
    """
    Cloud Scheduler endpoint for sending daily reports
    Configure Cloud Scheduler to call this once per day at 8 AM
    """
    try:
        logger.info("Generating daily reports...")
        
        from app_logic.reports import send_daily_reports
        
        results = send_daily_reports(get_db())
        
        logger.info(f"Daily reports sent: {results}")
        
        return https_fn.Response(f"Reports sent: {results}", status=200)
        
    except Exception as e:
        logger.error(f"Error sending daily reports: {str(e)}", exc_info=True)
        return https_fn.Response(f"Error: {str(e)}", status=500)
