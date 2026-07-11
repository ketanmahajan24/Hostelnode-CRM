from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime, timezone


class WATemplate(BaseModel):
    """Mirrors an approved Meta template, cached locally for fast access."""
    name: str
    language: str = "en_US"
    category: str = "MARKETING"
    status: str = "APPROVED"
    components: List[Any] = Field(default_factory=list)
    body_text: Optional[str] = None
    variable_count: int = 0
    synced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuickReply(BaseModel):
    shortcut: str
    text: str
