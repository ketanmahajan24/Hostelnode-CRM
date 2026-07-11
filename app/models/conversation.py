from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class Conversation(BaseModel):
    """One doc per customer — powers the chat list without scanning all messages."""
    wa_id: str
    last_message_text: str = ""
    last_message_type: str = "text"
    last_message_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    unread_count: int = 0
    is_archived: bool = False
    is_pinned: bool = False
    is_starred: bool = False
    is_typing: bool = False
