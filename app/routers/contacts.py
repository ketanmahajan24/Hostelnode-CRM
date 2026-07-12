from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List
import asyncio
from datetime import datetime, timezone

from app.database import templates_col
from app.services import contact_service, message_service
from app.services.whatsapp_service import send_template_message, WhatsAppAPIError
from app.services.import_service import parse_leads_file
from app.models.contact import LEAD_STATUSES

router = APIRouter()
templates = Jinja2Templates(directory="templates")

AVAILABLE_TAGS = ["Students", "Owners", "Influencers", "Leads", "Customers", "Blocked"]


def _current_user_id(request: Request) -> str:
    return request.session.get("user_id") or "unknown_user"


@router.get("/contacts", response_class=HTMLResponse)
async def contacts_page(request: Request, search: Optional[str] = None, tag: Optional[str] = None,
                         status: Optional[str] = None):
    contacts = await contact_service.list_contacts(search, tag, status)
    wa_templates = [t async for t in templates_col.find().sort("name", 1)]
    return templates.TemplateResponse("contacts/index.html", {
        "request": request, "contacts": contacts, "tags": AVAILABLE_TAGS,
        "active_tag": tag, "active_status": status, "statuses": LEAD_STATUSES,
        "wa_templates": wa_templates, "page": "contacts",
    })


@router.get("/contacts/table", response_class=HTMLResponse)
async def contacts_table_partial(request: Request, search: Optional[str] = None, tag: Optional[str] = None,
                                  status: Optional[str] = None):
    contacts = await contact_service.list_contacts(search, tag, status)
    wa_templates = [t async for t in templates_col.find().sort("name", 1)]
    return templates.TemplateResponse("contacts/table.html", {
        "request": request, "contacts": contacts, "wa_templates": wa_templates,
    })


@router.post("/contacts/{wa_id}/update")
async def update_contact(request: Request, wa_id: str, name: Optional[str] = Form(None),
                          city: Optional[str] = Form(None), lead_status: Optional[str] = Form(None)):
    await contact_service.update_contact(
        wa_id, {"name": name, "city": city, "lead_status": lead_status},
        triggered_by=_current_user_id(request),
    )
    return {"ok": True}


@router.post("/contacts/{wa_id}/note")
async def add_note(wa_id: str, text: str = Form(...)):
    await contact_service.add_note(wa_id, text)
    return {"ok": True}


@router.post("/contacts/{wa_id}/tag")
async def add_tag(wa_id: str, tag: str = Form(...)):
    await contact_service.add_tag(wa_id, tag)
    return {"ok": True}


@router.post("/contacts/{wa_id}/untag")
async def remove_tag(wa_id: str, tag: str = Form(...)):
    await contact_service.remove_tag(wa_id, tag)
    return {"ok": True}


@router.post("/contacts/{wa_id}/block")
async def block_contact(wa_id: str):
    contact = await contact_service.update_contact(wa_id, {})
    new_val = not (contact or {}).get("is_blocked", False)
    await contact_service.block_contact(wa_id, new_val)
    return {"is_blocked": new_val}


# ---------------------------------------------------------------------------
# Lead import — manual + Excel/CSV
# ---------------------------------------------------------------------------

@router.get("/contacts/new", response_class=HTMLResponse)
async def new_lead_form(request: Request):
    return templates.TemplateResponse("contacts/new.html", {"request": request, "page": "contacts"})


@router.post("/contacts/new")
async def create_lead(request: Request, name: str = Form(...), phone: str = Form(...),
                       pg_name: str = Form(""), location: str = Form(""), email: str = Form("")):
    result = await contact_service.create_lead_manual(name, phone, pg_name, location, email)
    if not result["created"]:
        return templates.TemplateResponse("contacts/new.html", {
            "request": request, "page": "contacts",
            "error": "A lead with this phone number already exists.",
            "name": name, "phone": phone, "pg_name": pg_name, "location": location, "email": email,
        }, status_code=400)
    return RedirectResponse(url="/contacts", status_code=303)


@router.get("/contacts/import", response_class=HTMLResponse)
async def import_leads_page(request: Request):
    return templates.TemplateResponse("contacts/import.html", {"request": request, "page": "contacts"})


@router.post("/contacts/import", response_class=HTMLResponse)
async def import_leads_submit(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    try:
        rows = parse_leads_file(content, file.filename)
    except Exception:
        return templates.TemplateResponse("contacts/import.html", {
            "request": request, "page": "contacts",
            "error": "Could not read that file. Please upload a .xlsx or .csv file.",
        }, status_code=400)

    if not rows:
        return templates.TemplateResponse("contacts/import.html", {
            "request": request, "page": "contacts",
            "error": "No rows found, or no recognizable Name/Phone columns detected.",
        }, status_code=400)

    result = await contact_service.bulk_import_leads(rows, source="excel")
    return templates.TemplateResponse("contacts/import.html", {
        "request": request, "page": "contacts", "result": result,
    })


# ---------------------------------------------------------------------------
# Bulk WhatsApp template send
# ---------------------------------------------------------------------------

SEND_PACE_SECONDS = 0.4   # basic pacing between sends — see Phase 2 notes


@router.post("/contacts/bulk-send", response_class=HTMLResponse)
async def bulk_send_template(request: Request, wa_ids: List[str] = Form(...),
                              template_name: str = Form(...), language: str = Form("en_US")):
    triggered_by = _current_user_id(request)
    sent, failed = 0, 0

    for wa_id in wa_ids:
        try:
            wa_result = await send_template_message(wa_id, template_name, language)
            wamid = wa_result.get("messages", [{}])[0].get("id")
            now = datetime.now(timezone.utc)
            await message_service.save_message({
                "wa_id": wa_id, "wamid": wamid, "direction": "outbound", "type": "template",
                "template_name": template_name, "status": "sent", "sent_by": triggered_by, "timestamp": now,
                "text": f"Template: {template_name}",
            })
            await message_service.upsert_conversation_on_outbound(wa_id, f"[template: {template_name}]", "template", now)
            await contact_service.update_contact(
                wa_id,
                {"lead_status": "Message Sent", "last_message_sent_at": now, "assigned_template": template_name},
                triggered_by=triggered_by,
            )
            sent += 1
        except WhatsAppAPIError:
            failed += 1
        # Basic pacing so a big batch doesn't hit Meta's per-second/tier rate limits.
        await asyncio.sleep(SEND_PACE_SECONDS)

    contacts = await contact_service.list_contacts()
    wa_templates = [t async for t in templates_col.find().sort("name", 1)]
    return templates.TemplateResponse("contacts/table.html", {
        "request": request, "contacts": contacts, "wa_templates": wa_templates,
        "send_result": {"sent": sent, "failed": failed, "total": len(wa_ids)},
    })
