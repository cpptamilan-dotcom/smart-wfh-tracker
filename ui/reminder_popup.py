"""Modal-style reminder: always on top, cannot be closed, only WFH or LEAVE completes it."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from utils import date_utils

GREEN, GREEN_HOVER = "#16A34A", "#15803D"
RED, RED_HOVER = "#DC2626", "#B91C1C"


class ReminderPopup(ctk.CTkToplevel):
    def __init__(self, master, on_select: Callable[[str], None], slot: str = "R1"):
        super().__init__(master)
        self._on_select = on_select
        self.overrideredirect(True)                       # no title bar: no close/minimize
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", lambda: None)   # Alt+F4 does nothing
        self.configure(fg_color="#FFFFFF")
        width, height = 520, 340
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 3
        self.geometry(f"{width}x{height}+{x}+{y}")

        card = ctk.CTkFrame(self, fg_color="#FFFFFF", border_width=2,
                            border_color=GREEN, corner_radius=0)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(card, text="What is your work status today?",
                     font=ctk.CTkFont(size=24, weight="bold"), text_color="#111827").pack(pady=(30, 4))
        sub = "Final reminder" if slot == "R2" else "Daily reminder"
        ctk.CTkLabel(card, text=f"{date_utils.format_date(date_utils.today())}  •  {sub}",
                     font=ctk.CTkFont(size=14), text_color="#6B7280").pack(pady=(0, 22))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=30)
        row.columnconfigure((0, 1), weight=1, uniform="b")
        self._wfh = ctk.CTkButton(row, text="🏠\nWORK FROM HOME", height=110, corner_radius=14,
                                  fg_color=GREEN, hover_color=GREEN_HOVER,
                                  font=ctk.CTkFont(size=16, weight="bold"),
                                  command=lambda: self._click("WFH"))
        self._leave = ctk.CTkButton(row, text="🗓\nLEAVE", height=110, corner_radius=14,
                                    fg_color=RED, hover_color=RED_HOVER,
                                    font=ctk.CTkFont(size=16, weight="bold"),
                                    command=lambda: self._click("LEAVE"))
        self._wfh.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self._leave.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self._note = ctk.CTkLabel(card, text="Choose one to continue. WFH prepares an Outlook draft "
                                             "for you to review; nothing is sent automatically.",
                                  font=ctk.CTkFont(size=12), text_color="#6B7280", wraplength=450)
        self._note.pack(pady=(20, 0))
        self.bind("<Escape>", lambda _e: "break")
        self.after(150, self.bring_to_front)

    def bring_to_front(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
        except Exception:
            pass

    def _click(self, mode: str) -> None:
        self._wfh.configure(state="disabled")      # block double clicks
        self._leave.configure(state="disabled")
        self._on_select(mode)
