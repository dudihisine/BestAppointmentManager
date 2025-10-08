"""
Firestore Database Manager
Handles all database operations for the appointment system
"""
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
try:
    firebase_admin.get_app()
except ValueError:
    # Initialize if not already initialized
    firebase_admin.initialize_app()


class FirestoreDB:
    """Database manager for Firestore operations"""
    
    def __init__(self):
        self.db = firestore.client()
    
    # Owner operations
    def get_owner(self, owner_id: str) -> Optional[Dict[str, Any]]:
        """Get owner by ID"""
        doc = self.db.collection('owners').document(owner_id).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None
    
    def get_first_owner(self) -> Optional[Dict[str, Any]]:
        """Get the first owner (for single-owner systems)"""
        owners = self.db.collection('owners').limit(1).stream()
        for owner in owners:
            data = owner.to_dict()
            data['id'] = owner.id
            return data
        return None
    
    def create_owner(self, data: Dict[str, Any]) -> str:
        """Create a new owner"""
        doc_ref = self.db.collection('owners').document()
        data['created_at'] = datetime.utcnow()
        doc_ref.set(data)
        return doc_ref.id
    
    # Client operations
    def get_client_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get client by phone number"""
        clients = self.db.collection('clients').where('phone', '==', phone).limit(1).stream()
        for client in clients:
            data = client.to_dict()
            data['id'] = client.id
            return data
        return None
    
    def create_client(self, data: Dict[str, Any]) -> str:
        """Create a new client"""
        doc_ref = self.db.collection('clients').document()
        data['created_at'] = datetime.utcnow()
        doc_ref.set(data)
        return doc_ref.id
    
    def update_client(self, client_id: str, data: Dict[str, Any]):
        """Update client information"""
        self.db.collection('clients').document(client_id).update(data)
    
    # Service operations
    def get_services(self, owner_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all services for an owner"""
        query = self.db.collection('services').where('owner_id', '==', owner_id)
        if active_only:
            query = query.where('active', '==', True)
        
        services = []
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            services.append(data)
        
        return services
    
    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get service by ID"""
        doc = self.db.collection('services').document(service_id).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None
    
    # Appointment operations
    def create_appointment(self, data: Dict[str, Any]) -> str:
        """Create a new appointment"""
        doc_ref = self.db.collection('appointments').document()
        data['created_at'] = datetime.utcnow()
        doc_ref.set(data)
        return doc_ref.id
    
    def get_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """Get appointment by ID"""
        doc = self.db.collection('appointments').document(appointment_id).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None
    
    def get_client_appointments(self, client_id: str, from_date: datetime = None) -> List[Dict[str, Any]]:
        """Get all appointments for a client"""
        query = self.db.collection('appointments').where('client_id', '==', client_id)
        
        if from_date:
            query = query.where('start_dt', '>=', from_date)
        
        query = query.order_by('start_dt')
        
        appointments = []
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            appointments.append(data)
        
        return appointments
    
    def get_owner_appointments(self, owner_id: str, date: datetime) -> List[Dict[str, Any]]:
        """Get all appointments for an owner on a specific date"""
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = datetime.combine(date, datetime.max.time())
        
        query = (self.db.collection('appointments')
                .where('owner_id', '==', owner_id)
                .where('start_dt', '>=', start_of_day)
                .where('start_dt', '<=', end_of_day)
                .order_by('start_dt'))
        
        appointments = []
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            appointments.append(data)
        
        return appointments
    
    def update_appointment(self, appointment_id: str, data: Dict[str, Any]):
        """Update appointment"""
        data['updated_at'] = datetime.utcnow()
        self.db.collection('appointments').document(appointment_id).update(data)
    
    # Session operations (using Redis-like storage in Firestore)
    def get_session(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get session data for a phone number"""
        doc = self.db.collection('sessions').document(phone).get()
        if doc.exists:
            session = doc.to_dict()
            # Check if session is expired (30 minutes)
            if session.get('updated_at'):
                if datetime.utcnow() - session['updated_at'] > timedelta(minutes=30):
                    self.clear_session(phone)
                    return None
            return session
        return None
    
    def set_session(self, phone: str, data: Dict[str, Any]):
        """Set session data for a phone number"""
        data['updated_at'] = datetime.utcnow()
        self.db.collection('sessions').document(phone).set(data)
    
    def update_session(self, phone: str, data: Dict[str, Any]):
        """Update session data"""
        data['updated_at'] = datetime.utcnow()
        self.db.collection('sessions').document(phone).update(data)
    
    def clear_session(self, phone: str):
        """Clear session for a phone number"""
        self.db.collection('sessions').document(phone).delete()
    
    # Waitlist operations
    def create_waitlist_entry(self, data: Dict[str, Any]) -> str:
        """Create a waitlist entry"""
        doc_ref = self.db.collection('waitlist').document()
        data['created_at'] = datetime.utcnow()
        doc_ref.set(data)
        return doc_ref.id
    
    def get_waitlist_entries(self, owner_id: str, date: datetime = None) -> List[Dict[str, Any]]:
        """Get waitlist entries"""
        query = self.db.collection('waitlist').where('owner_id', '==', owner_id)
        
        if date:
            start_of_day = datetime.combine(date, datetime.min.time())
            end_of_day = datetime.combine(date, datetime.max.time())
            query = query.where('window_start_dt', '>=', start_of_day).where('window_start_dt', '<=', end_of_day)
        
        entries = []
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            entries.append(data)
        
        return entries
    
    def delete_waitlist_entry(self, entry_id: str):
        """Delete a waitlist entry"""
        self.db.collection('waitlist').document(entry_id).delete()
    
    # Settings operations
    def get_settings(self, owner_id: str) -> Optional[Dict[str, Any]]:
        """Get owner settings"""
        doc = self.db.collection('settings').document(owner_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    
    def update_settings(self, owner_id: str, data: Dict[str, Any]):
        """Update owner settings"""
        self.db.collection('settings').document(owner_id).set(data, merge=True)
