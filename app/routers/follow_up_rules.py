from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId

from app.database import follow_up_rules_col, tasks_col, templates_col
from app.models.contact import LEAD_STATUSES
from app.utils.helpers import register_filters

router = APIRouter()
templates = Jinja2Templates(directory="templates")
register_filters(templates.env)

ACTIONS = ["send_template", "notify_rep", "escalate"]
NON_TERMINAL_STATUSES = [s for s in LEAD_STATUSES if s not in ("Onboarded", "Lost")]


@router.get("/follow-up-rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    rules = [r async for r in follow_up_rules_col.find().sort("trigger_status", 1)]
    for r in rules:
        r["_id"] = str(r["_id"])
    wa_templates = [t async for t in templates_col.find({"status": "APPROVED"}).sort("name", 1)]
    return templates.TemplateResponse("follow_up_rules/index.html", {
        "request": request, "rules": rules, "statuses": NON_TERMINAL_STATUSES,
        "actions": ACTIONS, "wa_templates": wa_templates, "page": "follow_up_rules",
    })


@router.post("/follow-up-rules")
async def create_rule(request: Request, trigger_status: str = Form(...), days_since_last_activity: int = Form(...),
                       action: str = Form(...), template_name: str = Form(""), is_active: bool = Form(True)):
    await follow_up_rules_col.insert_one({
        "trigger_status": trigger_status,
        "days_since_last_activity": days_since_last_activity,
        "action": action,
        "template_name": template_name or None,
        "language": "en_US",
        "is_active": is_active,
    })
    return RedirectResponse(url="/follow-up-rules", status_code=303)


@router.post("/follow-up-rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str):
    rule = await follow_up_rules_col.find_one({"_id": ObjectId(rule_id)})
    if rule:
        await follow_up_rules_col.update_one(
            {"_id": rule["_id"]}, {"$set": {"is_active": not rule.get("is_active", True)}}
        )
    return RedirectResponse(url="/follow-up-rules", status_code=303)


@router.post("/follow-up-rules/{rule_id}/delete")
async def delete_rule(rule_id: str):
    await follow_up_rules_col.delete_one({"_id": ObjectId(rule_id)})
    return RedirectResponse(url="/follow-up-rules", status_code=303)


# ---------------------------------------------------------------------------
# Tasks / "needs attention" — created automatically by the rule engine
# ---------------------------------------------------------------------------

@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    tasks = [t async for t in tasks_col.find({"status": "pending"}).sort("due_at", -1)]
    for t in tasks:
        t["_id"] = str(t["_id"])
    return templates.TemplateResponse("tasks/index.html", {
        "request": request, "tasks": tasks, "page": "tasks",
    })


@router.post("/tasks/{task_id}/done")
async def mark_task_done(task_id: str):
    await tasks_col.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "done"}})
    return RedirectResponse(url="/tasks", status_code=303)
