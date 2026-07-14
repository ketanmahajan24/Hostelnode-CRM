"""
Phase 7 — "Today's follow-ups": the rep homepage. Pulls together three
sources so nothing falls through the cracks:
  1. Pending tasks from the follow-up rule engine (notify_rep/escalate)
  2. Leads whose next_follow_up_at is due or overdue
  3. Active leads with NO scheduled follow-up at all but gone stale — the
     gap a rule-based system alone would silently miss
Then scores and sorts everything by priority so the most-actionable lead
is always at the top, not just the oldest one.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone, timedelta

from app.database import contacts_col, tasks_col
from app.services import scoring_service
from app.utils.helpers import register_filters

router = APIRouter()
templates = Jinja2Templates(directory="templates")
register_filters(templates.env)

TERMINAL_STATUSES = ["Onboarded", "Lost"]
STALE_GRACE_DAYS = 3


@router.get("/today", response_class=HTMLResponse)
async def today_page(request: Request):
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=STALE_GRACE_DAYS)

    entries = {}   # wa_id -> {contact, reason}

    # 1. Pending tasks from the rule engine — these are explicit "a human needs to look at this"
    async for t in tasks_col.find({"status": "pending"}):
        contact = await contacts_col.find_one({"wa_id": t["wa_id"]})
        if not contact or contact.get("lead_status") in TERMINAL_STATUSES:
            continue
        reason = t.get("reason") or t.get("note") or f"{t.get('type', 'task').replace('_', ' ').title()}"
        entries[t["wa_id"]] = {"contact": contact, "reason": reason}

    # 2. Leads due or overdue for their scheduled follow-up
    async for c in contacts_col.find({
        "next_follow_up_at": {"$lte": now},
        "lead_status": {"$nin": TERMINAL_STATUSES},
    }):
        entries.setdefault(c["wa_id"], {"contact": c, "reason": "Follow-up due"})

    # 3. Active leads with no scheduled follow-up at all, gone stale — the gap-filler.
    # (No rule matched their status, so nothing would otherwise surface them.)
    async for c in contacts_col.find({
        "next_follow_up_at": None,
        "lead_status": {"$nin": TERMINAL_STATUSES},
    }):
        last_activity = scoring_service._most_recent_activity(c)
        if last_activity and last_activity < stale_cutoff:
            entries.setdefault(c["wa_id"], {"contact": c, "reason": "Stale — no follow-up rule set for this status"})

    rows = []
    for wa_id, data in entries.items():
        contact = data["contact"]
        score = await scoring_service.compute_priority_score(contact)
        rows.append({
            "wa_id": wa_id, "name": contact.get("name"), "pg_name": contact.get("pg_name"),
            "city": contact.get("city"), "lead_status": contact.get("lead_status"),
            "reason": data["reason"], "score": score,
        })

    rows.sort(key=lambda r: r["score"], reverse=True)

    return templates.TemplateResponse("today/index.html", {
        "request": request, "rows": rows, "page": "today",
    })
