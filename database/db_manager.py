"""SQLite access layer: parameterized queries, transactions, backups, recovery, migrations."""
from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger(__name__)


def _schema_v1() -> str:
    return config.resource_path("database/schema.sql").read_text(encoding="utf-8")


# (target user_version, callable returning SQL). Append new entries to migrate.
MIGRATIONS = [(1, _schema_v1)]


class DatabaseManager:
    def __init__(self, db_path=None, backup_dir=None):
        self.db_path = Path(db_path) if db_path else config.app_data_dir() / config.DB_FILENAME
        self._backup_dir_override = Path(backup_dir) if backup_dir else None
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists() and not self._is_healthy(self.db_path):
            self._recover()
        self._connect()
        self._migrate()
        self._seed_defaults()

    # ---------- lifecycle ----------
    @staticmethod
    def _is_healthy(path: Path) -> bool:
        try:
            conn = sqlite3.connect(str(path))
            try:
                return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return False

    def _recover(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        corrupt = self.db_path.with_name(f"{self.db_path.stem}.corrupt-{stamp}.db")
        shutil.move(str(self.db_path), str(corrupt))
        log.error("Database corrupt; moved to %s", corrupt)
        for candidate in sorted(self.backup_dir.glob("attendance_backup_*.db"), reverse=True):
            if self._is_healthy(candidate):
                shutil.copy2(candidate, self.db_path)
                log.warning("Restored database from backup %s", candidate)
                return
        log.warning("No healthy backup found; starting with a fresh database")

    def _connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row

    def _migrate(self) -> None:
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            for target, sql_fn in MIGRATIONS:
                if target > version:
                    self._conn.executescript(sql_fn())
                    self._conn.execute(f"PRAGMA user_version = {int(target)}")
                    self._conn.commit()
                    log.info("Database migrated to version %s", target)

    def _seed_defaults(self) -> None:
        with self._lock, self._conn:
            for key, value in config.DEFAULT_SETTINGS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)",
                    (key, value))

    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ---------- settings ----------
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT setting_value FROM settings WHERE setting_key = ?", (key,)).fetchone()
        return row["setting_value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.set_settings({key: value})

    def set_settings(self, values: dict) -> None:
        with self._lock, self._conn:
            for key, value in values.items():
                self._conn.execute(
                    "INSERT INTO settings (setting_key, setting_value) VALUES (?, ?) "
                    "ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value",
                    (key, str(value)))

    def all_settings(self) -> dict:
        with self._lock:
            rows = self._conn.execute("SELECT setting_key, setting_value FROM settings").fetchall()
        merged = dict(config.DEFAULT_SETTINGS)
        merged.update({r["setting_key"]: r["setting_value"] for r in rows})
        return merged

    # ---------- attendance ----------
    def add_attendance(self, attendance_date: str, work_mode: str,
                       selected_at: str, email_status: str) -> bool:
        """Insert today's record. Returns False if the date already exists."""
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT INTO attendance (attendance_date, work_mode, selected_at, email_status) "
                    "VALUES (?, ?, ?, ?)", (attendance_date, work_mode, selected_at, email_status))
            return True
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                return False
            raise

    def update_email_status(self, attendance_date: str, status: str,
                            created_at: Optional[str] = None) -> None:
        with self._lock, self._conn:
            if created_at is not None:
                self._conn.execute(
                    "UPDATE attendance SET email_status = ?, email_created_at = ? "
                    "WHERE attendance_date = ?", (status, created_at, attendance_date))
            else:
                self._conn.execute(
                    "UPDATE attendance SET email_status = ? WHERE attendance_date = ?",
                    (status, attendance_date))

    def update_attendance(self, attendance_date: str, work_mode: str,
                          email_status: str) -> bool:
        """Update an existing attendance record. Returns False if it is missing."""
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE attendance SET work_mode = ?, email_status = ?, "
                "email_created_at = NULL WHERE attendance_date = ?",
                (work_mode, email_status, attendance_date))
        return cursor.rowcount == 1

    def get_attendance(self, attendance_date: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM attendance WHERE attendance_date = ?", (attendance_date,)).fetchone()
        return dict(row) if row else None

    def list_attendance(self, limit: int = 400) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM attendance ORDER BY attendance_date DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT work_mode, COUNT(*) AS n FROM attendance GROUP BY work_mode").fetchall()
        result = {"WFH": 0, "LEAVE": 0}
        result.update({r["work_mode"]: r["n"] for r in rows})
        return result

    def month_summary(self, year: int, month: int) -> dict:
        pattern = f"{year:04d}-{month:02d}-%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT work_mode, COUNT(*) AS n FROM attendance "
                "WHERE attendance_date LIKE ? GROUP BY work_mode", (pattern,)).fetchall()
        result = {"WFH": 0, "LEAVE": 0}
        result.update({r["work_mode"]: r["n"] for r in rows})
        result["TOTAL"] = result["WFH"] + result["LEAVE"]
        return result

    # ---------- backup ----------
    @property
    def backup_dir(self) -> Path:
        if self._backup_dir_override:
            path = self._backup_dir_override
        else:
            configured = ""
            if self._conn is not None:
                configured = (self.get_setting("backup_dir", "") or "").strip()
            path = Path(configured) if configured else config.default_backup_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def backup(self) -> Path:
        dest = self.backup_dir / f"attendance_backup_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                with target:
                    self._conn.backup(target)
            finally:
                target.close()
        backups = sorted(self.backup_dir.glob("attendance_backup_*.db"))
        for old in backups[:-config.BACKUP_KEEP]:
            old.unlink(missing_ok=True)
        log.info("Database backup written to %s", dest)
        return dest
