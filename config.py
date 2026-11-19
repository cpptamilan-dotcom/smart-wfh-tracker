"""Application-wide constants, default settings and path helpers."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "SmartWFHTracker"
APP_TITLE = "Smart WFH & Leave Tracker"
APP_VERSION = "1.0.0"
TIMEZONE = "Asia/Kolkata"
DATE_FORMAT = "%d/%m/%Y"
DB_FILENAME = "attendance.db"
BACKUP_KEEP = 10
POLL_SECONDS = 15

WORK_MODES = ("WFH", "LEAVE")


class EmailStatus:
    NOT_REQUIRED = "NOT_REQUIRED"          # LEAVE: no email by design
    PENDING = "PENDING"                    # WFH saved, draft not yet created
    DRAFT_CREATED = "DRAFT_CREATED"
    FAILED_OUTLOOK_UNAVAILABLE = "FAILED_OUTLOOK_UNAVAILABLE"
    FAILED_SENDER_MISMATCH = "FAILED_SENDER_MISMATCH"
    FAILED = "FAILED"


DEFAULT_SETTINGS = {
    "first_reminder": "11:00",
    "second_reminder": "15:00",
    "sender_name": "Vignesh S",
    "sender_email": "Vignesh.S@andortech.com",
    "to_recipients": "Bhagya.S@andortech.com",
    "cc_recipients": "Anjali.Kumari@andortech.com; Prangya.Priyadarshini@andortech.com",
    "subject_template": "Work From Home Request - {DD/MM/YYYY}",
    "body_template": (
        "Hi Team,\n\n"
        "I have back-to-back client meetings scheduled throughout the {DD/MM/YYYY}. "
        "To attend the meetings without interruptions, I would like to work from home today.\n\n"
        "Please consider this as my WFH request for today.\n\n"
        "Regards,\nVignesh S"
    ),
    "outlook_mode": "web",   # "web" (Outlook on the web / PWA) or "classic" (desktop COM)
    "web_compose_url": "https://outlook.cloud.microsoft/mail/deeplink/compose",
    "startup_enabled": "1",
    "backup_dir": "",
}


def app_data_dir() -> Path:
    """Local application data directory (override with SMART_WFH_HOME)."""
    override = os.environ.get("SMART_WFH_HOME")
    if override:
        base = Path(override)
    elif os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"]) / APP_NAME
    else:
        base = Path.home() / ".smart_wfh_tracker"
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_backup_dir() -> Path:
    path = app_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Locate bundled resources both from source and from a PyInstaller EXE."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative
