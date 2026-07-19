from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.utils.helpers import register_filters
from datetime import datetime, timezone
from typing import Optional

from app.database import conversations_col, contacts_col
from app.services import message_service, contact_service, media_service, whatsapp_service
from app.services.whatsapp_service import WhatsAppAPIError
from app.websocket.manager import manager

router = APIRouter()
templates = Jinja2Templates(directory="templates")
register_filters(templates.env)


@router.get("/conversations", response_class=HTMLResponse)
async def conversations_page(request: Request):
    chats = await message_service.get_chat_list("all")
    return templates.TemplateResponse("conversations/index.html", {
        "request": request, "chats": chats, "active_wa_id": None, "page": "conversations",
    })


@router.get("/conversations/list", response_class=HTMLResponse)
async def chat_list_partial(request: Request, filter: str = "all", search: Optional[str] = None):
    chats = await message_service.get_chat_list(filter, search)
    return templates.TemplateResponse("conversations/chat_list.html", {
        "request": request, "chats": chats,
    })


@router.get("/conversations/{wa_id}", response_class=HTMLResponse)
async def open_conversation(request: Request, wa_id: str):
    contact = await contact_service.get_or_create_contact(wa_id)
    messages = await message_service.get_conversation_messages(wa_id)
    await message_service.mark_conversation_read(wa_id)
    chats = await message_service.get_chat_list("all")

    return templates.TemplateResponse("conversations/index.html", {
        "request": request, "chats": chats, "active_wa_id": wa_id,
        "contact": contact, "messages": messages, "page": "conversations",
    })


@router.get("/conversations/{wa_id}/window", response_class=HTMLResponse)
async def chat_window_partial(request: Request, wa_id: str):
    contact = await contact_service.get_or_create_contact(wa_id)
    messages = await message_service.get_conversation_messages(wa_id)
    await message_service.mark_conversation_read(wa_id)
    return templates.TemplateResponse("conversations/chat_window.html", {
        "request": request, "contact": contact, "messages": messages, "active_wa_id": wa_id,
    })


@router.get("/conversations/{wa_id}/panel", response_class=HTMLResponse)
async def customer_panel_partial(request: Request, wa_id: str):
    contact = await contact_service.get_or_create_contact(wa_id)
    conv = await conversations_col.find_one({"wa_id": wa_id})
    total_msgs = await message_service.get_conversation_messages(wa_id, limit=10000)
    stats = {
        "total": len(total_msgs),
        "inbound": len([m for m in total_msgs if m["direction"] == "inbound"]),
        "outbound": len([m for m in total_msgs if m["direction"] == "outbound"]),
    }
    return templates.TemplateResponse("conversations/customer_panel.html", {
        "request": request, "contact": contact, "conversation": conv, "stats": stats,
    })


@router.post("/conversations/{wa_id}/send-text", response_class=HTMLResponse)
async def send_text(request: Request, wa_id: str, body: str = Form(...)):
    if not body.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    now = datetime.now(timezone.utc)
    doc = {
        "wa_id": wa_id, "direction": "outbound", "type": "text",
        "text": body, "status": "sent", "sent_by": "agent", "timestamp": now,
    }
    try:
        result = await whatsapp_service.send_text_message(wa_id, body)
        doc["wamid"] = result.get("messages", [{}])[0].get("id")
    except WhatsAppAPIError as e:
        doc["status"] = "failed"
        doc["error"] = str(e)

    saved = await message_service.save_message(doc)
    await message_service.upsert_conversation_on_outbound(wa_id, body[:80], "text", now)
    await manager.broadcast("new_message", {
        "message": saved, "contact": {"wa_id": wa_id},
    })

    messages = await message_service.get_conversation_messages(wa_id)
    contact = await contact_service.get_or_create_contact(wa_id)
    return templates.TemplateResponse("conversations/chat_window.html", {
        "request": request, "contact": contact, "messages": messages, "active_wa_id": wa_id,
    })


@router.post("/conversations/{wa_id}/send-media", response_class=HTMLResponse)
async def send_media(request: Request, wa_id: str, file: UploadFile = File(...),
                      caption: Optional[str] = Form(None)):
    saved_file = await media_service.save_upload(file)
    media_type = _classify_mime(saved_file["mime_type"])

    now = datetime.now(timezone.utc)
    doc = {
        "wa_id": wa_id, "direction": "outbound", "type": media_type,
        "media_url": saved_file["url"], "media_mime": saved_file["mime_type"],
        "media_filename": saved_file["filename"], "caption": caption,
        "status": "sent", "sent_by": "agent", "timestamp": now,
    }

    try:
        media_id = await whatsapp_service.upload_media(saved_file["stored_path"], saved_file["mime_type"])
        result = await whatsapp_service.send_media_message(
            wa_id, media_type, media_id, id_based=True,
            caption=caption, filename=saved_file["filename"],
        )
        doc["wamid"] = result.get("messages", [{}])[0].get("id")
    except WhatsAppAPIError as e:
        doc["status"] = "failed"
        doc["error"] = str(e)

    saved = await message_service.save_message(doc)
    await message_service.upsert_conversation_on_outbound(wa_id, f"[{media_type}]", media_type, now)
    await manager.broadcast("new_message", {"message": saved, "contact": {"wa_id": wa_id}})

    messages = await message_service.get_conversation_messages(wa_id)
    contact = await contact_service.get_or_create_contact(wa_id)
    return templates.TemplateResponse("conversations/chat_window.html", {
        "request": request, "contact": contact, "messages": messages, "active_wa_id": wa_id,
    })


@router.get("/conversations/{wa_id}/templates-picker", response_class=HTMLResponse)
async def templates_picker(request: Request, wa_id: str):
    from app.database import templates_col
    docs = [d async for d in templates_col.find({"status": "APPROVED"}).sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    return templates.TemplateResponse("conversations/templates_picker.html", {
        "request": request, "wa_templates": docs, "active_wa_id": wa_id,
    })


@router.post("/conversations/{wa_id}/send-template", response_class=HTMLResponse)
async def send_template_to_chat(request: Request, wa_id: str, template_name: str = Form(...),
                                 language: str = Form("en_US")):
    now = datetime.now(timezone.utc)
    doc = {
        "wa_id": wa_id, "direction": "outbound", "type": "template",
        "template_name": template_name, "status": "sent", "sent_by": "agent", "timestamp": now,
        "text": f"Template: {template_name}",
    }
    try:
        from app.database import templates_col
        from app.services.template_media_service import build_template_components
        template_doc = await templates_col.find_one({"name": template_name})
        components = build_template_components(template_doc) if template_doc else None
        result = await whatsapp_service.send_template_message(wa_id, template_name, language, components=components)
        doc["wamid"] = result.get("messages", [{}])[0].get("id")
    except (WhatsAppAPIError, ValueError) as e:
        doc["status"] = "failed"
        doc["error"] = str(e)

    saved = await message_service.save_message(doc)
    await message_service.upsert_conversation_on_outbound(wa_id, f"[template: {template_name}]", "template", now)
    await manager.broadcast("new_message", {"message": saved, "contact": {"wa_id": wa_id}})

    messages = await message_service.get_conversation_messages(wa_id)
    contact = await contact_service.get_or_create_contact(wa_id)
    return templates.TemplateResponse("conversations/chat_window.html", {
        "request": request, "contact": contact, "messages": messages, "active_wa_id": wa_id,
    })


@router.post("/conversations/{wa_id}/pin")
async def toggle_pin(wa_id: str):
    conv = await conversations_col.find_one({"wa_id": wa_id})
    new_val = not conv.get("is_pinned", False) if conv else True
    await conversations_col.update_one({"wa_id": wa_id}, {"$set": {"is_pinned": new_val}}, upsert=True)
    return {"is_pinned": new_val}


@router.post("/conversations/{wa_id}/star")
async def toggle_star(wa_id: str):
    conv = await conversations_col.find_one({"wa_id": wa_id})
    new_val = not conv.get("is_starred", False) if conv else True
    await conversations_col.update_one({"wa_id": wa_id}, {"$set": {"is_starred": new_val}}, upsert=True)
    return {"is_starred": new_val}


@router.post("/conversations/{wa_id}/archive")
async def toggle_archive(wa_id: str):
    conv = await conversations_col.find_one({"wa_id": wa_id})
    new_val = not conv.get("is_archived", False) if conv else True
    await conversations_col.update_one({"wa_id": wa_id}, {"$set": {"is_archived": new_val}}, upsert=True)
    return {"is_archived": new_val}


def _classify_mime(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "document"
