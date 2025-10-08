"""
Pydantic schemas for API request/response models.
"""
from datetime import datetime, time, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum

from app.models import IntentMode, AppointmentStatus, AuditActor


# Base schemas
class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    
    class Config:
        from_attributes = True
        use_enum_values = True


# Owner schemas
class OwnerBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)
    timezone: str = Field(default="Asia/Jerusalem", max_length=50)
    default_intent: IntentMode = Field(default=IntentMode.BALANCED)
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None


class OwnerCreate(OwnerBase):
    pass


class OwnerUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    default_intent: Optional[IntentMode] = None
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None


class Owner(OwnerBase):
    id: int
    created_at: datetime


# Owner Settings schemas
class OwnerSettingBase(BaseSchema):
    lead_time_min: int = Field(default=60, ge=0)
    cancel_window_hr: int = Field(default=24, ge=0)
    reminder_hours: List[int] = Field(default=[24, 2])
    max_outreach_per_gap: int = Field(default=5, ge=0)

    @validator('reminder_hours')
    def validate_reminder_hours(cls, v):
        if not v:
            raise ValueError('reminder_hours cannot be empty')
        if any(h < 0 for h in v):
            raise ValueError('reminder hours must be non-negative')
        return sorted(set(v), reverse=True)  # Remove duplicates and sort descending


class OwnerSettingCreate(OwnerSettingBase):
    pass


class OwnerSettingUpdate(BaseSchema):
    lead_time_min: Optional[int] = Field(None, ge=0)
    cancel_window_hr: Optional[int] = Field(None, ge=0)
    reminder_hours: Optional[List[int]] = None
    max_outreach_per_gap: Optional[int] = Field(None, ge=0)


class OwnerSetting(OwnerSettingBase):
    owner_id: int


# Availability schemas
class AvailabilityBase(BaseSchema):
    weekday: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time
    active: bool = Field(default=True)

    @validator('end_time')
    def validate_end_after_start(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v


class AvailabilityCreate(AvailabilityBase):
    pass


class AvailabilityUpdate(BaseSchema):
    weekday: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    active: Optional[bool] = None


class Availability(AvailabilityBase):
    id: int
    owner_id: int


# Block schemas
class BlockBase(BaseSchema):
    date: date
    start_time: time
    end_time: time
    reason: Optional[str] = Field(None, max_length=200)

    @validator('end_time')
    def validate_end_after_start(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v


class BlockCreate(BlockBase):
    pass


class BlockUpdate(BaseSchema):
    date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    reason: Optional[str] = Field(None, max_length=200)


class Block(BlockBase):
    id: int
    owner_id: int


# Client schemas
class ClientBase(BaseSchema):
    phone: str = Field(..., min_length=10, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    language: str = Field(default="en", max_length=10)
    opt_in_move_earlier: bool = Field(default=False)
    tags: Optional[List[str]] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    language: Optional[str] = Field(None, max_length=10)
    opt_in_move_earlier: Optional[bool] = None
    tags: Optional[List[str]] = None


class Client(ClientBase):
    id: int
    owner_id: int
    created_at: datetime


# Service schemas
class ServiceBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    duration_min: int = Field(..., gt=0)
    price_cents: int = Field(..., ge=0)
    buffer_min: int = Field(default=0, ge=0)
    groupable: bool = Field(default=False)
    active: bool = Field(default=True)


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    duration_min: Optional[int] = Field(None, gt=0)
    price_cents: Optional[int] = Field(None, ge=0)
    buffer_min: Optional[int] = Field(None, ge=0)
    groupable: Optional[bool] = None
    active: Optional[bool] = None


class Service(ServiceBase):
    id: int
    owner_id: int


# Appointment schemas
class AppointmentBase(BaseSchema):
    start_dt: datetime
    end_dt: datetime
    status: AppointmentStatus = Field(default=AppointmentStatus.PENDING)
    channel: str = Field(default="whatsapp", max_length=50)
    notes: Optional[str] = None

    @validator('end_dt')
    def validate_end_after_start(cls, v, values):
        if 'start_dt' in values and v <= values['start_dt']:
            raise ValueError('end_dt must be after start_dt')
        return v


class AppointmentCreate(BaseSchema):
    client_id: int
    service_id: int
    start_dt: datetime
    notes: Optional[str] = None


class AppointmentUpdate(BaseSchema):
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None
    status: Optional[AppointmentStatus] = None
    notes: Optional[str] = None


class Appointment(AppointmentBase):
    id: int
    owner_id: int
    client_id: int
    service_id: int
    created_at: datetime


# Waitlist schemas
class WaitlistBase(BaseSchema):
    window_start_dt: datetime
    window_end_dt: datetime
    priority: int = Field(default=0, ge=0)

    @validator('window_end_dt')
    def validate_window_end_after_start(cls, v, values):
        if 'window_start_dt' in values and v <= values['window_start_dt']:
            raise ValueError('window_end_dt must be after window_start_dt')
        return v


class WaitlistCreate(BaseSchema):
    client_id: int
    service_id: int
    window_start_dt: datetime
    window_end_dt: datetime
    priority: int = Field(default=0, ge=0)


class WaitlistUpdate(BaseSchema):
    window_start_dt: Optional[datetime] = None
    window_end_dt: Optional[datetime] = None
    priority: Optional[int] = Field(None, ge=0)


class Waitlist(WaitlistBase):
    id: int
    owner_id: int
    client_id: int
    service_id: int
    notify_count: int
    last_notified_at: Optional[datetime]
    created_at: datetime


# Audit Log schemas
class AuditLogBase(BaseSchema):
    actor: AuditActor
    action: str = Field(..., min_length=1, max_length=100)
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLog(AuditLogBase):
    id: int
    owner_id: int
    created_at: datetime


# Composite schemas for complex responses
class AppointmentWithDetails(Appointment):
    """Appointment with related client and service details."""
    client: Client
    service: Service


class ClientWithAppointments(Client):
    """Client with their appointments."""
    appointments: List[Appointment] = []


class ServiceWithAppointments(Service):
    """Service with its appointments."""
    appointments: List[Appointment] = []


class OwnerWithDetails(Owner):
    """Owner with settings and related data."""
    settings: Optional[OwnerSetting] = None
    availabilities: List[Availability] = []
    services: List[Service] = []


# WhatsApp-specific schemas
class WhatsAppMessage(BaseSchema):
    """Incoming WhatsApp message from Twilio webhook."""
    From: str = Field(..., alias="From")
    WaId: str = Field(..., alias="WaId") 
    Body: str = Field(..., alias="Body")
    MessageSid: str = Field(..., alias="MessageSid")


class WhatsAppResponse(BaseSchema):
    """Response to send via WhatsApp."""
    to: str
    text: str
    buttons: Optional[List[str]] = None


# Session state schemas for Redis
class SessionState(BaseSchema):
    """User session state stored in Redis."""
    phone: str
    state_type: str  # e.g., "booking", "setup", "reschedule"
    step: str  # current step in the flow
    data: Dict[str, Any] = {}  # collected data
    expires_at: datetime


# Scheduling schemas
class TimeSlot(BaseSchema):
    """Available time slot for booking."""
    start_dt: datetime
    end_dt: datetime
    service_id: int
    price_cents: int
    
    
class SlotSuggestion(BaseSchema):
    """Suggested slots for client booking."""
    slots: List[TimeSlot]
    message: str


class BookingRequest(BaseSchema):
    """Client booking request."""
    client_phone: str
    client_name: str
    service_id: int
    preferred_start: Optional[datetime] = None
    preferred_window_start: Optional[datetime] = None
    preferred_window_end: Optional[datetime] = None


class BookingResponse(BaseSchema):
    """Booking confirmation response."""
    success: bool
    appointment_id: Optional[int] = None
    message: str
    suggested_slots: Optional[List[TimeSlot]] = None
