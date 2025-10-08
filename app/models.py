"""
SQLAlchemy models for the appointment management system.
"""
from datetime import datetime, time, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Time, Boolean, 
    Text, JSON, Enum, ForeignKey, Index, CheckConstraint,
    DECIMAL, UniqueConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
import enum

from app.db import Base


class IntentMode(enum.Enum):
    """Owner's scheduling intent modes."""
    PROFIT = "profit"
    BALANCED = "balanced"
    FREE_TIME = "free_time"


class AppointmentStatus(enum.Enum):
    """Appointment status options."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class AuditActor(enum.Enum):
    """Who performed the action in audit log."""
    OWNER = "owner"
    CLIENT = "client"
    SYSTEM = "system"


class Owner(Base):
    """Business owner entity."""
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Jerusalem")
    default_intent: Mapped[IntentMode] = mapped_column(Enum(IntentMode), nullable=False, default=IntentMode.BALANCED)
    quiet_hours_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    settings: Mapped[Optional["OwnerSetting"]] = relationship("OwnerSetting", back_populates="owner", uselist=False)
    availabilities: Mapped[List["Availability"]] = relationship("Availability", back_populates="owner")
    blocks: Mapped[List["Block"]] = relationship("Block", back_populates="owner")
    clients: Mapped[List["Client"]] = relationship("Client", back_populates="owner")
    services: Mapped[List["Service"]] = relationship("Service", back_populates="owner")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="owner")
    waitlists: Mapped[List["Waitlist"]] = relationship("Waitlist", back_populates="owner")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="owner")

    def __repr__(self):
        return f"<Owner(id={self.id}, name='{self.name}', phone='{self.phone}')>"


class OwnerSetting(Base):
    """Owner's business settings and policies."""
    __tablename__ = "owner_settings"

    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), primary_key=True)
    lead_time_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)  # minutes
    cancel_window_hr: Mapped[int] = mapped_column(Integer, nullable=False, default=24)  # hours
    reminder_hours: Mapped[List[int]] = mapped_column(JSON, nullable=False, default=[24, 2])  # hours before appointment
    max_outreach_per_gap: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="settings")

    __table_args__ = (
        CheckConstraint("lead_time_min >= 0", name="check_lead_time_positive"),
        CheckConstraint("cancel_window_hr >= 0", name="check_cancel_window_positive"),
        CheckConstraint("max_outreach_per_gap >= 0", name="check_max_outreach_positive"),
    )

    def __repr__(self):
        return f"<OwnerSetting(owner_id={self.owner_id}, lead_time={self.lead_time_min}min)>"


class Availability(Base):
    """Owner's weekly availability schedule."""
    __tablename__ = "availabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="availabilities")

    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="check_weekday_range"),
        Index("idx_owner_weekday_active", "owner_id", "weekday", "active"),
    )

    def __repr__(self):
        return f"<Availability(owner_id={self.owner_id}, weekday={self.weekday}, {self.start_time}-{self.end_time})>"


class Block(Base):
    """Owner's blocked time periods (breaks, personal time, etc.)."""
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="blocks")

    __table_args__ = (
        Index("idx_owner_date", "owner_id", "date"),
    )

    def __repr__(self):
        return f"<Block(owner_id={self.owner_id}, date={self.date}, {self.start_time}-{self.end_time})>"


class Client(Base):
    """Client/customer entity."""
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    opt_in_move_earlier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="clients")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="client")
    waitlists: Mapped[List["Waitlist"]] = relationship("Waitlist", back_populates="client")

    __table_args__ = (
        UniqueConstraint("owner_id", "phone", name="uq_owner_client_phone"),
        Index("idx_owner_phone", "owner_id", "phone"),
    )

    def __repr__(self):
        return f"<Client(id={self.id}, name='{self.name}', phone='{self.phone}')>"


class Service(Base):
    """Services offered by the business."""
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    groupable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="services")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="service")
    waitlists: Mapped[List["Waitlist"]] = relationship("Waitlist", back_populates="service")

    __table_args__ = (
        CheckConstraint("duration_min > 0", name="check_duration_positive"),
        CheckConstraint("price_cents >= 0", name="check_price_non_negative"),
        CheckConstraint("buffer_min >= 0", name="check_buffer_non_negative"),
        Index("idx_owner_active", "owner_id", "active"),
    )

    def __repr__(self):
        return f"<Service(id={self.id}, name='{self.name}', duration={self.duration_min}min, price=${self.price_cents/100:.2f})>"


class Appointment(Base):
    """Scheduled appointments."""
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("services.id"), nullable=False)
    start_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.PENDING)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="whatsapp")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="appointments")
    client: Mapped["Client"] = relationship("Client", back_populates="appointments")
    service: Mapped["Service"] = relationship("Service", back_populates="appointments")

    __table_args__ = (
        CheckConstraint("end_dt > start_dt", name="check_end_after_start"),
        Index("idx_owner_start_dt", "owner_id", "start_dt"),
        Index("idx_owner_date_status", "owner_id", "start_dt", "status"),
        Index("idx_client_start_dt", "client_id", "start_dt"),
    )

    def __repr__(self):
        return f"<Appointment(id={self.id}, client_id={self.client_id}, service_id={self.service_id}, start={self.start_dt})>"


class Waitlist(Base):
    """Client waitlist for services when no slots available."""
    __tablename__ = "waitlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("services.id"), nullable=False)
    window_start_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notify_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="waitlists")
    client: Mapped["Client"] = relationship("Client", back_populates="waitlists")
    service: Mapped["Service"] = relationship("Service", back_populates="waitlists")

    __table_args__ = (
        CheckConstraint("window_end_dt > window_start_dt", name="check_window_end_after_start"),
        CheckConstraint("priority >= 0", name="check_priority_non_negative"),
        CheckConstraint("notify_count >= 0", name="check_notify_count_non_negative"),
        Index("idx_owner_window", "owner_id", "window_start_dt", "window_end_dt"),
        Index("idx_priority_created", "priority", "created_at"),
    )

    def __repr__(self):
        return f"<Waitlist(id={self.id}, client_id={self.client_id}, service_id={self.service_id}, window={self.window_start_dt}-{self.window_end_dt})>"


class AuditLog(Base):
    """Audit trail for all system actions."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    actor: Mapped[AuditActor] = mapped_column(Enum(AuditActor), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_owner_created", "owner_id", "created_at"),
        Index("idx_actor_action", "actor", "action"),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, owner_id={self.owner_id}, actor={self.actor.value}, action='{self.action}')>"
