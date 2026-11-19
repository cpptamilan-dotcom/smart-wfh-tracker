"""Date/time helpers. All 'today' logic uses Asia/Kolkata consistently."""
from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import config

TZ = ZoneInfo(config.TIMEZONE)
_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def iso_date(d: date) -> str:
    return d.isoformat()


def format_date(d: date) -> str:
    return d.strftime(config.DATE_FORMAT)


def format_time_12h(dt) -> str:
    return dt.strftime("%I:%M %p")


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %I:%M %p")


def parse_hhmm(text: str) -> time:
    match = _HHMM.match((text or "").strip())
    if not match:
        raise ValueError(f"'{text}' is not a valid 24-hour time (use HH:MM, e.g. 15:00)")
    return time(int(match.group(1)), int(match.group(2)))


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=TZ)
