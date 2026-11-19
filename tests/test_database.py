import sqlite3

import pytest

from database.db_manager import DatabaseManager


def test_schema_created_with_version(db):
    assert db.schema_version() == 1
    assert db.get_setting("first_reminder") == "11:00"


def test_persists_after_restart(tmp_path):
    path = tmp_path / "attendance.db"
    first = DatabaseManager(path, backup_dir=tmp_path / "bk")
    assert first.add_attendance("2026-11-18", "WFH", "2026-11-18T11:00:00+05:30", "PENDING")
    first.close()
    second = DatabaseManager(path, backup_dir=tmp_path / "bk")
    assert second.get_attendance("2026-11-18")["work_mode"] == "WFH"
    second.close()


def test_duplicate_date_rejected(db):
    assert db.add_attendance("2026-11-18", "WFH", "t", "PENDING")
    assert not db.add_attendance("2026-11-18", "LEAVE", "t", "NOT_REQUIRED")
    assert db.get_attendance("2026-11-18")["work_mode"] == "WFH"


def test_invalid_mode_rejected(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.add_attendance("2026-11-18", "HOLIDAY", "t", "X")


def test_parameterized_queries_resist_injection(db):
    evil = "x'); DROP TABLE attendance;--"
    db.set_setting("subject_template", evil)
    assert db.get_setting("subject_template") == evil
    assert db.add_attendance(evil, "WFH", "t", "PENDING")
    assert db.counts()["WFH"] == 1


def test_counts_and_month_summary(db):
    db.add_attendance("2026-11-02", "WFH", "t", "DRAFT_CREATED")
    db.add_attendance("2026-11-03", "LEAVE", "t", "NOT_REQUIRED")
    db.add_attendance("2026-10-30", "WFH", "t", "DRAFT_CREATED")
    assert db.counts() == {"WFH": 2, "LEAVE": 1}
    assert db.month_summary(2026, 11) == {"WFH": 1, "LEAVE": 1, "TOTAL": 2}


def test_history_preserved_newest_first(db):
    db.add_attendance("2026-11-01", "WFH", "t", "X")
    db.add_attendance("2026-11-02", "LEAVE", "t", "X")
    assert [r["attendance_date"] for r in db.list_attendance()] == ["2026-11-02", "2026-11-01"]


def test_backup_created_and_pruned(db):
    db.add_attendance("2026-11-18", "WFH", "t", "X")
    for _ in range(13):
        path = db.backup()
    assert path.exists()
    assert len(list(db.backup_dir.glob("attendance_backup_*.db"))) == 10


def test_corrupt_db_restored_from_backup(tmp_path):
    path = tmp_path / "attendance.db"
    manager = DatabaseManager(path, backup_dir=tmp_path / "bk")
    manager.add_attendance("2026-11-18", "WFH", "t", "X")
    manager.backup()
    manager.close()
    path.write_bytes(b"this is not a sqlite database" * 50)
    recovered = DatabaseManager(path, backup_dir=tmp_path / "bk")
    assert recovered.get_attendance("2026-11-18")["work_mode"] == "WFH"
    assert list(tmp_path.glob("attendance.corrupt-*.db"))
    recovered.close()


def test_corrupt_db_without_backup_starts_fresh(tmp_path):
    path = tmp_path / "attendance.db"
    path.write_bytes(b"garbage" * 100)
    fresh = DatabaseManager(path, backup_dir=tmp_path / "bk")
    assert fresh.counts() == {"WFH": 0, "LEAVE": 0}
    fresh.close()


def test_migration_keeps_existing_data(tmp_path):
    path = tmp_path / "attendance.db"
    conn = sqlite3.connect(path)
    conn.executescript(open("database/schema.sql", encoding="utf-8").read())
    conn.execute("INSERT INTO attendance (attendance_date, work_mode, selected_at, email_status) "
                 "VALUES ('2026-01-05','LEAVE','t','NOT_REQUIRED')")
    conn.commit()
    conn.close()  # user_version is still 0
    manager = DatabaseManager(path, backup_dir=tmp_path / "bk")
    assert manager.schema_version() == 1
    assert manager.get_attendance("2026-01-05")["work_mode"] == "LEAVE"
    manager.close()
