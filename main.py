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
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import init_indexes
from app.middlewares.logging import LoggingMiddleware
from app.middlewares.auth import AuthMiddleware
from app.utils.helpers import register_filters
from app.config import settings

from app.routers import dashboard, contacts, campaigns, analytics
from app.routers import conversations as conversations_router
from app.routers import templates_router, settings_router, auth as auth_router, security as security_router
from app.routers import follow_up_rules as follow_up_rules_router
from app.webhook import whatsapp_webhook
from app.websocket import ws_router
from app.services.follow_up_service import run_due_follow_ups


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


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_indexes()
    await check_whatsapp_connection()   # <-- yahan call kiya

    # Follow-up engine: checks for due leads every 2 hours and runs whichever
    # rule matches their current status (send nudge / notify rep / escalate).
    scheduler.add_job(run_due_follow_ups, "interval", hours=2, id="follow_up_check", replace_existing=True)
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title="HostelNode CRM", lifespan=lifespan)

# Middleware order matters: Starlette runs the LAST-added middleware FIRST.
# We need the session cookie decoded before AuthMiddleware checks it, so
# SessionMiddleware is added last (outermost).
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age_seconds,
    https_only=False,  # set True once you're serving over HTTPS in production
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# static/uploads is served through /static/uploads/<file> automatically via the mount above.

templates = Jinja2Templates(directory="templates")
register_filters(templates.env)

# Routers
app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(conversations_router.router)
app.include_router(contacts.router)
app.include_router(templates_router.router)
app.include_router(campaigns.router)
app.include_router(analytics.router)
app.include_router(settings_router.router)
app.include_router(security_router.router)
app.include_router(follow_up_rules_router.router)
app.include_router(whatsapp_webhook.router)
app.include_router(ws_router.router)