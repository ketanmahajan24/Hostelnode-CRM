from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

# Paths that must stay reachable without a logged-in session.
PUBLIC_PREFIXES = (
    "/static",
    "/webhook",        # Meta WhatsApp webhook calls this directly
    "/favicon.ico",
)
PUBLIC_PATHS = {
    "/login",
    "/signup",
    "/logout",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Blocks every page/API route behind a logged-in session, except the
    whitelisted paths above. Must run after SessionMiddleware has parsed
    the session cookie (i.e. SessionMiddleware should be added *after*
    this one, since Starlette runs the last-added middleware first).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        is_public = path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES)

        if is_public:
            return await call_next(request)

        user_id = request.session.get("user_id")

        if not user_id:
            # Websocket connections can't be redirected with an HTTP 302;
            # closing the connection is the correct behaviour there.
            if path.startswith("/ws"):
                from starlette.responses import Response
                return Response(status_code=403)

            next_url = path
            if request.url.query:
                next_url += f"?{request.url.query}"
            return RedirectResponse(url=f"/login?next={next_url}", status_code=303)

        return await call_next(request)
