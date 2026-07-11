from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings

try:
    DISPLAY_TZ = ZoneInfo(settings.display_timezone)
except Exception:
    DISPLAY_TZ = timezone.utc


def format_time(dt: datetime) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ).strftime("%I:%M %p").lstrip("0")


def format_day(dt: datetime) -> str:
    if not dt:
        return ""
    now = datetime.now(DISPLAY_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(DISPLAY_TZ)
    if dt.date() == now.date():
        return "Today"
    yesterday = now.date().toordinal() - 1
    if dt.date().toordinal() == yesterday:
        return "Yesterday"
    return dt.strftime("%d %b %Y")


def format_datetime_full(dt: datetime) -> str:
    """Full timestamp including seconds, converted to the configured display
    timezone, e.g. '11 Jul 2026, 11:24:05 PM IST'."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_dt = dt.astimezone(DISPLAY_TZ)
    tz_label = local_dt.tzname() or str(DISPLAY_TZ)
    return local_dt.strftime(f"%d %b %Y, %I:%M:%S %p {tz_label}").replace(" 0", " ")


def short_user_agent(ua: str) -> str:
    """Very lightweight browser/OS summary, no extra dependency needed."""
    if not ua:
        return "Unknown device"
    ua_l = ua.lower()

    if "edg/" in ua_l:
        browser = "Edge"
    elif "chrome/" in ua_l and "chromium" not in ua_l:
        browser = "Chrome"
    elif "firefox/" in ua_l:
        browser = "Firefox"
    elif "safari/" in ua_l and "chrome" not in ua_l:
        browser = "Safari"
    else:
        browser = "Browser"

    if "windows" in ua_l:
        os_name = "Windows"
    elif "mac os" in ua_l or "macintosh" in ua_l:
        os_name = "macOS"
    elif "android" in ua_l:
        os_name = "Android"
    elif "iphone" in ua_l or "ipad" in ua_l:
        os_name = "iOS"
    elif "linux" in ua_l:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"

    return f"{browser} on {os_name}"


def register_filters(templates_env):
    templates_env.filters["fmt_time"] = format_time
    templates_env.filters["fmt_day"] = format_day
    templates_env.filters["fmt_datetime_full"] = format_datetime_full
    templates_env.filters["short_ua"] = short_user_agent