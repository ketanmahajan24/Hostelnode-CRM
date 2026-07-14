"""
Phase 8 — full pipeline analytics: funnel by status/source/city, average
time spent per stage, and per-rep activity (ready for when this stops
being a single-admin setup).
"""
from collections import defaultdict
from datetime import datetime, timezone
from typing import List

from bson import ObjectId
from app.database import contacts_col, status_history_col, users_col
from app.models.contact import LEAD_STATUSES

AUTOMATED_TRIGGERS = {"webhook", "rule_engine", "import"}


async def get_overall_funnel() -> List[dict]:
    funnel = []
    for status in LEAD_STATUSES:
        count = await contacts_col.count_documents({"lead_status": status})
        funnel.append({"status": status, "count": count})
    return funnel


async def get_funnel_by_source() -> List[dict]:
    sources = await contacts_col.distinct("source")
    sources = sorted([s for s in sources if s])

    breakdown = []
    for source in sources:
        total = await contacts_col.count_documents({"source": source})
        onboarded = await contacts_col.count_documents({"source": source, "lead_status": "Onboarded"})
        lost = await contacts_col.count_documents({"source": source, "lead_status": "Lost"})
        conversion_rate = round((onboarded / total) * 100, 1) if total else 0.0
        breakdown.append({
            "source": source, "total": total, "onboarded": onboarded,
            "lost": lost, "conversion_rate": conversion_rate,
        })
    breakdown.sort(key=lambda b: b["total"], reverse=True)
    return breakdown


async def get_avg_days_per_stage() -> dict:
    """
    For each lead, walks its status_history in order and attributes the time
    between consecutive changes to the status it had just entered. Leads
    still sitting in a stage are counted up to now (so a stage full of
    currently-stuck leads will show a higher average — that's accurate,
    not a bug: it really has been that long for them).
    """
    now = datetime.now(timezone.utc)
    by_lead = defaultdict(list)

    async for h in status_history_col.find().sort([("wa_id", 1), ("created_at", 1)]):
        by_lead[h["wa_id"]].append(h)

    stage_durations = defaultdict(list)
    for wa_id, events in by_lead.items():
        events.sort(key=lambda e: e["created_at"])
        for i, e in enumerate(events):
            status = e.get("to_status")
            if not status:
                continue
            start = e["created_at"]
            end = events[i + 1]["created_at"] if i + 1 < len(events) else now
            duration_days = (end - start).total_seconds() / 86400
            if duration_days >= 0:
                stage_durations[status].append(duration_days)

    return {
        status: round(sum(durations) / len(durations), 1)
        for status, durations in stage_durations.items() if durations
    }


async def get_rep_activity() -> List[dict]:
    """
    Status changes triggered by an actual logged-in user (not webhook/rule
    engine/import). Useful today as a sanity check, and ready to become a
    real leaderboard once there's more than one rep.
    """
    pipeline = [
        {"$match": {"triggered_by": {"$nin": list(AUTOMATED_TRIGGERS)}}},
        {"$group": {"_id": "$triggered_by", "changes": {"$sum": 1}}},
        {"$sort": {"changes": -1}},
    ]
    raw = [r async for r in status_history_col.aggregate(pipeline)]

    results = []
    for r in raw:
        user_id = r["_id"]
        name, email = user_id, None
        try:
            user = await users_col.find_one({"_id": ObjectId(user_id)})
            if user:
                name, email = user.get("name", user_id), user.get("email")
        except Exception:
            pass
        results.append({"user_id": user_id, "name": name, "email": email, "changes": r["changes"]})
    return results


async def get_automated_vs_manual_split() -> dict:
    """How much of the pipeline movement is automation doing the work vs a human clicking."""
    total = await status_history_col.count_documents({})
    automated = await status_history_col.count_documents({"triggered_by": {"$in": list(AUTOMATED_TRIGGERS)}})
    manual = total - automated
    return {
        "total": total, "automated": automated, "manual": manual,
        "automated_pct": round((automated / total) * 100, 1) if total else 0.0,
    }
