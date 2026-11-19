"""Settings window with validation."""
from __future__ import annotations

from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from database.db_manager import DatabaseManager
from services.attendance_service import invalid_addresses, parse_addresses
from services.startup_service import StartupService
from utils import date_utils

ACCENT, RED = "#16A34A", "#DC2626"


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, db: DatabaseManager, startup: StartupService,
                 on_saved: Callable[[], None]):
        super().__init__(master)
        self._db, self._startup, self._on_saved = db, startup, on_saved
        self.title("Settings")
        self.geometry("640x860")
        self.configure(fg_color="#FFFFFF")
        s = db.all_settings()
        body = ctk.CTkScrollableFrame(self, fg_color="#FFFFFF")
        body.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        self._entries = {}

        def field(label, key, hint=""):
            ctk.CTkLabel(body, text=label + (f"  ({hint})" if hint else ""), anchor="w").pack(fill="x", pady=(8, 0))
            entry = ctk.CTkEntry(body)
            entry.insert(0, s[key])
            entry.pack(fill="x")
            self._entries[key] = entry

        field("First reminder time", "first_reminder", "24-hour HH:MM")
        field("Second reminder time", "second_reminder", "24-hour HH:MM")
        ctk.CTkLabel(body, text="Outlook type", anchor="w").pack(fill="x", pady=(8, 0))
        self._mode = ctk.CTkOptionMenu(body, values=["web", "classic"], fg_color=ACCENT, button_color=ACCENT)
        self._mode.set(s["outlook_mode"])
        self._mode.pack(anchor="w")
        field("Outlook on the web compose link", "web_compose_url", "web mode only")
        field("Email sender address", "sender_email", "must match an Outlook account")
        field("Email recipients (To)", "to_recipients", "separate with ;")
        field("CC recipients", "cc_recipients", "separate with ;")
        field("Email subject template", "subject_template", "{DD/MM/YYYY} = today")
        ctk.CTkLabel(body, text="Email body template", anchor="w").pack(fill="x", pady=(8, 0))
        self._body = ctk.CTkTextbox(body, height=190, border_width=1, border_color="#D1D5DB")
        self._body.insert("1.0", s["body_template"])
        self._body.pack(fill="x")
        ctk.CTkLabel(body, text="Database backup location (blank = default)", anchor="w").pack(fill="x", pady=(8, 0))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self._backup = ctk.CTkEntry(row)
        self._backup.insert(0, s["backup_dir"])
        self._backup.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Browse", width=80, fg_color=ACCENT, command=self._browse).pack(side="left", padx=(6, 0))
        self._startup_var = ctk.BooleanVar(value=startup.is_enabled() or s["startup_enabled"] == "1")
        ctk.CTkCheckBox(body, text="Start automatically when Windows starts", variable=self._startup_var,
                        fg_color=ACCENT).pack(anchor="w", pady=14)

        self._msg = ctk.CTkLabel(self, text="", text_color=RED, wraplength=580)
        self._msg.pack(pady=(6, 0))
        ctk.CTkButton(self, text="Save settings", fg_color=ACCENT, command=self._save).pack(pady=12)
        self.after(100, self.lift)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(parent=self)
        if folder:
            self._backup.delete(0, "end")
            self._backup.insert(0, folder)

    def _validate(self, values: dict) -> str:
        try:
            r1 = date_utils.parse_hhmm(values["first_reminder"])
            r2 = date_utils.parse_hhmm(values["second_reminder"])
        except ValueError as exc:
            return str(exc)
        if r2 <= r1:
            return "The second reminder must be later than the first."
        if not values["web_compose_url"].lower().startswith("https://"):
            return "The Outlook web compose link must start with https://"
        for key in ("sender_email", "to_recipients", "cc_recipients"):
            bad = invalid_addresses(values[key])
            if bad:
                return f"Invalid email address: {', '.join(bad)}"
        if len(parse_addresses(values["sender_email"])) != 1:
            return "Enter exactly one sender address."
        if not values["subject_template"].strip() or not values["body_template"].strip():
            return "Subject and body templates cannot be empty."
        return ""

    def _save(self) -> None:
        values = {k: e.get().strip() for k, e in self._entries.items()}
        values["body_template"] = self._body.get("1.0", "end-1c")
        values["backup_dir"] = self._backup.get().strip()
        values["outlook_mode"] = self._mode.get()
        values["startup_enabled"] = "1" if self._startup_var.get() else "0"
        error = self._validate(values)
        if error:
            self._msg.configure(text=error)
            return
        self._db.set_settings(values)
        ok = self._startup.enable() if self._startup_var.get() else self._startup.disable()
        self._on_saved()
        self._msg.configure(text="" if ok else "Saved, but Windows startup could not be updated.",
                            text_color=RED)
        if ok:
            self.destroy()
