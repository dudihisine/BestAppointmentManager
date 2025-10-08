"""
WhatsApp-like messaging interface for local testing.
Simulates WhatsApp conversations between owner and clients.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Owner, Client, Service, Appointment, Waitlist
from app.routes.client import handle_client_message
from app.routes.owner import handle_owner_message
from app.utils.time import now_in_timezone, format_datetime_for_user
from app.services.test_messaging import (
    enable_test_mode, disable_test_mode, get_captured_messages, 
    clear_captured_messages, capture_message
)

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")

# In-memory message storage for testing (in production, this would be in database)
test_messages = {}  # phone_number -> list of messages

class TestMessage:
    def __init__(self, phone: str, content: str, is_from_client: bool, timestamp: datetime = None):
        self.phone = phone
        self.content = content
        self.is_from_client = is_from_client
        self.timestamp = timestamp or datetime.now()
        self.id = f"{phone}_{self.timestamp.timestamp()}"

def get_or_create_conversation(phone: str) -> List[TestMessage]:
    """Get or create a conversation for a phone number."""
    if phone not in test_messages:
        test_messages[phone] = []
    return test_messages[phone]

def add_message(phone: str, content: str, is_from_client: bool) -> TestMessage:
    """Add a message to the conversation."""
    conversation = get_or_create_conversation(phone)
    message = TestMessage(phone, content, is_from_client)
    conversation.append(message)
    return message

@router.get("/messages", response_class=HTMLResponse)
async def messages_home(request: Request, db: Session = Depends(get_db)):
    """WhatsApp-like messaging interface home page."""
    
    owner = db.query(Owner).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Get all conversations (unique phone numbers)
    conversations = []
    for phone, messages in test_messages.items():
        if messages:
            last_message = messages[-1]
            # Get client info if exists
            client = db.query(Client).filter(
                Client.owner_id == owner.id,
                Client.phone == phone
            ).first()
            
            conversations.append({
                "phone": phone,
                "client_name": client.name if client else f"Unknown ({phone})",
                "last_message": last_message.content[:50] + "..." if len(last_message.content) > 50 else last_message.content,
                "last_timestamp": last_message.timestamp,
                "is_from_client": last_message.is_from_client,
                "unread_count": len([m for m in messages if m.is_from_client and m.timestamp > datetime.now() - timedelta(hours=1)])
            })
    
    # Sort by last message timestamp
    conversations.sort(key=lambda x: x["last_timestamp"], reverse=True)
    
    return templates.TemplateResponse("messages_home.html", {
        "request": request,
        "owner": owner,
        "conversations": conversations,
        "total_conversations": len(conversations)
    })

@router.get("/messages/chat/{phone}", response_class=HTMLResponse)
async def chat_interface(request: Request, phone: str, db: Session = Depends(get_db)):
    """Chat interface for a specific phone number."""
    
    owner = db.query(Owner).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Get or create client
    client = db.query(Client).filter(
        Client.owner_id == owner.id,
        Client.phone == phone
    ).first()
    
    if not client:
        # Create a test client
        client = Client(
            owner_id=owner.id,
            name=f"Test Client {phone[-4:]}",
            phone=phone
        )
        db.add(client)
        db.commit()
        db.refresh(client)
    
    # Get conversation
    conversation = get_or_create_conversation(phone)
    
    # Format messages for display
    formatted_messages = []
    for msg in conversation:
        formatted_messages.append({
            "id": msg.id,
            "content": msg.content,
            "is_from_client": msg.is_from_client,
            "timestamp": msg.timestamp.strftime("%H:%M"),
            "full_timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # Get client's appointments and waitlist entries for context
    appointments = db.query(Appointment).filter(
        Appointment.client_id == client.id
    ).order_by(Appointment.start_dt.desc()).limit(5).all()
    
    waitlist_entries = db.query(Waitlist).filter(
        Waitlist.client_id == client.id
    ).all()
    
    # Get services for quick actions
    services = db.query(Service).filter(Service.owner_id == owner.id).all()
    
    return templates.TemplateResponse("chat_interface.html", {
        "request": request,
        "owner": owner,
        "client": client,
        "messages": formatted_messages,
        "appointments": appointments,
        "waitlist_entries": waitlist_entries,
        "services": services,
        "phone": phone
    })

@router.post("/messages/send")
async def send_message(
    phone: str = Form(...),
    message: str = Form(...),
    is_from_client: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Send a message in the conversation."""
    
    if not message.strip():
        return JSONResponse({"success": False, "error": "Message cannot be empty"})
    
    try:
        # Add message to conversation
        test_msg = add_message(phone, message.strip(), is_from_client)
        
        # If message is from client, process it through WhatsApp handler
        if is_from_client:
            try:
                # Enable test mode to capture bot responses
                enable_test_mode()
                
                # Clear any previous captured messages for this phone
                clear_captured_messages(phone)
                
                # Process the message through the existing client handler
                await handle_client_message(phone, message.strip(), db)
                
                # Get captured bot responses and add them to the conversation
                captured_responses = get_captured_messages(phone)
                for captured in captured_responses:
                    add_message(phone, captured["content"], False)  # Bot response
                
                # If no responses were captured, add a fallback
                if not captured_responses:
                    add_message(phone, "✅ Message processed (no response generated)", False)
                        
            except Exception as e:
                logger.error(f"Error processing WhatsApp message: {e}")
                # Add error response
                add_message(phone, "Sorry, I encountered an error processing your message. Please try again.", False)
            finally:
                # Always disable test mode when done
                disable_test_mode()
        
        return JSONResponse({
            "success": True,
            "message_id": test_msg.id,
            "timestamp": test_msg.timestamp.strftime("%H:%M")
        })
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@router.get("/messages/api/conversation/{phone}")
async def get_conversation(phone: str):
    """Get conversation messages via API (for auto-refresh)."""
    
    conversation = get_or_create_conversation(phone)
    
    messages = []
    for msg in conversation:
        messages.append({
            "id": msg.id,
            "content": msg.content,
            "is_from_client": msg.is_from_client,
            "timestamp": msg.timestamp.strftime("%H:%M"),
            "full_timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    return JSONResponse({"messages": messages})

@router.post("/messages/simulate-client")
async def simulate_client_action(
    phone: str = Form(...),
    action: str = Form(...),
    data: str = Form(""),
    db: Session = Depends(get_db)
):
    """Simulate common client actions (booking, cancellation, etc.)."""
    
    try:
        owner = db.query(Owner).first()
        if not owner:
            return JSONResponse({"success": False, "error": "Owner not found"})
        
        # Simulate different client actions
        if action == "book_service":
            service_name = data
            message = f"Hi! I'd like to book a {service_name} appointment. When do you have availability?"
            
        elif action == "join_waitlist":
            service_name = data
            message = f"Hi! I'd like to join the waitlist for {service_name}. I'm flexible with timing."
            
        elif action == "cancel_appointment":
            message = "Hi, I need to cancel my upcoming appointment. Can you help me with that?"
            
        elif action == "reschedule":
            message = "Hi, I need to reschedule my appointment. Do you have any other times available?"
            
        elif action == "check_appointments":
            message = "Hi! Can you show me my upcoming appointments?"
            
        elif action == "greeting":
            message = "Hi!"
            
        else:
            message = data or "Hello!"
        
        # Send the simulated client message
        test_msg = add_message(phone, message, True)  # From client
        
        # Enable test mode and process through existing client handler
        enable_test_mode()
        clear_captured_messages(phone)
        
        try:
            await handle_client_message(phone, message, db)
            
            # Get captured bot responses
            captured_responses = get_captured_messages(phone)
            for captured in captured_responses:
                add_message(phone, captured["content"], False)  # Bot response
            
            # If no responses captured, add fallback
            if not captured_responses:
                add_message(phone, "✅ Action processed (no response generated)", False)
                
        finally:
            disable_test_mode()
        
        return JSONResponse({
            "success": True,
            "client_message": message,
            "bot_responses": len(captured_responses)
        })
        
    except Exception as e:
        logger.error(f"Error simulating client action: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@router.post("/messages/clear/{phone}")
async def clear_conversation(phone: str):
    """Clear conversation for testing."""
    
    if phone in test_messages:
        test_messages[phone] = []
    
    # Also clear captured messages
    clear_captured_messages(phone)
    
    return JSONResponse({"success": True, "message": "Conversation cleared"})

@router.post("/messages/clear-all")
async def clear_all_conversations():
    """Clear all conversations for testing."""
    
    global test_messages
    test_messages = {}
    
    # Also clear all captured messages
    clear_captured_messages()
    
    return JSONResponse({"success": True, "message": "All conversations cleared"})
