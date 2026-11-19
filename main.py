"""Smart WFH & Leave Tracker - application entry point and controller.

Everything that touches the UI or Outlook runs on the Tk main thread. The tray
icon thread only schedules callbacks onto the main thread. No code path sends mail.
"""
from __future__ import annotations

import argparse
import atexit
import logging
import sys
from datetime import datetime

import customtkinter as ctk

import config
from database.db_manager import DatabaseManager
from services.attendance_service import AttendanceService
from services.notification_service import NotificationService, make_icon_image
from services.outlook_service import RoutedOutlookService
from services.scheduler import ReminderScheduler
from services.startup_service import SingleInstance, StartupService
from ui.attendance_history import HistoryWindow
from ui.dashboard import Dashboard
from ui.reminder_popup import ReminderPopup
from ui.settings import SettingsWindow
from utils import date_utils
from utils.logger import setup_logging

log = logging.getLogger("main")


def _message_box(text: str) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, config.APP_TITLE, 0x40)
    else:
        print(text)


class TrackerApp:
    def __init__(self, start_minimized: bool):
        self.db = DatabaseManager()
        self.outlook = RoutedOutlookService(self.db.get_setting)
        self.attendance = AttendanceService(self.db, self.outlook)
        self.scheduler = ReminderScheduler(self.db)
        self.notifier = NotificationService()
        self.startup = StartupService()
        self.started_at = date_utils.now()
        self._last_tick = None
        self._popup = None
        self._popup_day = None
        self._tray = None
        self._quitting = False
        self._outlook_text = ("Outlook on the web mode (opens in your browser/PWA)"
                              if self.outlook.mode == "web" else
                              ("Classic Outlook detected" if self.outlook.is_installed()
                               else "Classic Outlook not detected - drafts unavailable"))
        self._last_email_msg = "No draft created yet"

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")
        self.root = Dashboard({
            "history": lambda: HistoryWindow(self.root, self.db),
            "settings": self._open_settings,
            "check_outlook": self._check_outlook,
            "retry_draft": self._retry_draft,
            "reopen": self._reopen_draft,
            "edit_recent": self._edit_recent,
            "backup": self._backup_now,
            "hide": self.hide_dashboard,
            "quit": self.quit,
        })
        self.root.protocol("WM_DELETE_WINDOW", self.hide_dashboard)
        self._ensure_startup_registration()
        self._start_tray()
        if start_minimized and self._tray:
            self.root.withdraw()
        atexit.register(self._cleanup)
        self.root.after(500, self._tick)
        self.root.after(1000, self._clock_tick)

    # ---------- tray / window ----------
    def _start_tray(self) -> None:
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem("Open dashboard", lambda: self.root.after(0, self.show_dashboard), default=True),
                pystray.MenuItem("Quit", lambda: self.root.after(0, self.quit)))
            self._tray = pystray.Icon(config.APP_NAME, make_icon_image(), config.APP_TITLE, menu)
            self._tray.run_detached()
            self.notifier.attach_tray(self._tray)
        except Exception:
            log.warning("System tray unavailable; minimizing to taskbar instead", exc_info=True)
            self._tray = None

    def show_dashboard(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_dashboard(self) -> None:
        if self._tray:
            self.root.withdraw()
            self.notifier.notify(config.APP_TITLE, "Still running in the system tray.")
        else:
            self.root.iconify()

    def _ensure_startup_registration(self) -> None:
        wanted = self.db.get_setting("startup_enabled", "1") == "1"
        if wanted and not self.startup.is_enabled():
            self.startup.enable()

    # ---------- scheduler loop ----------
    def _tick(self) -> None:
        try:
            now = date_utils.now()
            if self._last_tick and (now - self._last_tick).total_seconds() > config.POLL_SECONDS * 3:
                log.info("Resume after sleep or clock jump detected; re-evaluating reminders")
            self._last_tick = now
            self._daily_backup(now)
            if self._popup and self._popup_day != now.date():
                self._close_popup()                      # day rolled over while pending
            result = self.scheduler.tick(now)
            if result.show_popup:
                if self._popup is None:
                    self._open_popup(result.new_slot or "R1")
                    if result.new_slot:
                        self.notifier.notify(config.APP_TITLE, "Select WFH or LEAVE for today.", beep=True)
                elif result.new_slot:
                    self._popup.bring_to_front()
                    self.notifier.notify(config.APP_TITLE, "Reminder: select WFH or LEAVE.", beep=True)
            elif self._popup is not None:
                self._close_popup()
            self.refresh()
        except Exception:
            log.exception("Tick failed")
        finally:
            if not self._quitting:
                self.root.after(config.POLL_SECONDS * 1000, self._tick)

    def _clock_tick(self) -> None:
        if self._quitting:
            return
        self.root.update_view({"clock": date_utils.format_datetime(date_utils.now())})
        self.root.after(1000, self._clock_tick)

    def _daily_backup(self, now) -> None:
        key = date_utils.iso_date(now.date())
        if self.db.get_setting("last_backup_date", "") != key:
            try:
                self.db.backup()
                self.db.set_setting("last_backup_date", key)
            except Exception:
                log.exception("Daily backup failed")

    # ---------- popup ----------
    def _open_popup(self, slot: str) -> None:
        self._popup = ReminderPopup(self.root, self._on_select, slot)
        self._popup_day = date_utils.now().date()

    def _close_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            finally:
                self._popup = None

    def _on_select(self, mode: str) -> None:
        try:
            result = self.attendance.select(mode)
        except Exception:
            log.exception("Selection failed")
            self.notifier.notify(config.APP_TITLE, "Could not save your selection. Please try again.")
            if self._popup:
                self._close_popup()
                self._open_popup("R1")
            return
        self._close_popup()
        self._last_email_msg = result.message
        self.notifier.notify(config.APP_TITLE, result.message)
        if mode == "WFH" and not result.draft_created and result.saved:
            self.show_dashboard()                        # surface the failure + Retry button
        self.refresh()

    # ---------- dashboard actions ----------
    def _open_settings(self) -> None:
        SettingsWindow(self.root, self.db, self.startup, self.refresh)

    def _check_outlook(self) -> None:
        ok, message = self.outlook.check_status(self.db.get_setting("sender_email", ""))
        self._outlook_text = message
        self.refresh()

    def _retry_draft(self) -> None:
        result = self.attendance.retry_draft()
        self._last_email_msg = result.message
        self.refresh()

    def _reopen_draft(self) -> None:
        result = self.attendance.reopen_draft()
        self._last_email_msg = result.message
        self.refresh()

    def _edit_recent(self, attendance_date: str, mode: str) -> None:
        try:
            result = self.attendance.edit_attendance(attendance_date, mode)
            self._last_email_msg = result.message
            self.notifier.notify(config.APP_TITLE, result.message)
        except Exception:
            log.exception("Recent attendance edit failed")
            self._last_email_msg = "Could not update the attendance record."
            self.notifier.notify(config.APP_TITLE, self._last_email_msg)
        self.refresh()

    def _backup_now(self) -> None:
        try:
            path = self.db.backup()
            self._last_email_msg = f"Backup saved: {path.name}"
        except Exception as exc:
            self._last_email_msg = f"Backup failed: {exc}"
        self.refresh()

    # ---------- view ----------
    def _mode_text(self) -> str:
        return ("Outlook on the web mode (opens in your browser/PWA)" if self.outlook.mode == "web"
                else self._outlook_text)

    def refresh(self) -> None:
        now = date_utils.now()
        record = self.attendance.today_record()
        counts = self.db.counts()
        month = self.db.month_summary(now.year, now.month)
        nxt = self.scheduler.next_reminder(now)
        if record:
            next_text = f"{date_utils.format_datetime(nxt)} (tomorrow)" if nxt else "—"
        else:
            next_text = date_utils.format_datetime(nxt) if nxt else "Due now - selection pending"
        if record and record["work_mode"] == "WFH":
            draft_text = f"{record['email_status']} - {self._last_email_msg}"
        elif record:
            draft_text = "Not required (Leave)"
        else:
            draft_text = self._last_email_msg
        recent = [(date_utils.format_date(datetime.strptime(r["attendance_date"], "%Y-%m-%d").date()),
                   r["work_mode"], r["email_status"], r["attendance_date"]) for r in self.db.list_attendance(7)]
        self.root.update_view({
            "clock": date_utils.format_datetime(now),
            "today": record["work_mode"] if record else "Not selected yet",
            "today_mode": record["work_mode"] if record else None,
            "wfh": str(counts["WFH"]), "leave": str(counts["LEAVE"]),
            "month": f"{month['WFH']} WFH / {month['LEAVE']} Leave",
            "outlook": self._outlook_text if self.outlook.mode == "classic" else self._mode_text(), "draft": draft_text, "next": next_text,
            "running": f"Running since {date_utils.format_time_12h(self.started_at)}",
            "recent": recent,
        })

    # ---------- shutdown ----------
    def quit(self) -> None:
        self._quitting = True
        self._cleanup()
        try:
            self.root.destroy()
        except Exception:
            pass

    def _cleanup(self) -> None:
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        try:
            self.db.close()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimized", action="store_true", help="start hidden in the tray")
    args = parser.parse_args()
    setup_logging()
    lock = SingleInstance()
    if not lock.acquire():
        _message_box(f"{config.APP_TITLE} is already running. Look for it in the system tray.")
        return 0
    atexit.register(lock.release)
    try:
        TrackerApp(args.minimized).run()
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
