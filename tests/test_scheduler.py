from datetime import datetime

from services.scheduler import ReminderScheduler
from services.startup_service import SingleInstance
from utils.date_utils import TZ


def at(h, m=0, day=18):
    return datetime(2026, 11, day, h, m, tzinfo=TZ)


def test_nothing_before_first_reminder(db):
    result = ReminderScheduler(db).tick(at(10, 59))
    assert not result.show_popup and result.new_slot is None


def test_11am_reminder_fires_once(db):
    sched = ReminderScheduler(db)
    first = sched.tick(at(11, 0))
    assert first.show_popup and first.new_slot == "R1"
    again = sched.tick(at(11, 1))
    assert again.show_popup and again.new_slot is None


def test_3pm_reminder_fires_if_unselected(db):
    sched = ReminderScheduler(db)
    sched.tick(at(11, 0))
    r2 = sched.tick(at(15, 0))
    assert r2.show_popup and r2.new_slot == "R2"
    assert sched.tick(at(15, 1)).new_slot is None


def test_reminder_remains_pending_until_selection(db):
    sched = ReminderScheduler(db)
    for hour in (11, 12, 13, 14, 16, 18, 23):
        assert sched.tick(at(hour, 30)).show_popup


def test_no_more_reminders_after_selection(db):
    db.add_attendance("2026-11-18", "LEAVE", "t", "NOT_REQUIRED")
    sched = ReminderScheduler(db)
    assert not sched.tick(at(11, 0)).show_popup
    assert not sched.tick(at(15, 0)).show_popup


def test_pending_reminder_recovers_after_restart(db):
    ReminderScheduler(db).tick(at(11, 0))          # first run fired R1
    restarted = ReminderScheduler(db)               # app restarted at 11:40
    result = restarted.tick(at(11, 40))
    assert result.show_popup and result.new_slot is None


def test_sleep_and_wake_catches_up(db):
    sched = ReminderScheduler(db)
    assert not sched.tick(at(10, 0)).show_popup
    woke = sched.tick(at(16, 30))                   # laptop slept through 11:00 and 15:00
    assert woke.show_popup and woke.new_slot == "R2"
    assert sched.tick(at(16, 31)).new_slot is None


def test_new_day_resets_reminders(db):
    sched = ReminderScheduler(db)
    sched.tick(at(11, 0))
    assert sched.tick(at(11, 0, day=19)).new_slot == "R1"


def test_custom_reminder_times(db):
    db.set_settings({"first_reminder": "09:30", "second_reminder": "13:00"})
    sched = ReminderScheduler(db)
    assert sched.tick(at(9, 30)).new_slot == "R1"
    assert sched.tick(at(13, 0)).new_slot == "R2"


def test_invalid_setting_falls_back_to_default(db):
    db.set_setting("first_reminder", "banana")
    assert ReminderScheduler(db).tick(at(11, 0)).new_slot == "R1"


def test_next_reminder_times(db):
    sched = ReminderScheduler(db)
    assert sched.next_reminder(at(9, 0)).strftime("%H:%M") == "11:00"
    assert sched.next_reminder(at(12, 0)).strftime("%H:%M") == "15:00"
    assert sched.next_reminder(at(16, 0)) is None
    db.add_attendance("2026-11-18", "WFH", "t", "X")
    nxt = sched.next_reminder(at(16, 0))
    assert nxt.day == 19 and nxt.strftime("%H:%M") == "11:00"


def test_single_instance_lock(tmp_path):
    lock = tmp_path / "app.lock"
    first, second = SingleInstance(lock), SingleInstance(lock)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()
