from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import uuid

from app.database import templates_col
from app.services import whatsapp_service
from app.services.whatsapp_service import WhatsAppAPIError
from app.services.template_media_service import needs_header_media, validate_upload
from app.models.contact import LEAD_STATUSES
from app.config import settings

TEMPLATE_MEDIA_DIR = "static/template_media"

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _flag_missing_media(docs: list):
    """Marks templates that need a header image/video/doc but don't have one set yet."""
    for d in docs:
        d["needs_header_image"] = needs_header_media(d) and not (
            d.get("header_media_id") or d.get("header_image_url") or d.get("header_media_url")
        )


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request):
    docs = [d async for d in templates_col.find().sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    _flag_missing_media(docs)
    return templates.TemplateResponse("templates_page/index.html", {
        "request": request, "wa_templates": docs, "statuses": LEAD_STATUSES, "page": "templates",
    })


@router.post("/templates/sync", response_class=HTMLResponse)
async def sync_templates(request: Request):
    error = None
    try:
        remote = await whatsapp_service.fetch_approved_templates()
        for t in remote:
            components = t.get("components", [])
            body_component = next((c for c in components if c.get("type") == "BODY"), {})
            header_component = next((c for c in components if c.get("type") == "HEADER"), {})
            # BUG FIX: this header_type is what build_template_components() in
            # template_media_service.py depends on. Previously nothing set
            # this field, so the media-header fix silently never fired.
            header_type = header_component.get("format", "") if header_component else ""

            await templates_col.update_one(
                {"name": t["name"], "language": t["language"]},
                {
                    "$set": {
                        "name": t["name"],
                        "language": t["language"],
                        "category": t.get("category", ""),
                        "status": t.get("status", ""),
                        "components": components,
                        "body_text": body_component.get("text", ""),
                        "header_type": header_type,   # "IMAGE" | "VIDEO" | "DOCUMENT" | "TEXT" | ""
                    },
                    # Only set these on brand-new template docs — a re-sync must
                    # never wipe out settings you already configured.
                    "$setOnInsert": {
                        "maps_to_lead_status": None,
                        "header_image_url": None,
                        "header_media_id": None,
                    },
                },
                upsert=True,
            )
    except WhatsAppAPIError as e:
        error = str(e)

    docs = [d async for d in templates_col.find().sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    _flag_missing_media(docs)
    return templates.TemplateResponse("templates_page/table.html", {
        "request": request, "wa_templates": docs, "error": error, "statuses": LEAD_STATUSES,
    })


@router.post("/templates/{template_id}/map", response_class=HTMLResponse)
async def map_template_to_status(request: Request, template_id: str, lead_status: str = Form("")):
    from bson import ObjectId
    await templates_col.update_one(
        {"_id": ObjectId(template_id)},
        {"$set": {"maps_to_lead_status": lead_status or None}},
    )
    docs = [d async for d in templates_col.find().sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    _flag_missing_media(docs)
    return templates.TemplateResponse("templates_page/table.html", {
        "request": request, "wa_templates": docs, "statuses": LEAD_STATUSES,
    })


@router.post("/templates/{template_id}/header-media/upload", response_class=HTMLResponse)
async def upload_header_media(request: Request, template_id: str, file: UploadFile = File(...)):
    from bson import ObjectId

    template_doc = await templates_col.find_one({"_id": ObjectId(template_id)})
    header_type = (template_doc or {}).get("header_type", "")

    content = await file.read()
    error = validate_upload(header_type, file.filename, len(content))

    if not error:
        os.makedirs(TEMPLATE_MEDIA_DIR, exist_ok=True)
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()
        # Random filename — avoids collisions and avoids exposing your original
        # filenames publicly.
        stored_name = f"{template_id}_{uuid.uuid4().hex[:8]}{ext}"
        stored_path = os.path.join(TEMPLATE_MEDIA_DIR, stored_name)
        with open(stored_path, "wb") as f:
            f.write(content)

        # Absolute public URL — Meta's servers fetch this directly, a relative
        # path is not enough. settings.public_base_url must be YOUR real
        # public domain/IP (set it once in .env).
        public_url = f"{settings.public_base_url.rstrip('/')}/static/template_media/{stored_name}"
        await templates_col.update_one(
            {"_id": ObjectId(template_id)},
            {"$set": {"header_image_url": public_url, "header_media_id": None}},
        )

    docs = [d async for d in templates_col.find().sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    _flag_missing_media(docs)
    return templates.TemplateResponse("templates_page/table.html", {
        "request": request, "wa_templates": docs, "statuses": LEAD_STATUSES,
        "upload_error": error,
    })


@router.post("/templates/{template_id}/header-image", response_class=HTMLResponse)
async def set_header_image(request: Request, template_id: str, header_image_url: str = Form(...)):
    from bson import ObjectId
    await templates_col.update_one(
        {"_id": ObjectId(template_id)},
        {"$set": {"header_image_url": header_image_url.strip()}},
    )
    docs = [d async for d in templates_col.find().sort("name", 1)]
    for d in docs:
        d["_id"] = str(d["_id"])
    _flag_missing_media(docs)
    return templates.TemplateResponse("templates_page/table.html", {
        "request": request, "wa_templates": docs, "statuses": LEAD_STATUSES,
    })
