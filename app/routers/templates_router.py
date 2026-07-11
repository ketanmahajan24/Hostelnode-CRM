from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import templates_col
from app.services import whatsapp_service
from app.services.whatsapp_service import WhatsAppAPIError

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request):
    docs = [d async for d in templates_col.find().sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    return templates.TemplateResponse("templates_page/index.html", {
        "request": request, "wa_templates": docs, "page": "templates",
    })


@router.post("/templates/sync", response_class=HTMLResponse)
async def sync_templates(request: Request):
    error = None
    try:
        remote = await whatsapp_service.fetch_approved_templates()
        for t in remote:
            body_component = next((c for c in t.get("components", []) if c.get("type") == "BODY"), {})
            await templates_col.update_one(
                {"name": t["name"], "language": t["language"]},
                {"$set": {
                    "name": t["name"],
                    "language": t["language"],
                    "category": t.get("category", ""),
                    "status": t.get("status", ""),
                    "components": t.get("components", []),
                    "body_text": body_component.get("text", ""),
                }},
                upsert=True,
            )
    except WhatsAppAPIError as e:
        error = str(e)

    docs = [d async for d in templates_col.find().sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    return templates.TemplateResponse("templates_page/table.html", {
        "request": request, "wa_templates": docs, "error": error,
    })
