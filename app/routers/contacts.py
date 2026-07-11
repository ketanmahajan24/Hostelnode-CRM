from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from app.services import contact_service

router = APIRouter()
templates = Jinja2Templates(directory="templates")

AVAILABLE_TAGS = ["Students", "Owners", "Influencers", "Leads", "Customers", "Blocked"]


@router.get("/contacts", response_class=HTMLResponse)
async def contacts_page(request: Request, search: Optional[str] = None, tag: Optional[str] = None):
    contacts = await contact_service.list_contacts(search, tag)
    return templates.TemplateResponse("contacts/index.html", {
        "request": request, "contacts": contacts, "tags": AVAILABLE_TAGS,
        "active_tag": tag, "page": "contacts",
    })


@router.get("/contacts/table", response_class=HTMLResponse)
async def contacts_table_partial(request: Request, search: Optional[str] = None, tag: Optional[str] = None):
    contacts = await contact_service.list_contacts(search, tag)
    return templates.TemplateResponse("contacts/table.html", {
        "request": request, "contacts": contacts,
    })


@router.post("/contacts/{wa_id}/update")
async def update_contact(wa_id: str, name: Optional[str] = Form(None), city: Optional[str] = Form(None),
                          lead_status: Optional[str] = Form(None)):
    await contact_service.update_contact(wa_id, {"name": name, "city": city, "lead_status": lead_status})
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
