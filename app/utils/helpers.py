from datetime import datetime, timezone


def format_time(dt: datetime) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%I:%M %p").lstrip("0")


def format_day(dt: datetime) -> str:
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.date() == now.date():
        return "Today"
    yesterday = now.date().toordinal() - 1
    if dt.date().toordinal() == yesterday:
        return "Yesterday"
    return dt.strftime("%d %b %Y")


def register_filters(templates_env):
    templates_env.filters["fmt_time"] = format_time
    templates_env.filters["fmt_day"] = format_day
