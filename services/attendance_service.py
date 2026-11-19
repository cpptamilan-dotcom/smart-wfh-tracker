"""Attendance business rules: validate, save, and (WFH only) prepare an Outlook draft."""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

import config
from database.db_manager import DatabaseManager
from services.outlook_service import EmailDraft, OutlookService
from utils import date_utils

log = logging.getLogger(__name__)
_EMAIL_RE = re.compile(r"^[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+$")


def parse_addresses(text: str) -> list:
    return [p.strip() for p in re.split(r"[;,\n]", text or "") if p.strip()]


def invalid_addresses(text: str) -> list:
    return [a for a in parse_addresses(text) if not _EMAIL_RE.match(a)]


@dataclass
class SelectionResult:
    saved: bool
    duplicate: bool
    work_mode: Optional[str]
    email_status: Optional[str]
    message: str
    draft_created: bool = False


class AttendanceService:
    def __init__(self, db: DatabaseManager, outlook: OutlookService,
                 clock: Callable = date_utils.now):
        self._db = db
        self._outlook = outlook
        self._clock = clock
        self._lock = threading.Lock()

    def today_record(self) -> Optional[dict]:
        return self._db.get_attendance(date_utils.iso_date(self._clock().date()))

    def has_selected_today(self) -> bool:
        return self.today_record() is not None

    def build_draft(self, on_date: date) -> EmailDraft:
        s = self._db.all_settings()
        stamp = date_utils.format_date(on_date)
        return EmailDraft(
            sender_email=s["sender_email"],
            to=parse_addresses(s["to_recipients"]),
            cc=parse_addresses(s["cc_recipients"]),
            subject=s["subject_template"].replace("{DD/MM/YYYY}", stamp),
            body=s["body_template"].replace("{DD/MM/YYYY}", stamp),
        )

    def select(self, mode: str) -> SelectionResult:
        mode = (mode or "").strip().upper()
        if mode not in config.WORK_MODES:
            raise ValueError(f"Invalid work mode: {mode!r}")
        with self._lock:
            now = self._clock()
            today = now.date()
            key = date_utils.iso_date(today)
            existing = self._db.get_attendance(key)
            if existing:
                return self._duplicate(existing)
            status = (config.EmailStatus.PENDING if mode == "WFH"
                      else config.EmailStatus.NOT_REQUIRED)
            if not self._db.add_attendance(key, mode, now.isoformat(timespec="seconds"), status):
                return self._duplicate(self._db.get_attendance(key) or {})
            log.info("Attendance saved: %s %s", key, mode)
            if mode == "LEAVE":
                return SelectionResult(True, False, "LEAVE", status,
                                       "Leave recorded. No email was created.")
            return self._create_draft(today, now)

    def edit_attendance(self, attendance_date: str, mode: str) -> SelectionResult:
        """Edit an existing record without an approval/permission prompt.

        Changing to WFH prepares a reviewable Outlook draft when the record does
        not already have one. No email is ever sent automatically.
        """
        mode = (mode or "").strip().upper()
        if mode not in config.WORK_MODES:
            raise ValueError(f"Invalid work mode: {mode!r}")
        with self._lock:
            existing = self._db.get_attendance(attendance_date)
            if not existing:
                return SelectionResult(False, False, None, None,
                                       "Attendance record was not found.")
            status = (config.EmailStatus.PENDING if mode == "WFH"
                      else config.EmailStatus.NOT_REQUIRED)
            if mode == "WFH" and existing["email_status"] == config.EmailStatus.DRAFT_CREATED:
                status = config.EmailStatus.DRAFT_CREATED
            self._db.update_attendance(attendance_date, mode, status)
            if mode == "LEAVE":
                return SelectionResult(True, False, mode, status,
                                       "Attendance updated to Leave.")
            if status == config.EmailStatus.DRAFT_CREATED:
                return SelectionResult(True, False, mode, status,
                                       "Attendance updated. The existing Outlook draft was kept.",
                                       draft_created=True)
            parsed = date.fromisoformat(attendance_date)
            return self._create_draft(parsed, self._clock())

    def retry_draft(self) -> SelectionResult:
        """Retry a failed WFH draft. Never creates a second draft once one exists."""
        with self._lock:
            now = self._clock()
            record = self._db.get_attendance(date_utils.iso_date(now.date()))
            if not record or record["work_mode"] != "WFH":
                return SelectionResult(False, False, None, None,
                                       "No WFH record for today, so there is no draft to create.")
            if record["email_status"] == config.EmailStatus.DRAFT_CREATED:
                return SelectionResult(False, True, "WFH", record["email_status"],
                                       "A draft was already created today. Check Outlook drafts.",
                                       draft_created=True)
            return self._create_draft(now.date(), now)

    def reopen_draft(self) -> SelectionResult:
        """User-initiated: open the compose window again (e.g. a web link that did not pre-fill).
        Only for today's WFH record; still draft-only and never sends."""
        with self._lock:
            now = self._clock()
            record = self._db.get_attendance(date_utils.iso_date(now.date()))
            if not record or record["work_mode"] != "WFH":
                return SelectionResult(False, False, None, None, "No WFH record for today.")
            return self._create_draft(now.date(), now)

    # ---------- internals ----------
    def _create_draft(self, today: date, now) -> SelectionResult:
        result = self._outlook.create_draft(self.build_draft(today))
        created_at = now.isoformat(timespec="seconds") if result.success else None
        self._db.update_email_status(date_utils.iso_date(today), result.status, created_at)
        return SelectionResult(True, False, "WFH", result.status, result.message, result.success)

    @staticmethod
    def _duplicate(existing: dict) -> SelectionResult:
        mode = existing.get("work_mode")
        return SelectionResult(False, True, mode, existing.get("email_status"),
                               f"Today's attendance is already recorded as {mode}.")
