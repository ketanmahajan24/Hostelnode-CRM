from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database import contacts_col
from app.services import city_service
from app.models.contact import LEAD_STATUSES
from app.utils.helpers import register_filters

router = APIRouter()
templates = Jinja2Templates(directory="templates")
register_filters(templates.env)


@router.get("/cities", response_class=HTMLResponse)
async def city_mappings_page(request: Request):
    all_mappings = await city_service.list_mappings()
    unmapped = [m for m in all_mappings if m.get("is_unmapped_guess")]
    mapped = [m for m in all_mappings if not m.get("is_unmapped_guess")]
    return templates.TemplateResponse("cities/mappings.html", {
        "request": request, "unmapped": unmapped, "mapped": mapped, "page": "cities",
    })


@router.post("/cities/{mapping_id}/confirm")
async def confirm_city_mapping(mapping_id: str, canonical_city: str = Form(...),
                                canonical_state: str = Form("")):
    await city_service.confirm_mapping(mapping_id, canonical_city.strip(), canonical_state.strip() or None)
    return RedirectResponse(url="/cities", status_code=303)


@router.post("/cities/{mapping_id}/delete")
async def delete_city_mapping(mapping_id: str):
    await city_service.delete_mapping(mapping_id)
    return RedirectResponse(url="/cities", status_code=303)


@router.post("/cities/{canonical_city}/toggle-high-conversion")
async def toggle_high_conversion(canonical_city: str):
    await city_service.toggle_high_conversion(canonical_city)
    return RedirectResponse(url="/cities", status_code=303)


@router.get("/cities/dashboard", response_class=HTMLResponse)
async def city_dashboard(request: Request, city: Optional[str] = None):
    all_cities = await city_service.list_mappings()
    known_cities = sorted({m["canonical_city"] for m in all_cities if m.get("canonical_city")})

    now = datetime.now(timezone.utc)
    city_stats = []

    target_cities = [city] if city else known_cities
    for c in target_cities:
        total = await contacts_col.count_documents({"city": c})
        if total == 0:
            continue
        onboarded = await contacts_col.count_documents({"city": c, "lead_status": "Onboarded"})
        lost = await contacts_col.count_documents({"city": c, "lead_status": "Lost"})

        status_breakdown = {}
        for s in LEAD_STATUSES:
            status_breakdown[s] = await contacts_col.count_documents({"city": c, "lead_status": s})

        # "Stuck" = still active (not onboarded/lost) and untouched for 3+ days.
        stuck_cutoff = now - timedelta(days=3)
        stuck = await contacts_col.count_documents({
            "city": c,
            "lead_status": {"$nin": ["Onboarded", "Lost"]},
            "$or": [
                {"last_reply_at": {"$lt": stuck_cutoff}},
                {"last_reply_at": None, "created_at": {"$lt": stuck_cutoff}},
            ],
        })

        conversion_rate = round((onboarded / total) * 100, 1) if total else 0.0

        city_stats.append({
            "city": c, "total": total, "onboarded": onboarded, "lost": lost,
            "conversion_rate": conversion_rate, "stuck": stuck, "breakdown": status_breakdown,
        })

    city_stats.sort(key=lambda s: s["total"], reverse=True)

    return templates.TemplateResponse("cities/dashboard.html", {
        "request": request, "city_stats": city_stats, "known_cities": known_cities,
        "selected_city": city, "statuses": LEAD_STATUSES, "page": "cities",
    })
