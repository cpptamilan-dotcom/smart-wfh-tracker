"""Windows startup registration (HKCU Run key, no admin rights) and single-instance lock."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class StartupService:
    def __init__(self, app_name: str = config.APP_NAME):
        self._name = app_name

    @staticmethod
    def command() -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --minimized'
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else Path(sys.executable)
        main = Path(__file__).resolve().parent.parent / "main.py"
        return f'"{exe}" "{main}" --minimized'

    def is_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, self._name)
                return True
        except OSError:
            return False

    def enable(self) -> bool:
        if sys.platform != "win32":
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self._name, 0, winreg.REG_SZ, self.command())
            return True
        except OSError:
            log.exception("Could not enable startup")
            return False

    def disable(self) -> bool:
        if sys.platform != "win32":
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self._name)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            log.exception("Could not disable startup")
            return False


class SingleInstance:
    """Cross-process lock held for the lifetime of the app (released on exit/crash)."""

    def __init__(self, lock_path: Optional[Path] = None):
        self._path = Path(lock_path) if lock_path else config.app_data_dir() / "app.lock"
        self._fh = None

    def acquire(self) -> bool:
        self._fh = open(self._path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self._fh.close()
            self._fh = None
            return False

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh, fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None
