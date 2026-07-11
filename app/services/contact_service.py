from datetime import datetime, timezone
from typing import Optional, List
from app.database import contacts_col


async def get_or_create_contact(wa_id: str, name: Optional[str] = None) -> dict:
    contact = await contacts_col.find_one({"wa_id": wa_id})
    if contact:
        return contact
    new_contact = {
        "wa_id": wa_id,
        "name": name or wa_id,
        "profile_photo": None,
        "city": None,
        "lead_status": "New",
        "tags": [],
        "is_blocked": False,
        "notes": [],
        "last_active": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    result = await contacts_col.insert_one(new_contact)
    new_contact["_id"] = result.inserted_id
    return new_contact


async def touch_last_active(wa_id: str):
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"last_active": datetime.now(timezone.utc)}})


async def update_contact(wa_id: str, updates: dict) -> Optional[dict]:
    updates = {k: v for k, v in updates.items() if v is not None}
    if updates:
        await contacts_col.update_one({"wa_id": wa_id}, {"$set": updates})
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


async def list_contacts(search: Optional[str] = None, tag: Optional[str] = None) -> List[dict]:
    query: dict = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"wa_id": {"$regex": search}},
        ]
    if tag:
        query["tags"] = tag
    cursor = contacts_col.find(query).sort("name", 1)
    docs = [d async for d in cursor]
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def block_contact(wa_id: str, blocked: bool = True):
    await contacts_col.update_one({"wa_id": wa_id}, {"$set": {"is_blocked": blocked}})
