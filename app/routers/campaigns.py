from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from typing import Optional, List

from app.database import campaigns_col, templates_col, contacts_col
from app.services import whatsapp_service, message_service
from app.services.whatsapp_service import WhatsAppAPIError

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    campaigns = [c async for c in campaigns_col.find().sort("created_at", -1)]
    wa_templates = [t async for t in templates_col.find()]
    for c in campaigns:
        c["_id"] = str(c["_id"])
    for t in wa_templates:
        t["_id"] = str(t["_id"])
    return templates.TemplateResponse("campaigns/index.html", {
        "request": request, "campaigns": campaigns, "wa_templates": wa_templates, "page": "campaigns",
    })


@router.post("/campaigns/broadcast", response_class=HTMLResponse)
async def send_broadcast(request: Request, name: str = Form(...), template_name: str = Form(...),
                          language: str = Form("en_US"), target_tag: Optional[str] = Form(None)):
    query = {"tags": target_tag} if target_tag else {}
    recipients = [c async for c in contacts_col.find(query) if not c.get("is_blocked")]
    wa_ids = [c["wa_id"] for c in recipients]

    campaign_doc = {
        "name": name, "template_name": template_name, "template_language": language,
        "target_tags": [target_tag] if target_tag else [],
        "target_wa_ids": wa_ids, "status": "running",
        "total_recipients": len(wa_ids), "sent_count": 0, "delivered_count": 0,
        "read_count": 0, "failed_count": 0, "created_at": datetime.now(timezone.utc),
    }
    result = await campaigns_col.insert_one(campaign_doc)

    sent, failed = 0, 0
    for wa_id in wa_ids:
        try:
            wa_result = await whatsapp_service.send_template_message(wa_id, template_name, language)
            wamid = wa_result.get("messages", [{}])[0].get("id")
            now = datetime.now(timezone.utc)
            await message_service.save_message({
                "wa_id": wa_id, "wamid": wamid, "direction": "outbound", "type": "template",
                "template_name": template_name, "status": "sent", "sent_by": "campaign", "timestamp": now,
                "text": f"Campaign: {name}",
            })
            await message_service.upsert_conversation_on_outbound(wa_id, f"[campaign: {name}]", "template", now)
            sent += 1
        except WhatsAppAPIError:
            failed += 1

    await campaigns_col.update_one(
        {"_id": result.inserted_id},
        {"$set": {"status": "completed", "sent_count": sent, "failed_count": failed}},
    )

    campaigns = [c async for c in campaigns_col.find().sort("created_at", -1)]
    for c in campaigns:
        c["_id"] = str(c["_id"])
    return templates.TemplateResponse("campaigns/table.html", {"request": request, "campaigns": campaigns})
