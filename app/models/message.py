from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime, timezone

MessageType = Literal[
    "text", "image", "video", "audio", "document",
    "location", "contacts", "interactive", "button", "template", "system"
]
MessageStatus = Literal["queued", "sent", "delivered", "read", "failed"]
Direction = Literal["inbound", "outbound"]


class Message(BaseModel):
    wa_id: str                       # customer's phone number, links to conversation
    wamid: Optional[str] = None      # WhatsApp message id (from Meta)
    direction: Direction
    type: MessageType = "text"
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_mime: Optional[str] = None
    media_filename: Optional[str] = None
    caption: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    template_name: Optional[str] = None
    reply_to_wamid: Optional[str] = None
    status: MessageStatus = "sent"
    error: Optional[str] = None
    sent_by: Optional[str] = None    # agent name/email for outbound
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
