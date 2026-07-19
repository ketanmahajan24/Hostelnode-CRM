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
from app.services.template_media_service import build_template_components
from app.utils.helpers import register_filters

router = APIRouter()
templates = Jinja2Templates(directory="templates")
register_filters(templates.env)

AVAILABLE_TAGS = ["Students", "Owners", "Influencers", "Leads", "Customers", "Blocked"]


def _current_user_id(request: Request) -> str:
    return request.session.get("user_id") or "unknown_user"


@router.get("/contacts", response_class=HTMLResponse)
async def contacts_page(request: Request, search: Optional[str] = None, tag: Optional[str] = None,
                         status: Optional[str] = None, city: Optional[str] = None):
    contacts = await contact_service.list_contacts(search, tag, status, city)
    wa_templates = [t async for t in templates_col.find().sort("name", 1)]
    cities = sorted([c for c in await contact_service.list_cities() if c])
    return templates.TemplateResponse("contacts/index.html", {
        "request": request, "contacts": contacts, "tags": AVAILABLE_TAGS,
        "active_tag": tag, "active_status": status, "active_city": city, "statuses": LEAD_STATUSES,
        "wa_templates": wa_templates, "cities": cities, "page": "contacts",
    })


@router.get("/contacts/table", response_class=HTMLResponse)
async def contacts_table_partial(request: Request, search: Optional[str] = None, tag: Optional[str] = None,
                                  status: Optional[str] = None, city: Optional[str] = None):
    contacts = await contact_service.list_contacts(search, tag, status, city)
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

@router.post("/contacts/{wa_id}/snooze")
async def snooze_lead(wa_id: str, days: int = Form(...)):
    from app.services.follow_up_service import snooze_lead as _snooze
    await _snooze(wa_id, days)
    return RedirectResponse(url=f"/contacts/{wa_id}/detail", status_code=303)


@router.get("/contacts/{wa_id}/detail", response_class=HTMLResponse)
async def lead_detail_page(request: Request, wa_id: str):
    contact = await contact_service.get_lead_detail(wa_id)
    if not contact:
        return RedirectResponse(url="/contacts", status_code=303)
    timeline = await contact_service.get_activity_timeline(wa_id)
    return templates.TemplateResponse("contacts/detail.html", {
        "request": request, "contact": contact, "timeline": timeline,
        "statuses": LEAD_STATUSES, "page": "contacts",
    })


@router.post("/contacts/{wa_id}/detail/note")
async def add_note_from_detail(wa_id: str, text: str = Form(...)):
    await contact_service.add_note(wa_id, text)
    return RedirectResponse(url=f"/contacts/{wa_id}/detail", status_code=303)


@router.post("/contacts/{wa_id}/snooze")
async def snooze_lead(wa_id: str, days: int = Form(...)):
    from app.services.follow_up_service import snooze_lead as do_snooze
    await do_snooze(wa_id, days)
    return RedirectResponse(url=f"/contacts/{wa_id}/detail", status_code=303)


@router.post("/contacts/{wa_id}/call")
async def log_call(request: Request, wa_id: str, outcome: str = Form(...), notes: str = Form("")):
    await contact_service.log_call(wa_id, outcome, notes, logged_by=_current_user_id(request))
    return RedirectResponse(url=f"/contacts/{wa_id}/detail", status_code=303)


@router.get("/contacts/cities", response_class=HTMLResponse)
async def city_mappings_page(request: Request):
    from app.services import city_service
    mappings = await city_service.list_mappings()
    return templates.TemplateResponse("contacts/cities.html", {
        "request": request, "mappings": mappings, "page": "contacts",
    })


@router.post("/contacts/cities")
async def create_city_mapping(canonical_city: str = Form(...), canonical_state: str = Form(""),
                               raw_variants: str = Form(...)):
    from app.services import city_service
    variants = [v.strip() for v in raw_variants.split(",") if v.strip()]
    await city_service.create_or_update_mapping(canonical_city.strip(), canonical_state.strip() or None, variants)
    return RedirectResponse(url="/contacts/cities", status_code=303)


@router.post("/contacts/cities/{mapping_id}/delete")
async def delete_city_mapping(mapping_id: str):
    from app.services import city_service
    await city_service.delete_mapping(mapping_id)
    return RedirectResponse(url="/contacts/cities", status_code=303)


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
    sent, failed, unmapped = 0, 0, 0
    fail_reasons = set()
    auto_mode = template_name == "__auto__"

    for wa_id in wa_ids:
        this_template_name, this_language = template_name, language
        lead_status = None
        template_doc = None

        if auto_mode:
            contact = await contact_service.get_lead_detail(wa_id)
            lead_status = (contact or {}).get("lead_status")
            mapped = await templates_col.find_one({"maps_to_lead_status": lead_status, "status": "APPROVED"})
            if not mapped:
                unmapped += 1
                continue
            this_template_name, this_language = mapped["name"], mapped["language"]
            template_doc = mapped
        else:
            template_doc = await templates_col.find_one({"name": this_template_name, "language": this_language})

        # BUG FIX: templates with a media header need that media supplied on
        # every send, or Meta rejects the whole message (this was the cause of
        # 100%-failed campaigns — see conversation history).
        try:
            header_components = build_template_components(template_doc) if template_doc else None
        except ValueError as e:
            failed += 1
            fail_reasons.add(str(e))
            continue

        try:
            wa_result = await send_template_message(wa_id, this_template_name, this_language, components=header_components)
            wamid = wa_result.get("messages", [{}])[0].get("id")
            now = datetime.now(timezone.utc)
            await message_service.save_message({
                "wa_id": wa_id, "wamid": wamid, "direction": "outbound", "type": "template",
                "template_name": this_template_name, "status": "sent", "sent_by": triggered_by, "timestamp": now,
                "text": f"Template: {this_template_name}",
            })
            await message_service.upsert_conversation_on_outbound(wa_id, f"[template: {this_template_name}]", "template", now)

            updates = {"last_message_sent_at": now, "assigned_template": this_template_name}
            # Auto mode already matched the template to the lead's current status,
            # so only bump a brand-new lead forward — don't touch anyone further
            # along the pipeline. Manual mode (explicit template pick) always
            # advances to "Message Sent", same as before.
            if not auto_mode or lead_status == "New":
                updates["lead_status"] = "Message Sent"
            await contact_service.update_contact(wa_id, updates, triggered_by=triggered_by)
            sent += 1
        except WhatsAppAPIError as e:
            failed += 1
            print(f"[bulk-send] failed for {wa_id} ({this_template_name}): {e}")
            fail_reasons.add(str(e))
        # Basic pacing so a big batch doesn't hit Meta's per-second/tier rate limits.
        await asyncio.sleep(SEND_PACE_SECONDS)

    contacts = await contact_service.list_contacts()
    wa_templates = [t async for t in templates_col.find().sort("name", 1)]
    return templates.TemplateResponse("contacts/table.html", {
        "request": request, "contacts": contacts, "wa_templates": wa_templates,
        "send_result": {
            "sent": sent, "failed": failed, "unmapped": unmapped, "total": len(wa_ids),
            "fail_reasons": list(fail_reasons),
        },
    })
