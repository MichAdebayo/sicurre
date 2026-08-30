"""Per-domain outbound notification policy."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def notification_is_allowed(
    preference: dict[str, Any] | None,
    now: datetime,
    event_type: str = "phishing",
) -> bool:
    """Return whether one domain event may send email now."""
    if preference and not bool(preference.get("email_enabled", 1)):
        return False
    key = {
        "phishing": "notify_phishing",
        "domain_shield": "notify_domain_shield",
    }.get(event_type)
    if preference and key and not bool(preference.get(key, 1)):
        return False
    if not preference or not bool(preference.get("quiet_hours_enabled", 0)):
        return True
    try:
        local_now = now.astimezone(ZoneInfo(str(preference.get("timezone") or "Europe/Paris")))
    except ZoneInfoNotFoundError:
        local_now = now.astimezone(ZoneInfo("UTC"))
    current = local_now.hour * 60 + local_now.minute
    start = _minute_of_day(str(preference.get("quiet_hours_start") or "22:00"))
    end = _minute_of_day(str(preference.get("quiet_hours_end") or "07:00"))
    inside = start <= current < end if start <= end else current >= start or current < end
    return not inside


def _minute_of_day(value: str) -> int:
    hours, minutes = value.split(":", maxsplit=1)
    return int(hours) * 60 + int(minutes)
