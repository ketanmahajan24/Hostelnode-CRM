from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone, timedelta

from app.database import messages_col, contacts_col, conversations_col

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    today_sent = await messages_col.count_documents({"direction": "outbound", "timestamp": {"$gte": today_start}})
    today_received = await messages_col.count_documents({"direction": "inbound", "timestamp": {"$gte": today_start}})
    total_unread = 0
    async for c in conversations_col.find({"unread_count": {"$gt": 0}}):
        total_unread += c["unread_count"]

    active_users = await contacts_col.count_documents({"last_active": {"$gte": now - timedelta(days=1)}})

    # last 7 days trend
    days = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        sent = await messages_col.count_documents({"direction": "outbound", "timestamp": {"$gte": day_start, "$lt": day_end}})
        received = await messages_col.count_documents({"direction": "inbound", "timestamp": {"$gte": day_start, "$lt": day_end}})
        days.append({"date": day_start.strftime("%b %d"), "sent": sent, "received": received})

    # most active contacts by inbound message count (all time, top 5)
    pipeline = [
        {"$match": {"direction": "inbound"}},
        {"$group": {"_id": "$wa_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top_raw = [r async for r in messages_col.aggregate(pipeline)]
    most_active = []
    for r in top_raw:
        contact = await contacts_col.find_one({"wa_id": r["_id"]})
        most_active.append({"wa_id": r["_id"], "name": (contact or {}).get("name", r["_id"]), "count": r["count"]})

    return templates.TemplateResponse("analytics/index.html", {
        "request": request, "today_sent": today_sent, "today_received": today_received,
        "total_unread": total_unread, "active_users": active_users,
        "days": days, "most_active": most_active, "page": "analytics",
    })
