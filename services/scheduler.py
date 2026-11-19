"""Reminder logic. Pure and clock-driven so it survives sleep/wake and restarts.

The UI polls tick() from the Tk main thread. Because decisions are based on the
wall clock and on persisted state (not on sleeping timers), a machine that was
asleep through 11:00 simply catches up on the next tick. Nothing here sends mail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from database.db_manager import DatabaseManager
from utils import date_utils

log = logging.getLogger(__name__)
DEFAULT_R1, DEFAULT_R2 = "11:00", "15:00"


@dataclass(frozen=True)
class TickResult:
    show_popup: bool          # a selection is pending: popup must be visible
    new_slot: Optional[str]   # "R1"/"R2" when a reminder fires for the first time today


class ReminderScheduler:
    def __init__(self, db: DatabaseManager):
        self._db = db

    def reminder_times(self):
        def parse(key, default):
            try:
                return date_utils.parse_hhmm(self._db.get_setting(key, default))
            except ValueError:
                log.warning("Invalid %s setting; using %s", key, default)
                return date_utils.parse_hhmm(default)
        r1 = parse("first_reminder", DEFAULT_R1)
        r2 = parse("second_reminder", DEFAULT_R2)
        return r1, r2

    def _selected(self, day) -> bool:
        return self._db.get_attendance(date_utils.iso_date(day)) is not None

    def _fired(self, day) -> set:
        raw = self._db.get_setting("fired_slots", "") or ""
        stamp, _, slots = raw.partition("|")
        if stamp != date_utils.iso_date(day):
            return set()
        return {s for s in slots.split(",") if s}

    def _save_fired(self, day, slots: set) -> None:
        self._db.set_setting("fired_slots", f"{date_utils.iso_date(day)}|{','.join(sorted(slots))}")

    def tick(self, now: Optional[datetime] = None) -> TickResult:
        now = now or date_utils.now()
        if self._selected(now.date()):
            return TickResult(False, None)
        r1, r2 = self.reminder_times()
        current = now.time()
        if current < r1:
            return TickResult(False, None)
        slot = "R2" if (r2 > r1 and current >= r2) else "R1"
        fired = self._fired(now.date())
        new_slot = None
        if slot not in fired:
            fired |= {"R1", slot}
            self._save_fired(now.date(), fired)
            new_slot = slot
            log.info("Reminder %s fired", slot)
        return TickResult(True, new_slot)

    def next_reminder(self, now: Optional[datetime] = None) -> Optional[datetime]:
        """Next future reminder, or None when a selection is already pending right now."""
        now = now or date_utils.now()
        r1, r2 = self.reminder_times()
        if self._selected(now.date()):
            return date_utils.at(now.date() + timedelta(days=1), r1)
        if now.time() < r1:
            return date_utils.at(now.date(), r1)
        if r2 > r1 and now.time() < r2:
            return date_utils.at(now.date(), r2)
        return None
