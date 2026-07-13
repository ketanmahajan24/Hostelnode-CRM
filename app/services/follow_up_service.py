"""
Data-driven follow-up automation:
- schedule_next_follow_up() runs whenever a lead's status changes, setting
  contacts.next_follow_up_at based on any active rule for the new status.
- run_due_follow_ups() is the scheduler job — scans for due leads and
  executes each matching rule's action (send a nudge template, or create
  a task for a rep to handle manually).

Kept deliberately simple for a single-admin setup: no distributed locking,
no retry queue. Good enough at hundreds-of-leads scale; revisit if this
ever needs to run across multiple app instances.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from bson import ObjectId

from app.database import contacts_col, follow_up_rules_col, tasks_col
from app.services import contact_service
from app.services.whatsapp_service import send_template_message, WhatsAppAPIError
from app.services import message_service

TERMINAL_STATUSES = {"Onboarded", "Lost"}


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------

async def list_rules() -> List[dict]:
    docs = [d async for d in follow_up_rules_col.find().sort("trigger_status", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def create_rule(trigger_status: str, days_since_last_activity: int, action: str,
                       template_name: Optional[str] = None) -> dict:
    doc = {
        "trigger_status": trigger_status,
        "days_since_last_activity": days_since_last_activity,
        "action": action,   # send_template | notify_rep | escalate
        "template_name": template_name,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    result = await follow_up_rules_col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def set_rule_active(rule_id: str, is_active: bool):
    await follow_up_rules_col.update_one({"_id": ObjectId(rule_id)}, {"$set": {"is_active": is_active}})


async def delete_rule(rule_id: str):
    await follow_up_rules_col.delete_one({"_id": ObjectId(rule_id)})


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

async def list_tasks(status: str = "pending") -> List[dict]:
    query = {"status": status} if status else {}
    docs = [d async for d in tasks_col.find(query).sort("created_at", -1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def complete_task(task_id: str):
    await tasks_col.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "done"}})


async def get_active_rule(status: str) -> Optional[dict]:
    return await follow_up_rules_col.find_one({"trigger_status": status, "is_active": True})


async def schedule_next_follow_up(wa_id: str, new_status: str):
    """Call this after any status change. Sets next_follow_up_at if an active
    rule exists for the new status; clears it otherwise (nothing to schedule)."""
    if new_status in TERMINAL_STATUSES:
        await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"next_follow_up_at": None}})
        return

    rule = await get_active_rule(new_status)
    if not rule:
        await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"next_follow_up_at": None}})
        return

    due_at = datetime.now(timezone.utc) + timedelta(days=rule["days_since_last_activity"])
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"next_follow_up_at": due_at}})


async def snooze_lead(wa_id: str, days: int):
    """Manual reschedule — e.g. 'call back in 3 days'."""
    due_at = datetime.now(timezone.utc) + timedelta(days=days)
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"next_follow_up_at": due_at}})


async def _execute_rule_action(contact: dict, rule: dict) -> str:
    wa_id = contact["wa_id"]
    action = rule["action"]

    if action == "send_template":
        template_name = rule.get("template_name")
        if not template_name:
            return "skipped (rule has no template configured)"
        try:
            wa_result = await send_template_message(wa_id, template_name, rule.get("language", "en_US"))
            wamid = wa_result.get("messages", [{}])[0].get("id")
            now = datetime.now(timezone.utc)
            await message_service.save_message({
                "wa_id": wa_id, "wamid": wamid, "direction": "outbound", "type": "template",
                "template_name": template_name, "status": "sent", "sent_by": "rule_engine", "timestamp": now,
                "text": f"Auto follow-up: {template_name}",
            })
            await message_service.upsert_conversation_on_outbound(wa_id, f"[auto follow-up: {template_name}]", "template", now)
            await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"last_message_sent_at": now}})
            return f"sent template '{template_name}'"
        except WhatsAppAPIError as e:
            return f"failed to send: {e}"

    if action == "notify_rep":
        await tasks_col.insert_one({
            "wa_id": wa_id, "assigned_to": contact.get("assigned_to"),
            "type": "follow_up", "status": "pending",
            "due_at": datetime.now(timezone.utc),
            "note": f"Stale in '{contact.get('lead_status')}' — needs a follow-up",
            "created_at": datetime.now(timezone.utc),
        })
        return "created a follow-up task"

    if action == "escalate":
        await contact_service.add_tag(wa_id, "Needs Attention")
        await tasks_col.insert_one({
            "wa_id": wa_id, "assigned_to": contact.get("assigned_to"),
            "type": "escalation", "status": "pending",
            "due_at": datetime.now(timezone.utc),
            "note": f"Escalated — stuck in '{contact.get('lead_status')}' too long with no action",
            "created_at": datetime.now(timezone.utc),
        })
        return "escalated + tagged Needs Attention"

    return f"unknown action '{action}'"


async def run_due_follow_ups() -> dict:
    """The scheduler job. Returns a small summary dict for logging."""
    now = datetime.now(timezone.utc)
    cursor = contacts_col.find({
        "next_follow_up_at": {"$lte": now},
        "lead_status": {"$nin": list(TERMINAL_STATUSES)},
    })

    processed, results = 0, []
    async for contact in cursor:
        rule = await get_active_rule(contact.get("lead_status"))
        if not rule:
            # Rule was deleted/deactivated since scheduling — just clear it.
            await contacts_col.update_one({"_id": contact["_id"]}, {"$set": {"next_follow_up_at": None}})
            continue

        outcome = await _execute_rule_action(contact, rule)
        processed += 1
        results.append({"wa_id": contact["wa_id"], "outcome": outcome})

        # Fire once per stale period, then go quiet until the status changes
        # again or someone manually snoozes — avoids repeatedly nudging the
        # same lead every scheduler tick.
        await contacts_col.update_one({"_id": contact["_id"]}, {"$set": {"next_follow_up_at": None}})

    return {"processed": processed, "checked_at": now, "results": results}
