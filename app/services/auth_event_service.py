"""
Records login/signup/logout activity for the security/activity log page.
"""
from datetime import datetime, timezone
from fastapi import Request

from app.database import auth_events_col
from app.utils.geo import get_client_ip, lookup_ip_location


async def log_auth_event(
    request: Request,
    event_type: str,          # "signup" | "login" | "login_failed" | "logout"
    user_id: str | None = None,
    email: str | None = None,
):
    ip = get_client_ip(request)
    location = await lookup_ip_location(ip)

    doc = {
        "event_type": event_type,
        "user_id": user_id,
        "email": email,
        "ip": ip,
        "user_agent": request.headers.get("user-agent", ""),
        "created_at": datetime.now(timezone.utc),  # stored with full precision (incl. seconds/microseconds)
        **{f"location_{k}": v for k, v in location.items()},
    }
    await auth_events_col.insert_one(doc)
