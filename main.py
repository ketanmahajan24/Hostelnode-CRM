"""
HostelNode CRM — self-hosted WhatsApp Cloud API dashboard.

Run with:
    uvicorn main:app --reload

Requires MongoDB running locally (see .env.example) and a configured
Meta WhatsApp Cloud API app (see README.md).
"""
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_indexes
from app.middlewares.logging import LoggingMiddleware
from app.utils.helpers import register_filters
from app.config import settings

from app.routers import dashboard, contacts, campaigns, analytics
from app.routers import conversations as conversations_router
from app.routers import templates_router, settings_router
from app.webhook import whatsapp_webhook
from app.websocket import ws_router


async def check_whatsapp_connection():
    url = f"https://graph.facebook.com/{settings.wa_api_version}/{settings.wa_phone_id}"
    headers = {"Authorization": f"Bearer {settings.wa_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                url, headers=headers,
                params={"fields": "display_phone_number,verified_name"},
            )
            data = res.json()
            if res.status_code == 200:
                print(f"✅ WhatsApp API Connected! Number: {data.get('display_phone_number') or data.get('verified_name')}", flush=True)
            else:
                print(f"❌ WhatsApp API NOT connected: {data.get('error', {}).get('message')}", flush=True)
    except Exception as e:
        print(f"❌ WhatsApp API NOT connected: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_indexes()
    await check_whatsapp_connection()   # <-- yahan call kiya
    yield


app = FastAPI(title="HostelNode CRM", lifespan=lifespan)
app.add_middleware(LoggingMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

# static/uploads is served through /static/uploads/<file> automatically via the mount above.

templates = Jinja2Templates(directory="templates")
register_filters(templates.env)

# Routers
app.include_router(dashboard.router)
app.include_router(conversations_router.router)
app.include_router(contacts.router)
app.include_router(templates_router.router)
app.include_router(campaigns.router)
app.include_router(analytics.router)
app.include_router(settings_router.router)
app.include_router(whatsapp_webhook.router)
app.include_router(ws_router.router)