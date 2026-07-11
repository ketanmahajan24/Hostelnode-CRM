from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone

from app.database import users_col
from app.utils.security import hash_password, verify_password
from app.services.auth_event_service import log_auth_event

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# async def _signup_is_open() -> bool:
#     """Signup is only available until the first (admin) account exists."""
#     existing = await users_col.count_documents({})
#     return existing == 0


# @router.get("/signup", response_class=HTMLResponse)
# async def signup_page(request: Request):
#     if not await _signup_is_open():
#         return RedirectResponse(url="/login", status_code=303)
#     return templates.TemplateResponse("auth/signup.html", {"request": request})


# @router.post("/signup", response_class=HTMLResponse)
# async def signup_submit(
#     request: Request,
#     name: str = Form(...),
#     email: str = Form(...),
#     password: str = Form(...),
#     confirm_password: str = Form(...),
# ):
#     if not await _signup_is_open():
#         return RedirectResponse(url="/login", status_code=303)
#
#     email = email.strip().lower()
#     ctx = {"request": request, "name": name, "email": email}
#
#     if len(password) < 8:
#         ctx["error"] = "Password must be at least 8 characters."
#         return templates.TemplateResponse("auth/signup.html", ctx, status_code=400)
#
#     if password != confirm_password:
#         ctx["error"] = "Passwords do not match."
#         return templates.TemplateResponse("auth/signup.html", ctx, status_code=400)
#
#     existing = await users_col.find_one({"email": email})
#     if existing:
#         ctx["error"] = "An account with that email already exists."
#         return templates.TemplateResponse("auth/signup.html", ctx, status_code=400)
#
#     user_doc = {
#         "name": name.strip(),
#         "email": email,
#         "password_hash": hash_password(password),
#         "role": "admin",
#         "is_active": True,
#         "created_at": datetime.now(timezone.utc),
#         "last_login_at": None,
#     }
#     result = await users_col.insert_one(user_doc)
#
#     request.session["user_id"] = str(result.inserted_id)
#     request.session["user_name"] = user_doc["name"]
#     request.session["user_email"] = user_doc["email"]
#
#     await log_auth_event(request, "signup", user_id=str(result.inserted_id), email=user_doc["email"])
#
#     return RedirectResponse(url="/", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    allow_signup = False   # signup route disabled — see commented-out block above
    return templates.TemplateResponse("auth/login.html", {
        "request": request, "next": next, "allow_signup": allow_signup,
    })


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    email = email.strip().lower()
    allow_signup = False   # signup route disabled — see commented-out block above

    user = await users_col.find_one({"email": email})
    if not user or not user.get("is_active", True) or not verify_password(password, user["password_hash"]):
        # Track failed attempts too — useful for spotting brute-force/guessing.
        await log_auth_event(request, "login_failed", user_id=None, email=email)
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "email": email, "next": next,
            "allow_signup": allow_signup, "error": "Incorrect email or password.",
        }, status_code=400)

    await users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login_at": datetime.now(timezone.utc)}},
    )

    request.session["user_id"] = str(user["_id"])
    request.session["user_name"] = user.get("name", "Admin")
    request.session["user_email"] = user["email"]

    await log_auth_event(request, "login", user_id=str(user["_id"]), email=user["email"])

    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    return RedirectResponse(url=safe_next, status_code=303)


@router.get("/logout")
async def logout(request: Request):
    user_id = request.session.get("user_id")
    email = request.session.get("user_email")
    if user_id:
        await log_auth_event(request, "logout", user_id=user_id, email=email)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
