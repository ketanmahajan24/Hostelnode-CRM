from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import auth_events_col
from app.utils.helpers import register_filters

router = APIRouter()
templates = Jinja2Templates(directory="templates")
register_filters(templates.env)

PAGE_SIZE = 25


async def _fetch_events(skip: int, limit: int):
    cursor = auth_events_col.find().sort("created_at", -1).skip(skip).limit(limit)
    return [e async for e in cursor]


@router.get("/security/login-history", response_class=HTMLResponse)
async def login_history_page(request: Request):
    total = await auth_events_col.count_documents({})
    events = await _fetch_events(skip=0, limit=PAGE_SIZE)
    return templates.TemplateResponse("security/login_history.html", {
        "request": request, "events": events, "page": "security",
        "total": total, "next_skip": PAGE_SIZE, "page_size": PAGE_SIZE,
    })


@router.get("/security/login-history/rows", response_class=HTMLResponse)
async def login_history_rows_partial(request: Request, skip: int = 0):
    events = await _fetch_events(skip=skip, limit=PAGE_SIZE)
    total = await auth_events_col.count_documents({})
    return templates.TemplateResponse("security/login_history_rows.html", {
        "request": request, "events": events,
        "total": total, "next_skip": skip + PAGE_SIZE, "page_size": PAGE_SIZE,
    })