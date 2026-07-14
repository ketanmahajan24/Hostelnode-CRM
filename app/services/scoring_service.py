"""
Phase 7 — priority scoring. A simple, explainable weighted score so the
pipeline can be sorted by "most worth acting on right now" instead of just
oldest-first or alphabetical.

    score = (+20 if replied within 1hr of the outbound message)
          + (+10 if the lead's city is flagged high-conversion)
          + (+15 if source == "referral")
          - (5 per day stale beyond a 3-day grace period)

This is intentionally simple and fully explainable — every point is
traceable to one factor, so you can tell at a glance why a lead ranks
where it does, rather than trusting an opaque number.
"""
from datetime import datetime, timezone
from typing import Optional

from app.database import contacts_col
from app.services import city_service

STALE_GRACE_DAYS = 3
STALE_PENALTY_PER_DAY = 5
FAST_REPLY_BONUS = 20
FAST_REPLY_WINDOW_MINUTES = 60
HIGH_CONVERSION_CITY_BONUS = 10
REFERRAL_SOURCE_BONUS = 15


def _most_recent_activity(contact: dict) -> Optional[datetime]:
    """The most recent thing that happened on this lead — used to measure staleness."""
    candidates = [
        contact.get("last_reply_at"),
        contact.get("last_message_sent_at"),
        contact.get("created_at"),
    ]
    candidates = [c for c in candidates if c is not None]
    return max(candidates) if candidates else None


async def compute_priority_score(contact: dict) -> int:
    score = 0
    now = datetime.now(timezone.utc)

    last_sent = contact.get("last_message_sent_at")
    last_reply = contact.get("last_reply_at")
    if last_sent and last_reply and last_reply >= last_sent:
        reply_gap_minutes = (last_reply - last_sent).total_seconds() / 60
        if reply_gap_minutes <= FAST_REPLY_WINDOW_MINUTES:
            score += FAST_REPLY_BONUS

    if await city_service.is_high_conversion_city(contact.get("city")):
        score += HIGH_CONVERSION_CITY_BONUS

    if contact.get("source") == "referral":
        score += REFERRAL_SOURCE_BONUS

    last_activity = _most_recent_activity(contact)
    if last_activity:
        stale_days = (now - last_activity).days
        if stale_days > STALE_GRACE_DAYS:
            score -= STALE_PENALTY_PER_DAY * (stale_days - STALE_GRACE_DAYS)

    return score


async def recompute_and_store(wa_id: str) -> int:
    """Recomputes and persists the score — call this after any event that
    could change it (reply received, status change, message sent)."""
    contact = await contacts_col.find_one({"wa_id": wa_id})
    if not contact:
        return 0
    score = await compute_priority_score(contact)
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"priority_score": score}})
    return score
