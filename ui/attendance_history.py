"""Full attendance history with a month filter."""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from database.db_manager import DatabaseManager

ACCENT, RED, MUTED = "#16A34A", "#DC2626", "#6B7280"


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, master, db: DatabaseManager):
        super().__init__(master)
        self._db = db
        self.title("Attendance history")
        self.geometry("720x560")
        self.configure(fg_color="#FFFFFF")
        self._records = db.list_attendance()
        months = sorted({r["attendance_date"][:7] for r in self._records}, reverse=True)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(top, text="Month:").pack(side="left")
        self._filter = ctk.CTkOptionMenu(top, values=["All"] + months, command=lambda _v: self._render(),
                                         fg_color=ACCENT, button_color=ACCENT)
        self._filter.pack(side="left", padx=8)
        self._summary = ctk.CTkLabel(top, text="", text_color=MUTED)
        self._summary.pack(side="right")
        self._list = ctk.CTkScrollableFrame(self, fg_color="#FFFFFF", border_width=1, border_color="#E5E7EB")
        self._list.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._render()
        self.after(100, self.lift)

    @staticmethod
    def _fmt_date(iso: str) -> str:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")

    @staticmethod
    def _fmt_selected(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%I:%M %p")
        except ValueError:
            return value

    def _render(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        chosen = self._filter.get()
        rows = [r for r in self._records if chosen == "All" or r["attendance_date"].startswith(chosen)]
        wfh = sum(1 for r in rows if r["work_mode"] == "WFH")
        self._summary.configure(text=f"WFH {wfh}  •  Leave {len(rows) - wfh}  •  Total {len(rows)}")
        header = ctk.CTkFrame(self._list, fg_color="transparent")
        header.pack(fill="x")
        for text, width in (("Date", 110), ("Mode", 80), ("Selected", 90), ("Email status", 260)):
            ctk.CTkLabel(header, text=text, width=width, anchor="w", text_color=MUTED,
                         font=ctk.CTkFont(weight="bold")).pack(side="left", padx=4)
        for r in rows:
            line = ctk.CTkFrame(self._list, fg_color="transparent")
            line.pack(fill="x", pady=1)
            ctk.CTkLabel(line, text=self._fmt_date(r["attendance_date"]), width=110, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(line, text=r["work_mode"], width=80, anchor="w", font=ctk.CTkFont(weight="bold"),
                         text_color=ACCENT if r["work_mode"] == "WFH" else RED).pack(side="left", padx=4)
            ctk.CTkLabel(line, text=self._fmt_selected(r["selected_at"]), width=90, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(line, text=r["email_status"], width=260, anchor="w", text_color=MUTED).pack(side="left", padx=4)
