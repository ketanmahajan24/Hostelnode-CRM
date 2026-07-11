from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone


class Contact(BaseModel):
    wa_id: str                     # WhatsApp phone number (E.164, no +)
    name: str = "Unknown"
    profile_photo: Optional[str] = None
    city: Optional[str] = None
    lead_status: str = "New"       # New, Contacted, Qualified, Customer, Lost
    tags: List[str] = Field(default_factory=list)   # Students, Owners, Influencers, Leads, Customers, Blocked
    is_blocked: bool = False
    notes: List[dict] = Field(default_factory=list)  # [{text, created_at}]
    last_active: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    lead_status: Optional[str] = None
    tags: Optional[List[str]] = None
    is_blocked: Optional[bool] = None
