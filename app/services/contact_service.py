import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from app.database import contacts_col, status_history_col, calls_col, follow_up_rules_col

# Statuses considered "not yet replied" — an inbound plain-text message from
# these states auto-advances to Replied. Anything further along the pipeline
# is left alone so a later message doesn't regress real progress.
PRE_REPLY_STATUSES = {"New", "Message Sent"}

# Map a WhatsApp interactive button-reply title (case-insensitive, exact match)
# straight to a lead status. Edit this to match your actual template button
# text — button replies are a clean, structured signal, unlike free text.
BUTTON_REPLY_STATUS_MAP = {
    "yes, interested": "Interested",
    "interested": "Interested",
    "not interested": "Lost",
    "not now": "Lost",
}


def normalize_phone(raw: str) -> str:
    """Strip spaces/dashes/parens/plus so numbers dedupe consistently as wa_id."""
    return re.sub(r"[^\d]", "", str(raw or "").strip())


async def log_status_change(wa_id: str, from_status: Optional[str], to_status: str, triggered_by: str):
    if from_status == to_status:
        return
    await status_history_col.insert_one({
        "wa_id": wa_id,
        "from_status": from_status,
        "to_status": to_status,
        "triggered_by": triggered_by,   # a user_id, "webhook", or "rule_engine"
        "created_at": datetime.now(timezone.utc),
    })


async def get_or_create_contact(wa_id: str, name: Optional[str] = None) -> dict:
    contact = await contacts_col.find_one({"wa_id": wa_id})
    if contact:
        return contact
    new_contact = {
        "wa_id": wa_id,
        "name": name or wa_id,
        "profile_photo": None,
        "city": None,
        "location": None,
        "pg_name": None,
        "email": None,
        "source": None,
        "lead_status": "New",
        "priority_score": 0,
        "next_follow_up_at": None,
        "last_message_sent_at": None,
        "last_reply_at": None,
        "assigned_template": None,
        "tags": [],
        "is_blocked": False,
        "notes": [],
        "last_active": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    result = await contacts_col.insert_one(new_contact)
    new_contact["_id"] = result.inserted_id
    await log_status_change(wa_id, None, "New", triggered_by="import")
    return new_contact


async def touch_last_active(wa_id: str):
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"last_active": datetime.now(timezone.utc)}})


async def update_contact(wa_id: str, updates: dict, triggered_by: str = "user") -> Optional[dict]:
    updates = {k: v for k, v in updates.items() if v is not None}
    if "lead_status" in updates:
        existing = await contacts_col.find_one({"wa_id": wa_id})
        old_status = (existing or {}).get("lead_status")
        await log_status_change(wa_id, old_status, updates["lead_status"], triggered_by=triggered_by)
    if updates:
        await contacts_col.update_one({"wa_id": wa_id}, {"$set": updates})
    if "lead_status" in updates:
        # Import here (not at module top) to avoid a circular import between
        # contact_service and follow_up_service, which both reference each other.
        from app.services.follow_up_service import schedule_next_follow_up
        await schedule_next_follow_up(wa_id, updates["lead_status"])
    from app.services.scoring_service import recompute_and_store
    await recompute_and_store(wa_id)
    return await contacts_col.find_one({"wa_id": wa_id})


async def add_note(wa_id: str, text: str):
    await contacts_col.update_one(
        {"wa_id": wa_id},
        {"$push": {"notes": {"text": text, "created_at": datetime.now(timezone.utc)}}},
    )


async def add_tag(wa_id: str, tag: str):
    await contacts_col.update_one({"wa_id": wa_id}, {"$addToSet": {"tags": tag}})


async def remove_tag(wa_id: str, tag: str):
    await contacts_col.update_one({"wa_id": wa_id}, {"$pull": {"tags": tag}})


async def list_contacts(search: Optional[str] = None, tag: Optional[str] = None,
                         status: Optional[str] = None, city: Optional[str] = None,
                         days: Optional[int] = None) -> List[dict]:
    query: dict = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"wa_id": {"$regex": search}},
            {"pg_name": {"$regex": search, "$options": "i"}},
        ]
    if tag:
        query["tags"] = tag
    if status:
        query["lead_status"] = status
    if city:
        query["city"] = city
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query["created_at"] = {"$gte": cutoff}
    cursor = contacts_col.find(query).sort("created_at", -1)
    docs = [d async for d in cursor]
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def log_call(wa_id: str, outcome: str, notes: str, logged_by: str):
    await calls_col.insert_one({
        "wa_id": wa_id, "outcome": outcome, "notes": notes,
        "logged_by": logged_by, "created_at": datetime.now(timezone.utc),
    })


async def get_lead_detail(wa_id: str) -> Optional[dict]:
    contact = await contacts_col.find_one({"wa_id": wa_id})
    if not contact:
        return None
    contact["_id"] = str(contact["_id"])
    return contact


async def get_activity_timeline(wa_id: str) -> List[dict]:
    """Merges status changes, notes, and call logs into one time-ordered feed."""
    events = []

    async for h in status_history_col.find({"wa_id": wa_id}).sort("created_at", -1):
        events.append({
            "kind": "status", "created_at": h["created_at"],
            "from_status": h.get("from_status"), "to_status": h.get("to_status"),
            "triggered_by": h.get("triggered_by"),
        })

    contact = await contacts_col.find_one({"wa_id": wa_id}) or {}
    for note in contact.get("notes", []):
        events.append({"kind": "note", "created_at": note.get("created_at"), "text": note.get("text")})

    async for c in calls_col.find({"wa_id": wa_id}).sort("created_at", -1):
        events.append({
            "kind": "call", "created_at": c["created_at"],
            "outcome": c.get("outcome"), "notes": c.get("notes"), "logged_by": c.get("logged_by"),
        })

    events.sort(key=lambda e: e["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return events


async def list_cities() -> List[str]:
    return await contacts_col.distinct("city")


async def block_contact(wa_id: str, blocked: bool = True):
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"is_blocked": blocked}})


async def auto_advance_on_reply(wa_id: str, reply_text: Optional[str], is_button_reply: bool):
    """
    Called from the WhatsApp webhook whenever an inbound message arrives.
    Button replies get an exact status mapping (structured signal).
    Plain text only advances New/Message Sent -> Replied — it never
    regresses a lead that's already further along the pipeline.
    """
    now = datetime.now(timezone.utc)
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"last_reply_at": now}})

    contact = await contacts_col.find_one({"wa_id": wa_id})
    current_status = (contact or {}).get("lead_status")

    if is_button_reply and reply_text:
        mapped = BUTTON_REPLY_STATUS_MAP.get(reply_text.strip().lower())
        if mapped:
            await update_contact(wa_id, {"lead_status": mapped}, triggered_by="webhook")
            return

    if current_status in PRE_REPLY_STATUSES:
        await update_contact(wa_id, {"lead_status": "Replied"}, triggered_by="webhook")


# ---------------------------------------------------------------------------
# Lead import
# ---------------------------------------------------------------------------

async def create_lead_manual(name: str, phone: str, pg_name: str, location: str, email: str,
                              source: str = "manual") -> dict:
    from app.services.city_service import normalize_city

    wa_id = normalize_phone(phone)
    existing = await contacts_col.find_one({"wa_id": wa_id})
    if existing:
        return {"created": False, "wa_id": wa_id, "reason": "duplicate phone"}

    city, state = await normalize_city(location)
    contact = await get_or_create_contact(wa_id, name=name)
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {
        "pg_name": pg_name, "location": location, "email": email, "source": source,
        "city": city, "state": state,
    }})
    return {"created": True, "wa_id": wa_id}


async def bulk_import_leads(rows: List[dict], source: str = "excel") -> dict:
    """
    rows: list of dicts already mapped to {name, phone, pg_name, location, email}.
    Dedupes by phone (wa_id) — existing contacts are skipped, not overwritten.
    """
    from app.services.city_service import normalize_city

    created, skipped = 0, 0
    for row in rows:
        phone = normalize_phone(row.get("phone", ""))
        if not phone:
            skipped += 1
            continue
        existing = await contacts_col.find_one({"wa_id": phone})
        if existing:
            skipped += 1
            continue
        city, state = await normalize_city(row.get("location"))
        await get_or_create_contact(phone, name=row.get("name") or phone)
        await contacts_col.update_one({"wa_id": phone}, {"$set": {
            "pg_name": row.get("pg_name"),
            "location": row.get("location"),
            "email": row.get("email"),
            "source": source,
            "city": city,
            "state": state,
        }})
        created += 1
    return {"created": created, "skipped": skipped, "total": len(rows)}
