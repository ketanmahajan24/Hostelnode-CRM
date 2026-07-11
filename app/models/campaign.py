from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone


class Campaign(BaseModel):
    name: str
    template_name: str
    template_language: str = "en_US"
    target_tags: List[str] = Field(default_factory=list)
    target_wa_ids: List[str] = Field(default_factory=list)
    status: Literal["draft", "scheduled", "running", "completed", "failed"] = "draft"
    scheduled_at: Optional[datetime] = None
    total_recipients: int = 0
    sent_count: int = 0
    delivered_count: int = 0
    read_count: int = 0
    failed_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
