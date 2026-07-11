"""
Best-effort IP -> location lookup for the login/signup activity log.

Important honesty note: IP-based geolocation is NOT precise GPS location.
It's typically accurate to city/region level at best (sometimes just the
country), because it's derived from which ISP block the IP was allocated
to — not a device GPS reading. Treat it as "roughly where this connection
came from," not an exact address.
"""
import ipaddress
import httpx
from fastapi import Request

# Free, no-API-key endpoint. Rate-limited (~45 req/min) — fine for an
# admin login log. Swap for a paid provider if you need higher volume
# or HTTPS-only outbound traffic.
IP_LOOKUP_URL = "http://ip-api.com/json/{ip}"
IP_LOOKUP_FIELDS = "status,country,countryCode,regionName,city,lat,lon,isp,query"


def get_client_ip(request: Request) -> str:
    """
    Prefer the original client IP from a reverse proxy header if present,
    falling back to the direct connection IP. If you deploy behind
    Nginx/Cloudflare/etc, make sure it's configured to set X-Forwarded-For.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _is_private_or_local(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return True  # not a parseable IP (e.g. "unknown") — treat as local


async def lookup_ip_location(ip: str) -> dict:
    """
    Returns a dict with best-effort location fields. Never raises —
    on any failure (offline, rate-limited, private IP) it returns a
    dict with location=None so the caller can show "Unknown".
    """
    if _is_private_or_local(ip):
        return {
            "city": None, "region": None, "country": None,
            "country_code": None, "lat": None, "lon": None,
            "isp": None, "note": "Local/private network",
        }

    try:
        async with httpx.AsyncClient(timeout=4) as client:
            res = await client.get(
                IP_LOOKUP_URL.format(ip=ip),
                params={"fields": IP_LOOKUP_FIELDS},
            )
            data = res.json()
            if data.get("status") == "success":
                return {
                    "city": data.get("city"),
                    "region": data.get("regionName"),
                    "country": data.get("country"),
                    "country_code": data.get("countryCode"),
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "isp": data.get("isp"),
                    "note": None,
                }
    except Exception:
        pass

    return {
        "city": None, "region": None, "country": None,
        "country_code": None, "lat": None, "lon": None,
        "isp": None, "note": "Lookup failed",
    }
