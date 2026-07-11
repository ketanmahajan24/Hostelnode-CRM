from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from app.utils.helpers import register_filters

from app.database import messages_col, contacts_col, conversations_col

router = APIRouter()
templates = Jinja2Templates(directory="templates")
register_filters(templates.env)


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_contacts = await contacts_col.count_documents({})
    today_sent = await messages_col.count_documents({"direction": "outbound", "timestamp": {"$gte": today_start}})
    today_received = await messages_col.count_documents({"direction": "inbound", "timestamp": {"$gte": today_start}})

    total_unread = 0
    async for c in conversations_col.find({"unread_count": {"$gt": 0}}):
        total_unread += c["unread_count"]

    recent_chats = [c async for c in conversations_col.find().sort("last_message_at", -1).limit(6)]
    recent = []
    for conv in recent_chats:
        contact = await contacts_col.find_one({"wa_id": conv["wa_id"]})
        recent.append({"conversation": conv, "contact": contact or {"name": conv["wa_id"], "wa_id": conv["wa_id"]}})

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "total_contacts": total_contacts, "today_sent": today_sent,
        "today_received": today_received, "total_unread": total_unread,
        "recent": recent, "page": "dashboard",
    })
