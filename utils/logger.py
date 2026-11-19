"""Rotating file logger. Never log credentials or full email bodies."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

import config

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    log_dir = config.app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    file_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000,
                                       backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    _configured = True
