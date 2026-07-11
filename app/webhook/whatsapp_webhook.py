"""
Receives all inbound events from Meta:
- message webhooks (text/media/location/interactive/button)
- status webhooks (sent/delivered/read/failed)

Configure this URL in Meta App Dashboard -> WhatsApp -> Configuration -> Webhook:
  https://yourdomain.com/webhook/whatsapp
Verify token must match WA_VERIFY_TOKEN in your .env.
"""
from fastapi import APIRouter, Request, Response, Query, HTTPException
from datetime import datetime, timezone

from app.config import settings
from app.database import messages_col
from app.services import whatsapp_service, message_service, contact_service, media_service
from app.websocket.manager import manager

router = APIRouter()


@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.wa_verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request):
    payload = await request.json()

    try:
        entry = payload.get("entry", [])
        for e in entry:
            for change in e.get("changes", []):
                value = change.get("value", {})
                if "messages" in value:
                    await _handle_incoming_messages(value)
                if "statuses" in value:
                    await _handle_statuses(value)
    except Exception as exc:  # never let a malformed payload break the webhook ack
        print(f"[webhook] error processing payload: {exc}")

    return Response(status_code=200)


async def _handle_incoming_messages(value: dict):
    contacts_meta = {c["wa_id"]: c.get("profile", {}).get("name") for c in value.get("contacts", [])}

    for msg in value.get("messages", []):
        wa_id = msg["from"]
        wamid = msg["id"]
        msg_type = msg["type"]
        ts = datetime.fromtimestamp(int(msg["timestamp"]), tz=timezone.utc)

        contact = await contact_service.get_or_create_contact(wa_id, contacts_meta.get(wa_id))
        await contact_service.touch_last_active(wa_id)

        doc = {
            "wa_id": wa_id,
            "wamid": wamid,
            "direction": "inbound",
            "type": msg_type,
            "status": "delivered",
            "timestamp": ts,
        }
        preview = ""

        if msg_type == "text":
            doc["text"] = msg["text"]["body"]
            preview = doc["text"][:80]

        elif msg_type in ("image", "video", "audio", "document", "sticker"):
            media_info = msg[msg_type]
            media_meta = await whatsapp_service.get_media_url(media_info["id"])
            content = await whatsapp_service.download_media_bytes(media_meta["url"])
            saved = await media_service.save_inbound_media(
                content, media_meta.get("mime_type", ""), media_info.get("filename")
            )
            doc["media_url"] = saved["url"]
            doc["media_mime"] = saved["mime_type"]
            doc["media_filename"] = saved["filename"]
            doc["caption"] = media_info.get("caption")
            preview = f"[{msg_type}]"

        elif msg_type == "location":
            loc = msg["location"]
            doc["latitude"] = loc.get("latitude")
            doc["longitude"] = loc.get("longitude")
            preview = "[location]"

        elif msg_type == "interactive":
            interactive = msg["interactive"]
            if interactive.get("type") == "button_reply":
                doc["text"] = interactive["button_reply"]["title"]
            elif interactive.get("type") == "list_reply":
                doc["text"] = interactive["list_reply"]["title"]
            preview = doc.get("text", "[interactive reply]")

        elif msg_type == "button":
            doc["text"] = msg["button"]["text"]
            preview = doc["text"]

        else:
            preview = f"[{msg_type}]"

        saved_msg = await message_service.save_message(doc)
        await message_service.upsert_conversation_on_inbound(wa_id, preview, msg_type, ts)

        await manager.broadcast("new_message", {
            "message": saved_msg,
            "contact": {"wa_id": wa_id, "name": contact.get("name", wa_id)},
        })

        # Auto mark-as-read at the WhatsApp level so blue ticks show for the customer
        # once an agent has the conversation open (kept simple: mark read immediately).
        try:
            await whatsapp_service.mark_message_as_read(wamid)
        except Exception as exc:
            print(f"[webhook] failed to mark read: {exc}")


async def _handle_statuses(value: dict):
    for status_event in value.get("statuses", []):
        wamid = status_event["id"]
        status = status_event["status"]  # sent, delivered, read, failed
        error = None
        if status == "failed":
            errors = status_event.get("errors", [])
            error = errors[0].get("title") if errors else "Unknown error"

        await message_service.update_message_status(wamid, status, error)

        await manager.broadcast("status_update", {
            "wamid": wamid, "status": status, "error": error,
        })
