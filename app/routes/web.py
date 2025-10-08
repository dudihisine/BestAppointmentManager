"""
Web interface routes for appointment booking and management.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Owner, Service, Client, Appointment, AppointmentStatus, OwnerSetting, IntentMode
from app.services.scheduler import AppointmentScheduler
from app.services.waitlist import WaitlistManager
from app.services.optimizer import get_optimization_suggestions
from app.utils.time import format_datetime_for_user, now_in_timezone

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """Home page - business selection or direct booking."""
    
    # Get the first owner for demo (in production, this would be business selection)
    owner = db.query(Owner).first()
    
    if not owner:
        return templates.TemplateResponse("setup_required.html", {"request": request})
    
    # Get services
    services = db.query(Service).filter(
        Service.owner_id == owner.id,
        Service.active == True
    ).all()
    
    return templates.TemplateResponse("home.html", {
        "request": request,
        "owner": owner,
        "services": services
    })


@router.get("/book", response_class=HTMLResponse)
async def booking_page(request: Request, service_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Booking page for clients."""
    
    owner = db.query(Owner).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    
    services = db.query(Service).filter(
        Service.owner_id == owner.id,
        Service.active == True
    ).all()
    
    selected_service = None
    if service_id:
        selected_service = db.query(Service).filter(
            Service.id == service_id,
            Service.owner_id == owner.id
        ).first()
    
    return templates.TemplateResponse("booking.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "selected_service": selected_service
    })


@router.post("/book", response_class=HTMLResponse)
async def process_booking(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(None),
    service_id: int = Form(...),
    preference: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process booking request and show available slots."""
    
    try:
        # Get service and owner
        service = db.query(Service).get(service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        owner = service.owner
        
        # Get or create client
        client = db.query(Client).filter(
            Client.owner_id == owner.id,
            Client.phone == phone
        ).first()
        
        if not client:
            client = Client(
                owner_id=owner.id,
                phone=phone,
                name=name,
                opt_in_move_earlier=True
            )
            db.add(client)
            db.commit()
        else:
            # Update name if provided
            client.name = name
            db.commit()
        
        # Get available slots
        scheduler = AppointmentScheduler(db)
        slot_suggestion = scheduler.suggest_slots_for_client(owner, service, preference)
        
        if not slot_suggestion.slots:
            # No slots available - offer waitlist
            return templates.TemplateResponse("waitlist_offer.html", {
                "request": request,
                "owner": owner,
                "service": service,
                "client": client,
                "preference": preference,
                "message": slot_suggestion.message
            })
        
        # Format slots for display
        formatted_slots = []
        for slot in slot_suggestion.slots:
            formatted_slots.append({
                "start_dt": slot.start_dt,
                "end_dt": slot.end_dt,
                "formatted_time": format_datetime_for_user(slot.start_dt, owner.timezone),
                "price": f"${slot.price_cents / 100:.0f}"
            })
        
        return templates.TemplateResponse("select_slot.html", {
            "request": request,
            "owner": owner,
            "service": service,
            "client": client,
            "slots": formatted_slots,
            "slot_data": [slot.__dict__ for slot in slot_suggestion.slots]
        })
        
    except Exception as e:
        logger.error(f"Booking error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "An error occurred while processing your booking. Please try again."
        })


@router.post("/confirm-booking", response_class=HTMLResponse)
async def confirm_booking(
    request: Request,
    client_id: int = Form(...),
    service_id: int = Form(...),
    slot_start: str = Form(...),
    db: Session = Depends(get_db)
):
    """Confirm and create the appointment."""
    
    try:
        # Get entities
        client = db.query(Client).get(client_id)
        service = db.query(Service).get(service_id)
        
        if not client or not service:
            raise HTTPException(status_code=404, detail="Client or service not found")
        
        owner = service.owner
        
        # Parse slot time
        start_dt = datetime.fromisoformat(slot_start)
        
        # Book appointment
        scheduler = AppointmentScheduler(db)
        appointment = scheduler.book_appointment(
            owner, client, service, start_dt,
            notes="Booked via web interface"
        )
        
        return templates.TemplateResponse("booking_confirmed.html", {
            "request": request,
            "owner": owner,
            "service": service,
            "client": client,
            "appointment": appointment,
            "formatted_time": format_datetime_for_user(appointment.start_dt, owner.timezone)
        })
        
    except Exception as e:
        logger.error(f"Booking confirmation error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Unable to confirm booking: {str(e)}"
        })


@router.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db)):
    """Owner dashboard for schedule management."""
    
    owner = db.query(Owner).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Get today's appointments
    scheduler = AppointmentScheduler(db)
    today = now_in_timezone(owner.timezone).date()
    appointments = scheduler.get_daily_schedule(owner, today)
    
    # Format appointments
    formatted_appointments = []
    total_revenue = 0
    
    for apt in appointments:
        formatted_appointments.append({
            "id": apt.id,
            "client_name": apt.client.name,
            "service_name": apt.service.name,
            "start_time": format_datetime_for_user(apt.start_dt, owner.timezone, include_date=False),
            "duration": apt.service.duration_min,
            "price": f"${apt.service.price_cents / 100:.0f}",
            "status": apt.status.value,
            "phone": apt.client.phone
        })
        total_revenue += apt.service.price_cents
    
    # Get optimization suggestions
    try:
        suggestions_result = await get_optimization_suggestions(db, owner.id, today)
        suggestions = suggestions_result.get("suggestions", [])
    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        suggestions = []
    
    # Get waitlist stats
    waitlist_manager = WaitlistManager(db)
    waitlist_stats = waitlist_manager.get_waitlist_stats(owner.id)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": owner,
        "appointments": formatted_appointments,
        "total_revenue": f"${total_revenue / 100:.0f}",
        "appointment_count": len(appointments),
        "suggestions": suggestions,
        "waitlist_stats": waitlist_stats,
        "today": today.strftime("%A, %B %d, %Y")
    })


@router.get("/appointments", response_class=HTMLResponse)
async def view_appointments(
    request: Request, 
    phone: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """View appointments for a client."""
    
    if not phone:
        return templates.TemplateResponse("find_appointments.html", {"request": request})
    
    # Find client
    client = db.query(Client).filter(Client.phone == phone).first()
    
    if not client:
        return templates.TemplateResponse("find_appointments.html", {
            "request": request,
            "error": "No appointments found for this phone number."
        })
    
    # Get upcoming appointments
    upcoming_appointments = db.query(Appointment).filter(
        Appointment.client_id == client.id,
        Appointment.start_dt > datetime.utcnow(),
        Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
    ).order_by(Appointment.start_dt).all()
    
    # Format appointments
    formatted_appointments = []
    for apt in upcoming_appointments:
        formatted_appointments.append({
            "id": apt.id,
            "service_name": apt.service.name,
            "business_name": apt.owner.name,
            "start_time": format_datetime_for_user(apt.start_dt, apt.owner.timezone),
            "duration": apt.service.duration_min,
            "price": f"${apt.service.price_cents / 100:.0f}",
            "status": apt.status.value
        })
    
    return templates.TemplateResponse("client_appointments.html", {
        "request": request,
        "client": client,
        "appointments": formatted_appointments
    })


@router.post("/cancel-appointment", response_class=HTMLResponse)
async def cancel_appointment(
    request: Request,
    appointment_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Cancel an appointment."""
    
    try:
        appointment = db.query(Appointment).get(appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        
        # Cancel the appointment
        scheduler = AppointmentScheduler(db)
        scheduler.cancel_appointment(appointment, "Cancelled via web interface")
        
        return templates.TemplateResponse("cancellation_confirmed.html", {
            "request": request,
            "appointment": appointment,
            "formatted_time": format_datetime_for_user(appointment.start_dt, appointment.owner.timezone)
        })
        
    except Exception as e:
        logger.error(f"Cancellation error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Unable to cancel appointment: {str(e)}"
        })


@router.get("/owner", response_class=HTMLResponse)
async def owner_login_page(request: Request):
    """Owner login page."""
    return templates.TemplateResponse("owner_login.html", {"request": request})


@router.post("/owner/login", response_class=HTMLResponse)
async def owner_login(request: Request, phone: str = Form(...), db: Session = Depends(get_db)):
    """Process owner login."""
    
    # Find owner by phone
    owner = db.query(Owner).filter(Owner.phone == phone).first()
    
    if not owner:
        return templates.TemplateResponse("owner_login.html", {
            "request": request,
            "error": "Owner not found with this phone number."
        })
    
    # Redirect to owner dashboard
    return RedirectResponse(url="/owner/dashboard", status_code=302)


@router.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, selected_date: str = None, db: Session = Depends(get_db)):
    """Enhanced owner dashboard with date navigation."""
    
    owner = db.query(Owner).first()
    if not owner:
        return RedirectResponse(url="/owner", status_code=302)
    
    # Parse selected date or default to today
    today = now_in_timezone(owner.timezone).date()
    if selected_date:
        try:
            view_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            view_date = today
    else:
        view_date = today
    
    # Get appointments for selected date
    scheduler = AppointmentScheduler(db)
    appointments = scheduler.get_daily_schedule(owner, view_date)
    
    # Format appointments
    formatted_appointments = []
    total_revenue = 0
    
    for apt in appointments:
        formatted_appointments.append({
            "id": apt.id,
            "client_name": apt.client.name,
            "client_phone": apt.client.phone,
            "service_name": apt.service.name,
            "start_time": format_datetime_for_user(apt.start_dt, owner.timezone, include_date=False),
            "duration": apt.service.duration_min,
            "price": f"${apt.service.price_cents / 100:.0f}",
            "status": apt.status.value,
        })
        total_revenue += apt.service.price_cents
    
    # Get optimization suggestions for the selected date
    try:
        suggestions_result = await get_optimization_suggestions(db, owner.id, view_date)
        suggestions = suggestions_result.get("suggestions", [])
    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        suggestions = []
    
    # Get week view data (7 days starting from selected date)
    week_start = view_date - timedelta(days=view_date.weekday())  # Monday of the week
    week_data = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_appointments = scheduler.get_daily_schedule(owner, day)
        day_revenue = sum(apt.service.price_cents for apt in day_appointments)
        
        week_data.append({
            "date": day,
            "is_today": day == today,
            "is_selected": day == view_date,
            "appointment_count": len(day_appointments),
            "revenue": day_revenue,
            "formatted_date": day.strftime("%a %d"),
            "iso_date": day.isoformat()
        })
    
    # Get waitlist stats
    waitlist_manager = WaitlistManager(db)
    waitlist_stats = waitlist_manager.get_waitlist_stats(owner.id)
    
    # Get owner settings
    settings = db.query(OwnerSetting).filter(OwnerSetting.owner_id == owner.id).first()
    
    return templates.TemplateResponse("owner_dashboard.html", {
        "request": request,
        "owner": owner,
        "settings": settings,
        "appointments": formatted_appointments,
        "total_revenue": f"${total_revenue / 100:.0f}",
        "appointment_count": len(appointments),
        "suggestions": suggestions,
        "waitlist_stats": waitlist_stats,
        "today": today.strftime("%A, %B %d, %Y"),
        "view_date": view_date,
        "view_date_formatted": view_date.strftime("%A, %B %d, %Y"),
        "is_today": view_date == today,
        "week_data": week_data,
        "prev_week_date": (view_date - timedelta(days=7)).isoformat(),
        "next_week_date": (view_date + timedelta(days=7)).isoformat(),
        "tomorrow_date": (view_date + timedelta(days=1)).isoformat(),
        "intent_modes": [mode.value for mode in IntentMode]
    })


@router.post("/owner/change-intent", response_class=HTMLResponse)
async def change_intent_mode(
    request: Request,
    intent: str = Form(...),
    db: Session = Depends(get_db)
):
    """Change owner's intent mode."""
    
    owner = db.query(Owner).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    try:
        # Validate intent mode
        new_intent = IntentMode(intent)
        owner.default_intent = new_intent
        db.commit()
        
        return RedirectResponse(url="/owner/dashboard?success=Intent mode updated", status_code=302)
    except ValueError:
        return RedirectResponse(url="/owner/dashboard?error=Invalid intent mode", status_code=302)


@router.get("/api/slots")
async def get_available_slots(
    service_id: int,
    preference: str = "this_week",
    db: Session = Depends(get_db)
):
    """API endpoint to get available slots (for AJAX requests)."""
    
    service = db.query(Service).get(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    owner = service.owner
    scheduler = AppointmentScheduler(db)
    slot_suggestion = scheduler.suggest_slots_for_client(owner, service, preference)
    
    # Format for JSON response
    slots_data = []
    for slot in slot_suggestion.slots:
        slots_data.append({
            "start_dt": slot.start_dt.isoformat(),
            "end_dt": slot.end_dt.isoformat(),
            "formatted_time": format_datetime_for_user(slot.start_dt, owner.timezone),
            "price": f"${slot.price_cents / 100:.0f}"
        })
    
    return {
        "success": len(slots_data) > 0,
        "slots": slots_data,
        "message": slot_suggestion.message
    }


@router.post("/owner/cancel-appointment/{appointment_id}")
async def cancel_appointment(
    appointment_id: int,
    reason: str = Form("Owner cancellation"),
    db: Session = Depends(get_db)
):
    """Cancel an appointment and trigger gap-fill optimization."""
    
    appointment = db.query(Appointment).get(appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    try:
        scheduler = AppointmentScheduler(db)
        success = scheduler.cancel_appointment(appointment, reason)
        
        if success:
            return RedirectResponse(
                url="/owner/dashboard?success=Appointment cancelled and gap-fill optimization triggered",
                status_code=302
            )
        else:
            return RedirectResponse(
                url="/owner/dashboard?error=Failed to cancel appointment",
                status_code=302
            )
    except Exception as e:
        logger.error(f"Error cancelling appointment {appointment_id}: {e}")
        return RedirectResponse(
            url=f"/owner/dashboard?error=Error cancelling appointment: {str(e)}",
            status_code=302
        )


@router.get("/owner/waitlist", response_class=HTMLResponse)
async def owner_waitlist(request: Request, db: Session = Depends(get_db)):
    """Owner waitlist management page."""
    
    owner = db.query(Owner).first()
    if not owner:
        return RedirectResponse(url="/owner", status_code=302)
    
    # Get all waitlist entries
    waitlist_entries = db.query(Waitlist).filter(
        Waitlist.owner_id == owner.id
    ).order_by(
        Waitlist.priority.desc(),
        Waitlist.created_at.asc()
    ).all()
    
    # Format waitlist entries for display
    formatted_entries = []
    for entry in waitlist_entries:
        window_start_local = from_utc(entry.window_start_dt, owner.timezone)
        window_end_local = from_utc(entry.window_end_dt, owner.timezone)
        
        # Calculate how long they've been waiting
        wait_time = now_in_timezone(owner.timezone) - from_utc(entry.created_at, owner.timezone)
        wait_days = wait_time.days
        wait_hours = wait_time.seconds // 3600
        
        if wait_days > 0:
            wait_text = f"{wait_days} day{'s' if wait_days != 1 else ''}"
        elif wait_hours > 0:
            wait_text = f"{wait_hours} hour{'s' if wait_hours != 1 else ''}"
        else:
            wait_text = "Less than 1 hour"
        
        formatted_entries.append({
            "id": entry.id,
            "client_name": entry.client.name,
            "client_phone": entry.client.phone,
            "service_name": entry.service.name,
            "service_duration": entry.service.duration_min,
            "service_price": f"${entry.service.price_cents / 100:.0f}",
            "priority": entry.priority,
            "priority_text": "HIGH PRIORITY" if entry.priority > 0 else "Normal",
            "window_start": window_start_local.strftime("%A, %B %d at %H:%M"),
            "window_end": window_end_local.strftime("%A, %B %d at %H:%M"),
            "window_start_short": window_start_local.strftime("%m/%d %H:%M"),
            "window_end_short": window_end_local.strftime("%m/%d %H:%M"),
            "created_at": format_datetime_for_user(entry.created_at, owner.timezone),
            "wait_time": wait_text,
            "is_today": window_start_local.date() == now_in_timezone(owner.timezone).date(),
            "is_tomorrow": window_start_local.date() == (now_in_timezone(owner.timezone).date() + timedelta(days=1)),
        })
    
    # Group by service for summary
    service_summary = {}
    for entry in formatted_entries:
        service = entry["service_name"]
        if service not in service_summary:
            service_summary[service] = {"count": 0, "high_priority": 0}
        service_summary[service]["count"] += 1
        if entry["priority"] > 0:
            service_summary[service]["high_priority"] += 1
    
    return templates.TemplateResponse("owner_waitlist.html", {
        "request": request,
        "owner": owner,
        "waitlist_entries": formatted_entries,
        "service_summary": service_summary,
        "total_entries": len(formatted_entries),
        "high_priority_count": len([e for e in formatted_entries if e["priority"] > 0]),
        "today": now_in_timezone(owner.timezone).strftime("%A, %B %d, %Y")
    })


@router.post("/owner/waitlist/remove/{waitlist_id}")
async def remove_from_waitlist(
    waitlist_id: int,
    reason: str = Form("Owner removed"),
    db: Session = Depends(get_db)
):
    """Remove a client from the waitlist."""
    
    waitlist_entry = db.query(Waitlist).get(waitlist_id)
    if not waitlist_entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    
    try:
        client_name = waitlist_entry.client.name
        service_name = waitlist_entry.service.name
        
        db.delete(waitlist_entry)
        db.commit()
        
        return RedirectResponse(
            url=f"/owner/waitlist?success=Removed {client_name} from {service_name} waitlist",
            status_code=302
        )
    except Exception as e:
        logger.error(f"Error removing waitlist entry {waitlist_id}: {e}")
        return RedirectResponse(
            url=f"/owner/waitlist?error=Failed to remove from waitlist: {str(e)}",
            status_code=302
        )
