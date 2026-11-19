"""Main light-theme dashboard."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

ACCENT, RED, AMBER = "#16A34A", "#DC2626", "#D97706"
CARD_BG, MUTED, TEXT = "#F8FAFC", "#6B7280", "#111827"


class Dashboard(ctk.CTk):
    def __init__(self, actions: dict):
        super().__init__()
        self._actions = actions
        self.title("Smart WFH & Leave Tracker")
        self.geometry("920x760")
        self.minsize(840, 680)
        self.configure(fg_color="#FFFFFF")
        self._vars = {k: ctk.StringVar(value="—") for k in (
            "clock", "today", "wfh", "leave", "month", "outlook", "draft", "next", "running")}
        self._history_sig = None
        self._build(actions)

    # ---------- layout ----------
    def _card(self, parent, title: str, var: ctk.StringVar, col: int, color: str = TEXT):
        frame = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14,
                             border_width=1, border_color="#E5E7EB")
        frame.grid(row=0, column=col, padx=6, sticky="nsew")
        ctk.CTkLabel(frame, text=title, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=16, pady=(12, 0))
        label = ctk.CTkLabel(frame, textvariable=var, text_color=color,
                             font=ctk.CTkFont(size=26, weight="bold"), wraplength=240, justify="left")
        label.pack(anchor="w", padx=16, pady=(2, 14))
        return label

    def _build(self, actions: dict) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))
        ctk.CTkLabel(header, text="Smart WFH & Leave Tracker", text_color=TEXT,
                     font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, textvariable=self._vars["clock"], text_color=MUTED,
                     font=ctk.CTkFont(size=14)).pack(side="right")

        today = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=16,
                             border_width=1, border_color="#E5E7EB")
        today.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(today, text="Today's attendance", text_color=MUTED).pack(anchor="w", padx=20, pady=(14, 0))
        self._today_label = ctk.CTkLabel(today, textvariable=self._vars["today"],
                                         font=ctk.CTkFont(size=34, weight="bold"), text_color=AMBER)
        self._today_label.pack(anchor="w", padx=20, pady=(0, 14))

        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=18, pady=4)
        stats.columnconfigure((0, 1, 2), weight=1, uniform="s")
        self._card(stats, "Total WFH", self._vars["wfh"], 0, ACCENT)
        self._card(stats, "Total Leave", self._vars["leave"], 1, RED)
        self._card(stats, "This month", self._vars["month"], 2)

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(fill="x", padx=24, pady=(10, 4))
        info.columnconfigure(1, weight=1)
        for i, (label, key) in enumerate((("Outlook", "outlook"), ("Email draft", "draft"),
                                          ("Next reminder", "next"), ("Application", "running"))):
            ctk.CTkLabel(info, text=label, text_color=MUTED, width=110, anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            ctk.CTkLabel(info, textvariable=self._vars[key], text_color=TEXT, anchor="w",
                         justify="left", wraplength=640).grid(row=i, column=1, sticky="w", pady=2)

        ctk.CTkLabel(self, text="Recent attendance", text_color=TEXT,
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=24, pady=(12, 2))
        self._history = ctk.CTkScrollableFrame(self, fg_color="#FFFFFF", height=150,
                                               border_width=1, border_color="#E5E7EB")
        self._history.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(4, 18))
        spec = (("Full history", "history", ACCENT), ("Settings", "settings", ACCENT),
                ("Check Outlook", "check_outlook", ACCENT), ("Retry draft", "retry_draft", ACCENT), ("Reopen compose", "reopen", ACCENT),
                ("Backup now", "backup", ACCENT), ("Hide to tray", "hide", "#6B7280"),
                ("Quit", "quit", RED))
        for text, key, color in spec:
            hover = {ACCENT: "#15803D", RED: "#B91C1C"}.get(color, "#374151")
            ctk.CTkButton(buttons, text=text, width=96, fg_color=color, hover_color=hover,
                          command=actions[key]).pack(side="left", padx=4)

    # ---------- updates ----------
    def update_view(self, data: dict) -> None:
        for key, var in self._vars.items():
            if key in data:
                var.set(data[key])
        if "today" in data:
            color = {"WFH": ACCENT, "LEAVE": RED}.get(data.get("today_mode"), AMBER)
            self._today_label.configure(text_color=color)
        if "recent" not in data:
            return
        rows = data["recent"]
        sig = tuple((r[0], r[1], r[2]) for r in rows)
        if sig != self._history_sig:
            self._history_sig = sig
            for child in self._history.winfo_children():
                child.destroy()
            if not rows:
                ctk.CTkLabel(self._history, text="No attendance recorded yet.", text_color=MUTED).pack(anchor="w", padx=8, pady=6)
            for date_text, mode, status, attendance_date in rows:
                line = ctk.CTkFrame(self._history, fg_color="transparent")
                line.pack(fill="x", pady=1)
                ctk.CTkLabel(line, text=date_text, width=110, anchor="w").pack(side="left", padx=6)
                ctk.CTkLabel(line, text=mode, width=80, anchor="w", font=ctk.CTkFont(weight="bold"),
                             text_color=ACCENT if mode == "WFH" else RED).pack(side="left")
                ctk.CTkLabel(line, text=status, anchor="w", text_color=MUTED).pack(side="left", padx=6)
                edit = ctk.CTkOptionMenu(
                    line, values=["WFH", "LEAVE"], width=96,
                    command=lambda selected, d=attendance_date: self._actions["edit_recent"](d, selected),
                    fg_color=ACCENT, button_color=ACCENT, dropdown_fg_color=CARD_BG)
                edit.set(mode)
                edit.pack(side="right", padx=6)
