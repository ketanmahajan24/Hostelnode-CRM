from datetime import datetime, timezone
from typing import Optional, List
from app.database import messages_col, conversations_col, contacts_col


async def upsert_conversation_on_inbound(wa_id: str, text_preview: str, msg_type: str, when: datetime):
    await conversations_col.update_one(
        {"wa_id": wa_id},
        {
            "$set": {
                "wa_id": wa_id,
                "last_message_text": text_preview,
                "last_message_type": msg_type,
                "last_message_at": when,
            },
            "$inc": {"unread_count": 1},
            "$setOnInsert": {
                "is_archived": False, "is_pinned": False, "is_starred": False, "is_typing": False,
            },
        },
        upsert=True,
    )


async def upsert_conversation_on_outbound(wa_id: str, text_preview: str, msg_type: str, when: datetime):
    await conversations_col.update_one(
        {"wa_id": wa_id},
        {
            "$set": {
                "wa_id": wa_id,
                "last_message_text": text_preview,
                "last_message_type": msg_type,
                "last_message_at": when,
            },
            "$setOnInsert": {
                "is_archived": False, "is_pinned": False, "is_starred": False,
                "is_typing": False, "unread_count": 0,
            },
        },
        upsert=True,
    )


async def mark_conversation_read(wa_id: str):
    await conversations_col.update_one({"wa_id": wa_id}, {"$set": {"unread_count": 0}})


async def save_message(message_dict: dict) -> dict:
    result = await messages_col.insert_one(message_dict)
    message_dict["_id"] = str(result.inserted_id)
    return message_dict


async def update_message_status(wamid: str, status: str, error: Optional[str] = None):
    update = {"status": status}
    if error:
        update["error"] = error
    await messages_col.update_one({"wamid": wamid}, {"$set": update})


async def get_conversation_messages(wa_id: str, limit: int = 100, before: Optional[datetime] = None) -> List[dict]:
    query = {"wa_id": wa_id}
    if before:
        query["timestamp"] = {"$lt": before}
    cursor = messages_col.find(query).sort("timestamp", -1).limit(limit)
    docs = [d async for d in cursor]
    docs.reverse()
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def get_chat_list(filter_type: str = "all", search: Optional[str] = None) -> List[dict]:
    query: dict = {}
    if filter_type == "unread":
        query["unread_count"] = {"$gt": 0}
    elif filter_type == "archived":
        query["is_archived"] = True
    elif filter_type == "starred":
        query["is_starred"] = True
    elif filter_type == "pinned":
        query["is_pinned"] = True
    else:
        query["is_archived"] = False

    cursor = conversations_col.find(query).sort([("is_pinned", -1), ("last_message_at", -1)])
    conversations = [c async for c in cursor]

    wa_ids = [c["wa_id"] for c in conversations]
    contacts = {}
    if wa_ids:
        async for c in contacts_col.find({"wa_id": {"$in": wa_ids}}):
            contacts[c["wa_id"]] = c

    merged = []
    for conv in conversations:
        contact = contacts.get(conv["wa_id"], {"name": "Unknown", "wa_id": conv["wa_id"]})
        if search:
            s = search.lower()
            if s not in contact.get("name", "").lower() and s not in conv["wa_id"]:
                continue
        conv["_id"] = str(conv["_id"])
        contact["_id"] = str(contact.get("_id", ""))
        merged.append({"conversation": conv, "contact": contact})
    return merged
