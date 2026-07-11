from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import db
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")
quick_replies_col = db["quick_replies"]


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    quick_replies = [q async for q in quick_replies_col.find()]
    for q in quick_replies:
        q["_id"] = str(q["_id"])
    return templates.TemplateResponse("settings/index.html", {
        "request": request, "quick_replies": quick_replies,
        "wa_phone_id": settings.wa_phone_id, "page": "settings",
    })


@router.get("/api/quick-replies")
async def get_quick_replies_json():
    quick_replies = [q async for q in quick_replies_col.find()]
    return [{"shortcut": q["shortcut"], "text": q["text"]} for q in quick_replies]


@router.post("/settings/quick-replies/add", response_class=HTMLResponse)
async def add_quick_reply(request: Request, shortcut: str = Form(...), text: str = Form(...)):
    await quick_replies_col.insert_one({"shortcut": shortcut, "text": text})
    quick_replies = [q async for q in quick_replies_col.find()]
    for q in quick_replies:
        q["_id"] = str(q["_id"])
    return templates.TemplateResponse("settings/quick_replies_list.html", {
        "request": request, "quick_replies": quick_replies,
    })


@router.post("/settings/quick-replies/{reply_id}/delete", response_class=HTMLResponse)
async def delete_quick_reply(request: Request, reply_id: str):
    from bson import ObjectId
    await quick_replies_col.delete_one({"_id": ObjectId(reply_id)})
    quick_replies = [q async for q in quick_replies_col.find()]
    for q in quick_replies:
        q["_id"] = str(q["_id"])
    return templates.TemplateResponse("settings/quick_replies_list.html", {
        "request": request, "quick_replies": quick_replies,
    })
