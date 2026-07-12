"""
Motor (async MongoDB driver) connection + index setup.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.mongo_uri)
db = client[settings.mongo_db_name]

# Collections
contacts_col = db["contacts"]
messages_col = db["messages"]
conversations_col = db["conversations"]
templates_col = db["templates"]
campaigns_col = db["campaigns"]
notes_col = db["notes"]
tags_col = db["tags"]
media_col = db["media"]
users_col = db["users"]
auth_events_col = db["auth_events"]
status_history_col = db["status_history"]
calls_col = db["calls"]


async def init_indexes():
    """Create indexes needed for performant lookups. Call once at startup."""
    await contacts_col.create_index("wa_id", unique=True)
    await contacts_col.create_index("name")
    await contacts_col.create_index("tags")

    await conversations_col.create_index("wa_id", unique=True)
    await conversations_col.create_index("last_message_at")
    await conversations_col.create_index("unread_count")
    await conversations_col.create_index("is_archived")
    await conversations_col.create_index("is_pinned")
    await conversations_col.create_index("is_starred")

    await messages_col.create_index("wa_id")
    await messages_col.create_index("wamid", unique=True, sparse=True)
    await messages_col.create_index("timestamp")

    await templates_col.create_index("name")
    await campaigns_col.create_index("created_at")
    await tags_col.create_index("name", unique=True)

    await users_col.create_index("email", unique=True)

    await auth_events_col.create_index("created_at")
    await auth_events_col.create_index("user_id")
    await auth_events_col.create_index("event_type")

    await status_history_col.create_index("wa_id")
    await status_history_col.create_index("created_at")

    await calls_col.create_index("wa_id")
    await calls_col.create_index("created_at")
