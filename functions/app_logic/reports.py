"""
Daily Reports System
"""
import logging
from datetime import datetime, timedelta
from .twilio_client import send_whatsapp_message

logger = logging.getLogger(__name__)


def send_daily_reports(db) -> dict:
    """Send daily reports to business owners"""
    try:
        owners_ref = db.db.collection('owners').stream()
        reports_sent = 0
        
        for owner_doc in owners_ref:
            owner = owner_doc.to_dict()
            owner['id'] = owner_doc.id
            
            # Skip if owner doesn't have a phone number
            if not owner.get('phone'):
                continue
            
            # Generate report
            yesterday = datetime.utcnow().date() - timedelta(days=1)
            today = datetime.utcnow().date()
            
            yesterday_apts = db.get_owner_appointments(owner['id'], yesterday)
            today_apts = db.get_owner_appointments(owner['id'], today)
            
            # Calculate stats
            confirmed_yesterday = len([a for a in yesterday_apts if a['status'] == 'CONFIRMED'])
            cancelled_yesterday = len([a for a in yesterday_apts if a['status'] == 'CANCELLED'])
            
            # Create report message
            message = (
                f"📊 **Daily Report - {yesterday.strftime('%B %d, %Y')}**\\n\\n"
                f"📈 **Yesterday's Performance:**\\n"
                f"• Total Appointments: {len(yesterday_apts)}\\n"
                f"• Confirmed: {confirmed_yesterday}\\n"
                f"• Cancelled: {cancelled_yesterday}\\n\\n"
                f"📅 **Today's Schedule:**\\n"
                f"• Appointments: {len(today_apts)}\\n\\n"
                f"Have a great day! 🎉"
            )
            
            send_whatsapp_message(owner['phone'], message)
            reports_sent += 1
            logger.info(f"Sent daily report to owner {owner['id']}")
        
        return {'success': True, 'reports_sent': reports_sent}
        
    except Exception as e:
        logger.error(f"Error sending daily reports: {str(e)}", exc_info=True)
        return {'success': False, 'error': str(e)}
