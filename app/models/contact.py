from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone

# The full PG-lead pipeline. "New" through "Onboarded" is the happy path;
# "Lost" is reachable from any stage.
LEAD_STATUSES = [
    "New", "Message Sent", "Replied", "Interested",
    "Wants Details", "Signed Up", "Listed", "Onboarded", "Lost",
]


class Contact(BaseModel):
    wa_id: str                     # WhatsApp phone number (E.164, no +) — also the lead's phone
    name: str = "Unknown"
    profile_photo: Optional[str] = None
    city: Optional[str] = None
    location: Optional[str] = None     # raw location text as imported/entered
    pg_name: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None       # cold_list, referral, ad, walk_in, manual
    lead_status: str = "New"
    priority_score: int = 0
    next_follow_up_at: Optional[datetime] = None
    last_message_sent_at: Optional[datetime] = None
    last_reply_at: Optional[datetime] = None
    assigned_template: Optional[str] = None
    tags: List[str] = Field(default_factory=list)   # Students, Owners, Influencers, Leads, Customers, Blocked
    is_blocked: bool = False
    notes: List[dict] = Field(default_factory=list)  # [{text, created_at}]
    last_active: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    location: Optional[str] = None
    pg_name: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    lead_status: Optional[str] = None
    tags: Optional[List[str]] = None
    is_blocked: Optional[bool] = None
